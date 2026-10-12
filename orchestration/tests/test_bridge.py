import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bridge


class FakeResponse:
    def __init__(self, status, value):
        self.status = status
        self.value = json.dumps(value).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.value


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.env = bridge.prepare('kelion-4', 'codex', 'agt_123', 'agtch_456', 'Hello',
                                  'https://github.com/kelion-team/kelionai_dots/issues/4')

    def test_prepare_only(self):
        self.assertEqual(self.env['status'], 'prepared_not_dispatched')
        self.assertEqual(self.env['origin'], 'codex')

    def test_refuse_bad_channel(self):
        with self.assertRaises(ValueError):
            bridge.prepare('kelion-4', 'chat', 'agt_123', 'agt_456', 'Hello', None)

    def test_refuse_unrecognized_surface(self):
        with self.assertRaises(ValueError):
            bridge.prepare('kelion-4', 'another', 'agt_123', 'agtch_456', 'Hello', None)

    def test_trigger_request_and_no_secret_in_receipt(self):
        def fake_open(req, timeout):
            self.assertEqual(req.get_method(), 'POST')
            self.assertEqual(req.get_header('Openai-beta'), 'workspace_agent_runs=v1')
            self.assertTrue(req.get_header('Idempotency-key'))
            self.assertEqual(req.get_header('Authorization'), 'Bearer SECRET')
            body = json.loads(req.data.decode())
            self.assertEqual(body['conversation_key'], 'kelion-4')
            self.assertIn('Task ledger:', body['input'])
            return FakeResponse(202, {'conversation_url': 'https://chatgpt.com/c/aaa',
                                      'agent_trigger_run_id': 'apirun_123'})
        receipt = bridge.trigger(self.env, 'SECRET', opener=fake_open)
        self.assertEqual(receipt['status'], 'trigger_accepted')
        self.assertFalse(receipt['verified'])
        self.assertNotIn('SECRET', json.dumps(receipt))

    def test_trigger_no_fake_success_without_url(self):
        def fake(req, timeout):
            return FakeResponse(202, {})
        with self.assertRaises(RuntimeError):
            bridge.trigger(self.env, 'SECRET', opener=fake)

    def test_status_completed_does_not_prove_result(self):
        receipt = {'task_id': 'kelion-4', 'api_trigger_id': 'agtch_456',
                   'agent_trigger_run_id': 'apirun_123', 'status': 'trigger_accepted'}
        def fake(req, timeout):
            self.assertEqual(req.get_method(), 'GET')
            return FakeResponse(200, {'id': 'apirun_123', 'status': 'completed'})
        out = bridge.check_status(receipt, 'SECRET', opener=fake)
        self.assertEqual(out['status'], 'run_completed_result_not_retrieved')
        self.assertFalse(out['verified'])
        self.assertFalse(out['result_retrieved'])

    def test_wrong_run_id_rejected(self):
        receipt = {'api_trigger_id': 'agtch_456', 'agent_trigger_run_id': 'apirun_123'}
        def fake(req, timeout):
            return FakeResponse(200, {'id': 'apirun_OTHER', 'status': 'completed'})
        with self.assertRaises(RuntimeError):
            bridge.check_status(receipt, 'SECRET', opener=fake)

    def test_missing_access_token_rejected(self):
        with self.assertRaises(ValueError):
            bridge.trigger(self.env, None)

    def test_no_live_trigger_without_execute(self):
        self.assertEqual(bridge.main(['trigger', '--envelope', '/nonexistent', '--out', '/tmp/out.json']), 2)


if __name__ == '__main__':
    unittest.main()
