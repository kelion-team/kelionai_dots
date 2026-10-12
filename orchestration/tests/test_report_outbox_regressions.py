"""Offline regression tests for atomic publication and destination validation."""
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import unittest

from orchestration.report_outbox import ReportOutbox


def expected_digest(payload):
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                         separators=(',', ':'), allow_nan=False)
    return hashlib.sha256(encoded.encode()).hexdigest()


class InsertSchedule:
    """Hold winner's write transaction until loser reaches its INSERT call.

    Unlike a two-reader barrier, this scheduler is compatible with the fixed
    insert-before-read algorithm. It records transaction state on each read.
    """
    def __init__(self, connection, role, winner_inserted, loser_attempted, log):
        self.connection = connection
        self.role = role
        self.winner_inserted = winner_inserted
        self.loser_attempted = loser_attempted
        self.log = log

    def __enter__(self):
        self.connection.__enter__()
        return self

    def __exit__(self, *args):
        return self.connection.__exit__(*args)

    def execute(self, sql, parameters=()):
        if sql.startswith('INSERT OR IGNORE INTO reports'):
            self.log.append({'statement': 'report-insert-attempt'})
            if self.role == 'loser':
                if not self.winner_inserted.wait(5):
                    raise RuntimeError('Winner did not acquire write transaction')
                self.loser_attempted.set()
            result = self.connection.execute(sql, parameters)
            self.log.append({'statement': 'report-insert-return',
                             'rowcount': result.rowcount,
                             'in_transaction': self.connection.in_transaction})
            if self.role == 'winner':
                self.winner_inserted.set()
                if not self.loser_attempted.wait(5):
                    raise RuntimeError('Loser did not attempt its publication')
            return result
        if sql.startswith('SELECT task_id,payload FROM reports'):
            self.log.append({'statement': 'report-validation-read',
                             'in_transaction': self.connection.in_transaction})
        return self.connection.execute(sql, parameters)

    def close(self):
        self.connection.close()


class ReportOutboxRegressions(unittest.TestCase):
    def check_overlapping_publications(self, case, loser_task, loser_payload,
                                       expect_conflict):
        with tempfile.TemporaryDirectory(prefix='independent-outbox-') as directory:
            path = Path(directory) / 'outbox.sqlite'
            seed = ReportOutbox(path)
            seed.close()
            ready = threading.Barrier(2)
            winner_inserted = threading.Event()
            loser_attempted = threading.Event()
            observations = {role: {'sql': []} for role in ('winner', 'loser')}
            winner_payload = {'state': 'running', 'details': {'b': 2, 'a': 1}}
            requests = {
                'winner': ('task', winner_payload),
                'loser': (loser_task, loser_payload),
            }

            def worker(role):
                box = None
                try:
                    box = ReportOutbox(path)
                    box.db = InsertSchedule(box.db, role, winner_inserted,
                                            loser_attempted,
                                            observations[role]['sql'])
                    ready.wait(5)
                    task, payload = requests[role]
                    observations[role]['digest'] = box.publish(
                        'owner', 'event', task, payload, [role + '-destination'])
                except BaseException as error:
                    observations[role]['error'] = type(error).__name__
                    observations[role]['message'] = str(error)
                finally:
                    if box is not None:
                        box.close()

            workers = [threading.Thread(target=worker, args=(role,), daemon=True)
                       for role in ('winner', 'loser')]
            for thread in workers:
                thread.start()
            for thread in workers:
                thread.join(12)
            self.assertFalse(any(thread.is_alive() for thread in workers),
                             'Bounded concurrent publication timed out')
            box = ReportOutbox(path)
            try:
                reports = box.db.execute(
                    'SELECT task_id,payload,digest FROM reports').fetchall()
                recipients = [row[0] for row in box.db.execute(
                    'SELECT destination FROM recipients ORDER BY destination')]
                pending = box.pending('owner', 'loser-destination')
                self.assertNotIn('error', observations['winner'])
                self.assertEqual(observations['winner']['digest'],
                                 expected_digest(winner_payload))
                self.assertEqual(len(reports), 1)
                self.assertEqual(reports[0][0], 'task')
                self.assertEqual(json.loads(reports[0][1]), winner_payload)
                self.assertEqual(reports[0][2], observations['winner']['digest'])
                for role in ('winner', 'loser'):
                    reads = [entry for entry in observations[role]['sql']
                             if entry['statement'] == 'report-validation-read']
                    self.assertEqual(len(reads), 1)
                    self.assertTrue(reads[0]['in_transaction'])
                    self.assertEqual(observations[role]['sql'][0]['statement'],
                                     'report-insert-attempt')
                self.assertEqual(observations['winner']['sql'][1]['rowcount'], 1)
                self.assertEqual(observations['loser']['sql'][1]['rowcount'], 0)
                if expect_conflict:
                    self.assertEqual(observations['loser'].get('error'), 'ValueError')
                    self.assertNotIn('digest', observations['loser'])
                    self.assertEqual(recipients, ['winner-destination'])
                    self.assertEqual(pending, [])
                else:
                    self.assertNotIn('error', observations['loser'])
                    self.assertEqual(observations['loser']['digest'], reports[0][2])
                    self.assertEqual(recipients,
                                     ['loser-destination', 'winner-destination'])
                    self.assertEqual(len(pending), 1)
            finally:
                box.close()

    def test_overlapping_payload_conflict_rolls_back_loser(self):
        self.check_overlapping_publications(
            'overlapping_payload_conflict', 'task', {'state': 'verified'}, True)

    def test_overlapping_task_conflict_rolls_back_loser(self):
        self.check_overlapping_publications(
            'overlapping_task_conflict', 'different-task',
            {'details': {'a': 1, 'b': 2}, 'state': 'running'}, True)

    def test_overlapping_identical_publications_keep_both_destinations(self):
        self.check_overlapping_publications(
            'overlapping_identical', 'task',
            {'details': {'a': 1, 'b': 2}, 'state': 'running'}, False)

    def test_invalid_destination_shapes_leave_no_rows(self):
        invalid = ['user-ui', b'user-ui', None, [], [' '], ['user-ui', 3],
                   ['user-ui', None], [False], ['']]
        with tempfile.TemporaryDirectory(prefix='independent-destinations-') as directory:
            box = ReportOutbox(Path(directory) / 'outbox.sqlite')
            try:
                for destinations in invalid:
                    with self.subTest(destinations=repr(destinations)):
                        with self.assertRaises(ValueError):
                            box.publish('owner', 'event', 'task', {}, destinations)
                        self.assertEqual(box.db.execute(
                            'SELECT COUNT(*) FROM reports').fetchone()[0], 0)
                        self.assertEqual(box.db.execute(
                            'SELECT COUNT(*) FROM recipients').fetchone()[0], 0)
            finally:
                box.close()

    def test_dedup_generator_replay_preserves_acknowledgement(self):
        with tempfile.TemporaryDirectory(prefix='independent-replay-') as directory:
            path = Path(directory) / 'outbox.sqlite'
            box = ReportOutbox(path)
            try:
                digest = box.publish('owner', 'event', 'task', {'b': 2, 'a': 1},
                                     (x for x in ['user-ui', 'user-ui', 'orchestrator']))
                box.acknowledge('owner', 'user-ui', 'event', digest)
                replay_digest = box.publish('owner', 'event', 'task', {'a': 1, 'b': 2},
                                            ['user-ui', 'new-ui'])
                self.assertEqual(replay_digest, digest)
                self.assertEqual(box.pending('owner', 'user-ui'), [])
                self.assertEqual(len(box.pending('owner', 'new-ui')), 1)
                recipients = box.db.execute(
                    'SELECT destination,acknowledged FROM recipients ORDER BY destination'
                ).fetchall()
                self.assertEqual(recipients,
                                 [('new-ui', 0), ('orchestrator', 0), ('user-ui', 1)])
                self.assertEqual(box.pending('other-owner', 'new-ui'), [])
                box.close()
                box = ReportOutbox(path)
                self.assertEqual(box.pending('owner', 'user-ui'), [])
                self.assertEqual(box.pending('owner', 'new-ui')[0]['sha256'], digest)
            finally:
                box.close()


if __name__ == '__main__':
    unittest.main()
