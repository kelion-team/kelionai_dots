"""Real loopback HTTP and SQLite; no external identity or model calls."""
import json
import unittest
import test_worker_http as helpers
from store import canonical, digest


class GatewayIngressTests(unittest.TestCase):
    setUp = helpers.AtomicWorkerHTTPTests.setUp
    tearDown = helpers.AtomicWorkerHTTPTests.tearDown
    call = helpers.AtomicWorkerHTTPTests.call

    def stored_payload(self, task_id):
        with self.store.connect() as db:
            row = db.execute('SELECT payload FROM tasks WHERE task_id=?', (task_id,)).fetchone()
        return json.loads(row['payload'])

    def test_authenticated_http_records_private_marker_without_public_leak(self):
        raw = dict(self.raw, task_id='SYNTHETIC-gateway-auth')
        status, result = self.call('/v1/tasks', raw, self.client)
        self.assertEqual(status, 202)
        self.assertEqual(result['input_hash'], digest(canonical(raw)))
        self.assertNotIn('private_ingress', result['payload'])
        payload = self.stored_payload(raw['task_id'])
        self.assertIn('private_ingress', payload)
        self.assertEqual(payload['request'], raw)
        self.assertEqual(payload['private_ingress']['authenticated_client_sha256'], digest(self.client))
        self.assertIsInstance(payload['private_ingress']['received_at'], (int, float))
        self.assertNotIn(self.client, canonical(payload))
        self.assertNotIn('private_ingress', self.store.get(raw['task_id'])['payload'])

    def test_unmarked_task_cannot_be_upgraded_by_replaying_authenticated_http(self):
        original = self.stored_payload(self.raw['task_id'])
        self.assertNotIn('private_ingress', original)
        status, _ = self.call('/v1/tasks', self.raw, self.client)
        self.assertEqual(status, 202)
        self.assertEqual(self.stored_payload(self.raw['task_id']), original)

    def test_client_supplied_marker_is_rejected_without_creating_task(self):
        raw = dict(self.raw, task_id='SYNTHETIC-forged-marker', private_ingress={
            'authenticated_client_sha256': digest(self.client), 'received_at': 123})
        self.assertEqual(self.call('/v1/tasks', raw, self.client)[0], 400)
        with self.assertRaises(KeyError):
            self.store.get(raw['task_id'])

    def test_invalid_credential_cannot_create_marked_task(self):
        raw = dict(self.raw, task_id='SYNTHETIC-unauthorized-marker')
        self.assertEqual(self.call('/v1/tasks', raw, 'SYNTHETIC-invalid-token')[0], 401)
        with self.assertRaises(KeyError):
            self.store.get(raw['task_id'])


if __name__ == '__main__':
    unittest.main()
