import json
import os
import secrets
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from channel_bridge.shared_http import make_server
try:
    from channel_bridge.shared_client import ChannelClient, ChannelClientError
except ImportError:
    ChannelClient = None
    ChannelClientError = ValueError


class SharedClientTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(ChannelClient, 'Authenticated remote and stdio clients are missing')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.tokens = {peer: secrets.token_urlsafe(32) for peer in ('chatgpt', 'work', 'kelion', 'cloud', 'contabo')}
        self.server = make_server(Path(self.temp.name) / 'db.sqlite', 'owner', self.tokens, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)
        self.base = f'http://127.0.0.1:{self.server.server_port}'

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(3)

    def test_clients_send_receive_ack_and_reply_over_real_http(self):
        kelion = ChannelClient(self.base, self.tokens['kelion'], expected_participant='kelion')
        cloud = ChannelClient(self.base, self.tokens['cloud'], expected_participant='cloud')
        self.assertEqual(cloud.health()['participant'], 'cloud')
        sent = kelion.send({'id': 'client-msg', 'correlation_id': 'task-1', 'text': 'Hello cloud'})
        received = cloud.read(unread_only=True)['messages'][0]
        self.assertEqual(received['sha256'], sent['sha256'])
        cloud.ack(received['id'], received['sha256'])
        cloud.send({'id': 'client-reply', 'correlation_id': 'task-1', 'text': 'Actual reply', 'reply_to': received['id']})
        self.assertEqual(kelion.read()['messages'][0]['text'], 'Actual reply')
        self.assertEqual(kelion.get(sent['id'])['acknowledged_by'], ['cloud'])

    def test_cli_read_and_stdio_mcp_are_real_subprocess_clients(self):
        ChannelClient(self.base, self.tokens['kelion']).send({'id': 'cli-msg', 'correlation_id': 'task-1', 'text': 'For client'})
        env = dict(os.environ, KELION_CHANNEL_URL=self.base, KELION_CHANNEL_CLOUD_TOKEN=self.tokens['cloud'])
        process = subprocess.run([sys.executable, '-B', '-m', 'channel_bridge.shared_client', 'read', '--unread-only'],
                                 env=env, capture_output=True, text=True, timeout=10)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(json.loads(process.stdout)['messages'][0]['text'], 'For client')
        messages = [
            {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {'protocolVersion': '2025-03-26', 'capabilities': {}, 'clientInfo': {'name': 'stdio-test', 'version': '1'}}},
            {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
            {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call', 'params': {'name': 'kelion_channel_read', 'arguments': {}}},
        ]
        process = subprocess.run([sys.executable, '-B', '-m', 'channel_bridge.shared_client', 'stdio'],
            input=''.join(json.dumps(x)+'\n' for x in messages), env=env, capture_output=True, text=True, timeout=10)
        self.assertEqual(process.returncode, 0, process.stderr)
        replies = [json.loads(line) for line in process.stdout.splitlines()]
        self.assertEqual(len(replies), 2)
        self.assertEqual(replies[0]['result']['serverInfo']['name'], 'kelion-shared-channel')
        self.assertEqual(replies[1]['result']['structuredContent']['messages'][0]['text'], 'For client')
        self.assertNotIn(self.tokens['cloud'], process.stdout + process.stderr)

    def test_large_mcp_inbox_is_byte_bounded_and_can_be_fully_paginated(self):
        sender = ChannelClient(self.base, self.tokens['kelion'])
        reader = ChannelClient(self.base, self.tokens['cloud'])
        for i in range(24):
            sender.send({'id': f'large-{i}', 'correlation_id': 'task-1', 'text': '\x00' * 32000})
        after, ids = 0, []
        while True:
            page = reader.request('/mcp', {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
                'params': {'name': 'kelion_channel_read', 'arguments': {'after': after, 'limit': 100}}}, mcp=True)
            data = page['result']['structuredContent']
            self.assertTrue(data['messages'])
            ids.extend(message['id'] for message in data['messages'])
            after = data['next_after']
            if not data['has_more']:
                break
        self.assertEqual(ids, [f'large-{i}' for i in range(24)])

    def test_plaintext_remote_credentials_and_wrong_identity_are_refused(self):
        for url in ['http://example.com', 'https://user:pass@example.com', 'https://example.com/?token=bad', 'https://example.com/#fragment']:
            with self.assertRaises(ChannelClientError):
                ChannelClient(url, self.tokens['cloud'])
        client = ChannelClient(self.base, self.tokens['cloud'], expected_participant='contabo')
        with self.assertRaises(ChannelClientError):
            client.health()
        with self.assertRaises(ChannelClientError):
            client.read()
        with self.assertRaises(ChannelClientError):
            ChannelClient(self.base, 'invalid').health()


if __name__ == '__main__':
    unittest.main()
