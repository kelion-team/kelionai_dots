"""Claude (Anthropic) is an optional sixth identity: separate credential, never an alias of cloud (Codex)."""
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import threading
import unittest

from channel_bridge.shared import PARTICIPANTS, OPTIONAL_PARTICIPANTS
from channel_bridge.shared_http import make_server
from channel_bridge.shared_client import ChannelClient, ChannelClientError


class ClaudeIdentityTests(unittest.TestCase):
    def start(self, directory, tokens):
        server = make_server(Path(directory) / 'channel.sqlite', 'owner', tokens, port=0)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        self.addCleanup(lambda: (server.shutdown(), server.server_close(), worker.join(3)))
        return f'http://127.0.0.1:{server.server_port}'

    def test_claude_is_optional_and_absent_without_its_own_credential(self):
        self.assertIn('claude', OPTIONAL_PARTICIPANTS)
        self.assertNotIn('claude', PARTICIPANTS)
        tokens = {peer: secrets.token_urlsafe(32) for peer in PARTICIPANTS}
        with tempfile.TemporaryDirectory() as directory:
            base = self.start(directory, tokens)
            health = ChannelClient(base, tokens['cloud'], expected_participant='cloud').health()
            self.assertNotIn('claude', health['participants'])
            sent = ChannelClient(base, tokens['kelion'], expected_participant='kelion').send(
                {'id': 'no-claude', 'correlation_id': 'c', 'text': 'five only'})
            self.assertNotIn('claude', sent['recipients'])

    def test_claude_shares_the_same_ordered_context_with_a_separate_identity(self):
        peers = PARTICIPANTS + ('claude',)
        tokens = {peer: secrets.token_urlsafe(32) for peer in peers}
        with tempfile.TemporaryDirectory() as directory:
            base = self.start(directory, tokens)
            clients = {peer: ChannelClient(base, token, expected_participant=peer) for peer, token in tokens.items()}
            claude = clients['claude']
            self.assertEqual(sorted(claude.health()['participants']), sorted(peers))
            # Claude receives what the others broadcast, in the same stored order.
            first = clients['kelion'].send({'id': 'k-1', 'correlation_id': 'oglinda', 'text': 'context comun 1'})
            second = clients['cloud'].send({'id': 'c-1', 'correlation_id': 'oglinda', 'text': 'context comun 2'})
            self.assertIn('claude', first['recipients'])
            inbox = claude.read(unread_only=True)['messages']
            self.assertEqual([m['id'] for m in inbox], ['k-1', 'c-1'])
            self.assertEqual([m['sender'] for m in inbox], ['kelion', 'cloud'])
            claude.ack(inbox[0]['id'], inbox[0]['sha256'])
            # Claude's ACK is its own: it does not acknowledge for cloud (Codex) or anyone else.
            self.assertEqual(clients['kelion'].get('k-1')['acknowledged_by'], ['claude'])
            reply = claude.send({'id': 'claude-ack-1', 'correlation_id': 'oglinda', 'reply_to': 'k-1',
                                 'text': 'ACK citit efectiv: k-1'})
            for peer in set(peers) - {'claude'}:
                got = [m for m in clients[peer].read()['messages'] if m['id'] == 'claude-ack-1']
                self.assertEqual(len(got), 1)
                self.assertEqual(got[0]['sender'], 'claude')
                self.assertEqual(got[0]['sha256'], reply['sha256'])
            self.assertEqual(second['sender'], 'cloud')

    def test_no_alias_or_impersonation_between_claude_and_cloud(self):
        peers = PARTICIPANTS + ('claude',)
        tokens = {peer: secrets.token_urlsafe(32) for peer in peers}
        with tempfile.TemporaryDirectory() as directory:
            shared = dict(tokens, claude=tokens['cloud'])
            with self.assertRaisesRegex(ValueError, 'distinct credential'):
                make_server(Path(directory) / 'same.sqlite', 'owner', shared, port=0)
            with self.assertRaisesRegex(ValueError, 'Separate credentials required'):
                make_server(Path(directory) / 'unknown.sqlite', 'owner', dict(tokens, codex=secrets.token_urlsafe(32)), port=0)
            base = self.start(directory, tokens)
            with self.assertRaises(ChannelClientError):
                ChannelClient(base, tokens['cloud'], expected_participant='claude').health()
            with self.assertRaises(ChannelClientError):
                ChannelClient(base, tokens['cloud'], expected_participant='cloud').send(
                    {'id': 'spoof', 'correlation_id': 'c', 'text': 'x', 'sender': 'claude'})

    def test_cli_accepts_claude_only_with_its_own_variable(self):
        peers = PARTICIPANTS + ('claude',)
        tokens = {peer: secrets.token_urlsafe(32) for peer in peers}
        with tempfile.TemporaryDirectory() as directory:
            base = self.start(directory, tokens)
            env = dict(os.environ, KELION_CHANNEL_URL=base, KELION_CHANNEL_CLAUDE_TOKEN=tokens['claude'])
            env.pop('KELION_CHANNEL_CLOUD_TOKEN', None)
            result = subprocess.run([sys.executable, '-B', '-m', 'channel_bridge.shared_client', '--participant', 'claude', 'health'],
                                    env=env, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['participant'], 'claude')
            self.assertNotIn(tokens['claude'], result.stdout + result.stderr)
            env['KELION_CHANNEL_CLAUDE_TOKEN'] = tokens['cloud']
            result = subprocess.run([sys.executable, '-B', '-m', 'channel_bridge.shared_client', '--participant', 'claude', 'health'],
                                    env=env, capture_output=True, text=True, timeout=10)
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn(tokens['cloud'], result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
