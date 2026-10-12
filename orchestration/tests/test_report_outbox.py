import tempfile
import unittest
from pathlib import Path
from orchestration.report_outbox import ReportOutbox


class ReportDeliveryTest(unittest.TestCase):
    def test_restart_independent_acknowledgements_and_isolation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'reports.sqlite'
            box = ReportOutbox(path)
            digest = box.publish('owner', 'event', 'task', {'state': 'running'},
                                 ['user-ui', 'orchestrator'])
            box.publish('owner', 'event', 'task', {'state': 'running'},
                        ['user-ui', 'orchestrator'])
            box.close()
            box = ReportOutbox(path)
            self.assertEqual(len(box.pending('owner', 'user-ui')), 1)
            self.assertEqual(box.pending('other-owner', 'user-ui'), [])
            with self.assertRaises(ValueError):
                box.acknowledge('owner', 'user-ui', 'event', 'wrong')
            box.acknowledge('owner', 'user-ui', 'event', digest)
            self.assertEqual(box.pending('owner', 'user-ui'), [])
            self.assertEqual(len(box.pending('owner', 'orchestrator')), 1)
            with self.assertRaises(ValueError):
                box.publish('owner', 'event', 'task', {'state': 'verified'}, ['user-ui'])
            box.close()


if __name__ == '__main__':
    unittest.main()
