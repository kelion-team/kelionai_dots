import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from channel_bridge.bridge import Bridge, Blocked, Endpoint, Message, NotSent


class MockAdapter:
    def __init__(self):
        self.calls = []
        self.failure = None
        self.available = True

    def send(self, message):
        self.calls.append(message.id)
        if self.failure:
            raise self.failure
        return {'kind': 'ack', 'principal': 'brain-principal', 'correlation_id': message.correlation_id}

    def health(self):
        return self.available


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'ledger.db'
        self.now = 100
        self.adapter = MockAdapter()
        self.endpoints = [Endpoint(n, True, True, 'mock-contract', n + '-principal')
                          for n in ('keliondots', 'brain', 'cloud')]
        self.b = self.open()
        self.m = Message('msg-1', 'task-1', 'keliondots', 'brain', 'test')

    def open(self, enabled=True):
        return Bridge(self.path, self.endpoints, {'brain': self.adapter}, enabled,
                      clock=lambda: self.now, result_timeout=30)

    def tearDown(self):
        self.b.close()
        self.tmp.cleanup()

    def submit(self):
        return self.b.submit(self.m, 'keliondots-principal')

    def test_missing_identity_cannot_bypass_auth(self):
        for principal in (None, '', ' '):
            with self.assertRaisesRegex(Blocked, 'authenticated_principal_required'):
                self.b.submit(self.m, principal)
        self.submit()
        self.b.tick()
        with self.assertRaisesRegex(Blocked, 'authenticated_principal_required'):
            self.b.receive('msg-1', 'task-1', 'result', None, 'forged')
        self.assertEqual(self.b.status('msg-1')['state'], 'awaiting_result')

    def test_disabled_is_inert(self):
        self.b.enabled = False
        with self.assertRaisesRegex(Blocked, 'bridge_disabled'):
            self.submit()
        self.b.tick()
        self.assertEqual(self.adapter.calls, [])

    def test_authorization_and_unverified_endpoint(self):
        with self.assertRaisesRegex(Blocked, 'unauthorized'):
            self.b.submit(self.m, 'forged')
        self.b.endpoints['brain'] = Endpoint('brain')
        with self.assertRaisesRegex(Blocked, 'adapter_not_configured'):
            self.submit()
        self.assertEqual(self.adapter.calls, [])

    def test_duplicate_survives_restart(self):
        self.submit()
        self.b.close()
        self.b = self.open()
        self.submit()
        self.b.tick()
        self.submit()
        self.b.tick()
        self.assertEqual(self.adapter.calls, ['msg-1'])
        self.assertEqual(self.b.status('msg-1')['attempts'], 1)

    def test_conflicting_id_rejected(self):
        self.submit()
        with self.assertRaisesRegex(ValueError, 'id_content_conflict'):
            self.b.submit(Message('msg-1', 'task-1', 'keliondots', 'brain', 'changed'), 'keliondots-principal')

    def test_ack_is_not_result_and_duplicate_ack_no_extension(self):
        self.assertEqual(self.submit()['kind'], 'accepted_local')
        self.b.tick()
        self.assertEqual(self.b.status('msg-1')['state'], 'awaiting_result')
        self.now += 20
        self.b.receive('msg-1', 'task-1', 'ack', 'brain-principal')
        self.assertEqual(self.b.status('msg-1')['due'], 130)
        self.b.receive('msg-1', 'task-1', 'result', 'brain-principal', 'actual mock output')
        self.b.receive('msg-1', 'task-1', 'ack', 'brain-principal')
        self.assertEqual(self.b.status('msg-1')['state'], 'completed')
        self.assertEqual(self.b.status('msg-1')['result'], 'actual mock output')

    def test_result_auth_correlation_and_content(self):
        self.submit()
        with self.assertRaisesRegex(ValueError, 'receipt_before_delivery'):
            self.b.receive('msg-1', 'task-1', 'result', 'brain-principal', 'x')
        self.b.tick()
        with self.assertRaises(Blocked):
            self.b.receive('msg-1', 'task-1', 'result', 'cloud-principal', 'x')
        with self.assertRaisesRegex(ValueError, 'invalid_receipt'):
            self.b.receive('msg-1', 'other', 'result', 'brain-principal', 'x')
        with self.assertRaisesRegex(ValueError, 'actual_result_required'):
            self.b.receive('msg-1', 'task-1', 'result', 'brain-principal')
        self.b.receive('msg-1', 'task-1', 'result', 'brain-principal', 'x')
        self.b.receive('msg-1', 'task-1', 'result', 'brain-principal', 'x')
        with self.assertRaisesRegex(ValueError, 'result_conflict'):
            self.b.receive('msg-1', 'task-1', 'result', 'brain-principal', 'y')

    def test_retry_backoff_limit_and_restart(self):
        self.adapter.failure = NotSent()
        self.submit()
        self.b.tick()
        self.assertEqual(self.b.status('msg-1')['due'], 105)
        self.b.close()
        self.b = self.open()
        self.b.tick()
        self.assertEqual(len(self.adapter.calls), 1)
        self.now = 105
        self.b.tick()
        self.assertEqual(self.b.status('msg-1')['due'], 115)
        self.now = 115
        self.b.tick()
        self.now = 1000
        self.b.tick()
        self.assertEqual(len(self.adapter.calls), 3)
        self.assertEqual(self.b.status('msg-1')['state'], 'failed')

    def test_temporary_unavailable_then_recovered(self):
        self.adapter.failure = NotSent()
        self.submit()
        self.b.tick()
        self.adapter.failure = None
        self.now = 105
        self.b.tick()
        self.assertEqual(self.b.status('msg-1')['state'], 'awaiting_result')

    def test_unknown_effect_no_retry(self):
        self.adapter.failure = TimeoutError('secret must not be persisted')
        self.submit()
        self.b.tick()
        self.now = 1000
        self.b.tick()
        row = self.b.status('msg-1')
        self.assertEqual(row['state'], 'uncertain')
        self.assertNotIn('secret', row['reason'])
        self.assertEqual(len(self.adapter.calls), 1)

    def test_crash_during_send_requires_reconciliation(self):
        self.submit()
        with self.b.db:
            self.b.db.execute("UPDATE messages SET state='sending',attempts=1")
        self.b.close()
        self.b = self.open()
        self.b.tick()
        self.assertEqual(self.b.status('msg-1')['reason'], 'restart_during_send')
        self.assertEqual(self.adapter.calls, [])
        self.b.receive('msg-1', 'task-1', 'result', 'brain-principal', 'readback')
        self.assertEqual(self.b.status('msg-1')['state'], 'completed')

    def test_result_timeout_does_not_resend(self):
        self.submit()
        self.b.tick()
        self.now = 131
        self.b.tick()
        self.assertEqual(self.b.status('msg-1')['reason'], 'result_timeout_no_resend')
        self.assertEqual(len(self.adapter.calls), 1)

    def test_revocation_blocks_pending(self):
        self.submit()
        self.b.endpoints['brain'] = Endpoint('brain', blocker='access_revoked')
        self.b.tick()
        self.assertEqual(self.b.status('msg-1')['reason'], 'access_revoked')
        self.assertEqual(self.adapter.calls, [])

    def test_exclusive_ledger(self):
        with self.assertRaisesRegex(Blocked, 'ledger_already_owned'):
            self.open()

    def test_health_unavailable_and_default_registry(self):
        self.adapter.available = False
        self.assertEqual(self.b.health()['endpoints']['brain'], 'adapter_unavailable')
        config = json.loads((Path(__file__).parents[1] / 'registry.json').read_text())
        self.b.endpoints = {e['name']: Endpoint(**e) for e in config['endpoints']}
        self.assertEqual(self.b.health()['readiness'], 'blocked')
        self.assertEqual(self.b.health()['endpoints']['cloud'], 'cloud_conversation_delivery_api_undocumented')

    def test_cli_reports_blocked_without_network(self):
        proc = subprocess.run([sys.executable, '-B', '-m', 'channel_bridge', '--config',
                               str(Path(__file__).parents[1] / 'registry.json'), '--state',
                               str(Path(self.tmp.name) / 'cli.db')], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)['readiness'], 'blocked')

    def test_no_unknown_routes_or_limits(self):
        with self.assertRaises(ValueError):
            Message('x', 'c', 'keliondots', 'http://arbitrary', 'x').encode()
        with self.assertRaises(ValueError):
            Bridge(self.path, self.endpoints, max_attempts=100)


if __name__ == '__main__':
    unittest.main()
