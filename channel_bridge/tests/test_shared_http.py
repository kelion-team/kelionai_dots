import json
import secrets
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, build_opener, ProxyHandler

try:
    from channel_bridge.shared_http import make_server
except ImportError:
    make_server = None

PEERS = ('chatgpt', 'work', 'kelion', 'claude', 'contabo')


class SharedHTTPTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(make_server, 'The shared channel has no HTTP/MCP listener')
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.tokens = {peer: secrets.token_urlsafe(32) for peer in PEERS}
        self.path = Path(self.directory.name) / 'channel.sqlite'
        self.http = build_opener(ProxyHandler({}))
        self.start()
        self.addCleanup(self.stop)

    def start(self):
        self.server = make_server(self.path, 'owner', self.tokens, port=0, public_origin='https://kelionai.app')
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = 'http://127.0.0.1:' + str(self.server.server_port)

    def stop(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.thread.join(3)
            self.server = None

    def request(self, peer, path, body=None, expected=200, headers=None):
        actual = {'Authorization': 'Bearer ' + self.tokens[peer]} if peer else {}
        actual.update(headers or {})
        if body is not None:
            actual['Content-Type'] = 'application/json'
        request = Request(self.base + path, data=json.dumps(body).encode() if body is not None else None, headers=actual)
        try:
            with self.http.open(request, timeout=3) as response:
                status, content = response.status, response.read()
        except HTTPError as error:
            status, content = error.code, error.read()
        self.assertEqual(status, expected, content[:1000])
        return json.loads(content)

    def test_five_authenticated_clients_can_read_broadcast_and_reply(self):
        sent = self.request('kelion', '/v1/messages', {'id': 'broadcast', 'correlation_id': 'task-1', 'text': 'Urgent'}, 201)
        for peer in ('chatgpt', 'work', 'claude', 'contabo'):
            messages = self.request(peer, '/v1/inbox')['messages']
            self.assertEqual(messages[0]['text'], 'Urgent')
            self.request(peer, '/v1/ack', {'id': sent['id'], 'sha256': messages[0]['sha256']})
        status = self.request('kelion', '/v1/message/broadcast')
        self.assertEqual(status['acknowledged_by'], ['chatgpt', 'claude', 'contabo', 'work'])
        self.request('contabo', '/v1/messages', {'id': 'reply', 'correlation_id': 'task-1', 'text': 'Contabo reply', 'reply_to': 'broadcast'}, 201)
        messages = self.request('kelion', '/v1/inbox')['messages']
        self.assertEqual(messages[0]['text'], 'Contabo reply')
        self.assertEqual(messages[0]['reply_to'], 'broadcast')

    def test_authentication_host_origin_and_identity_cannot_be_bypassed(self):
        self.request(None, '/v1/health', expected=401)
        self.request('claude', '/v1/health', expected=403, headers={'Host': 'attacker.example'})
        self.request('claude', '/v1/health', expected=403, headers={'Origin': 'https://attacker.example'})
        self.request('claude', '/v1/messages', {'id': 'spoof', 'correlation_id': 'task-1', 'text': 'bad', 'sender': 'contabo'}, 400)
        health = self.request('claude', '/v1/health')
        self.assertEqual(health['participant'], 'claude')
        self.assertEqual(health['model_execution'], False)
        self.assertEqual(health['delivery_mode'], 'authenticated_client_readback')
        self.assertNotIn('token', json.dumps(health))

    def test_private_message_cannot_be_read_or_acked_by_other_identity(self):
        sent = self.request('claude', '/v1/messages', {'id': 'private', 'correlation_id': 'task-1', 'text': 'private text', 'recipients': ['contabo']}, 201)
        self.request('work', '/v1/message/private', expected=400)
        self.request('work', '/v1/ack', {'id': 'private', 'sha256': sent['sha256']}, 400)
        self.assertEqual(self.request('work', '/v1/inbox')['messages'], [])

    def test_restart_preserves_dedup_and_per_recipient_ack(self):
        body = {'id': 'durable', 'correlation_id': 'task-1', 'text': 'Keep me'}
        sent = self.request('claude', '/v1/messages', body, 201)
        self.request('work', '/v1/ack', {'id': sent['id'], 'sha256': sent['sha256']})
        self.stop()
        self.start()
        self.request('claude', '/v1/messages', body, 201)
        self.assertEqual(self.request('work', '/v1/inbox?unread_only=true')['messages'], [])
        self.assertEqual(len(self.request('contabo', '/v1/inbox')['messages']), 1)

    def test_mcp_initialize_send_read_and_ack_use_authenticated_identity(self):
        headers = {'Accept': 'application/json, text/event-stream'}
        def rpc(peer, method, params):
            return self.request(peer, '/mcp', {'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params}, headers=headers)
        init = rpc('work', 'initialize', {'protocolVersion': '2025-03-26', 'capabilities': {}, 'clientInfo': {'name': 'real-http-test', 'version': '1'}})
        self.assertEqual(init['result']['serverInfo']['name'], 'kelion-shared-channel')
        names = {tool['name'] for tool in rpc('work', 'tools/list', {})['result']['tools']}
        self.assertEqual(names, {'kelion_channel_send', 'kelion_channel_read', 'kelion_channel_ack', 'kelion_channel_get'})
        sent = rpc('work', 'tools/call', {'name': 'kelion_channel_send', 'arguments': {'id': 'mcp', 'correlation_id': 'task-1', 'text': 'From MCP'}})
        self.assertFalse(sent['result']['isError'])
        self.assertEqual(sent['result']['structuredContent']['sender'], 'work')
        received = rpc('chatgpt', 'tools/call', {'name': 'kelion_channel_read', 'arguments': {}})['result']['structuredContent']['messages']
        self.assertEqual(received[0]['text'], 'From MCP')
        reply = rpc('chatgpt', 'tools/call', {'name': 'kelion_channel_ack', 'arguments': {'id': 'mcp', 'sha256': received[0]['sha256']}})
        self.assertEqual(reply['result']['structuredContent']['participant'], 'chatgpt')
        forbidden = rpc('claude', 'tools/call', {'name': 'run_model', 'arguments': {}})
        self.assertIn('error', forbidden)

    def test_mcp_read_accepts_omitted_optional_arguments(self):
        request = {'jsonrpc': '2.0', 'id': 7, 'method': 'tools/call',
                   'params': {'name': 'kelion_channel_read'}}
        reply = self.request('claude', '/mcp', request,
                             headers={'Accept': 'application/json, text/event-stream'})
        self.assertFalse(reply['result']['isError'])
        self.assertEqual(reply['result']['structuredContent']['messages'], [])

    def test_public_origin_trailing_slash_is_canonicalized(self):
        self.stop()
        self.server = make_server(self.path, 'owner', self.tokens, port=0, public_origin='https://kelionai.app/')
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = 'http://127.0.0.1:' + str(self.server.server_port)
        self.request('claude', '/v1/health', headers={'Origin': 'https://kelionai.app'})

    def test_invalid_unicode_is_a_bounded_client_error(self):
        self.request('claude', '/v1/messages', {'id': 'unicode', 'correlation_id': 'task-1', 'text': '\ud800'}, 400)

    def test_invalid_configuration_and_bounded_request_parameters(self):
        with self.assertRaises(ValueError):
            make_server(self.path, 'owner', dict.fromkeys(PEERS, 'same' * 10), port=0)
        for query in ['limit=101', 'limit=true', 'after=-1', 'unread_only=wrong', 'sender=work', 'limit=2&limit=3']:
            self.request('claude', '/v1/inbox?' + query, expected=400)
        self.request('claude', '/v1/messages', {'id': 'big', 'correlation_id': 'task-1', 'text': 'x' * 270000}, 413)


if __name__ == '__main__':
    unittest.main()
