"""The cloud/Codex environment has its own identity, independent of Claude."""
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import threading
import unittest

from channel_bridge.shared_http import make_server
from channel_bridge.shared_client import ChannelClient


class CloudIdentityTests(unittest.TestCase):
    def test_each_environment_can_read_acknowledge_and_reply_to_cloud(self):
        peers = ('chatgpt', 'work', 'kelion', 'cloud', 'contabo')
        tokens = {peer: secrets.token_urlsafe(32) for peer in peers}
        with tempfile.TemporaryDirectory() as directory:
            server = make_server(Path(directory) / 'channel.sqlite', 'owner', tokens, port=0)
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                base = f'http://127.0.0.1:{server.server_port}'
                clients = {peer: ChannelClient(base, token, expected_participant=peer)
                           for peer, token in tokens.items()}
                cloud = clients['cloud']
                original = cloud.send({'id': 'cloud-probe', 'correlation_id': 'cloud-connect',
                                       'text': 'Message from the cloud environment here'})
                self.assertEqual(set(original['recipients']), set(peers) - {'cloud'})
                for peer in original['recipients']:
                    received = clients[peer].read(unread_only=True)['messages'][0]
                    self.assertEqual(received['sha256'], original['sha256'])
                    clients[peer].ack(received['id'], received['sha256'])
                    clients[peer].send({'id': 'reply-' + peer, 'correlation_id': 'cloud-connect',
                                        'reply_to': original['id'], 'text': 'Reply from ' + peer})
                self.assertEqual(set(cloud.get(original['id'])['acknowledged_by']), set(peers) - {'cloud'})
                self.assertEqual({message['sender'] for message in cloud.read()['messages']},
                                 set(peers) - {'cloud'})
                health = cloud.health()
                self.assertNotIn('claude', health['participants'])
                env = dict(os.environ, KELION_CHANNEL_URL=base,
                           KELION_CHANNEL_CLOUD_TOKEN=tokens['cloud'],
                           KELION_CHANNEL_CLAUDE_TOKEN=secrets.token_urlsafe(32))
                result = subprocess.run([sys.executable, '-B', '-m', 'channel_bridge.shared_client',
                                         '--participant', 'cloud', 'health'], env=env,
                                        capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout)['participant'], 'cloud')
                for token in tokens.values():
                    self.assertNotIn(token, result.stdout + result.stderr)
                env.pop('KELION_CHANNEL_CLOUD_TOKEN')
                env['KELION_CHANNEL_CLAUDE_TOKEN'] = tokens['cloud']
                result = subprocess.run([sys.executable, '-B', '-m', 'channel_bridge.shared_client',
                                         '--participant', 'cloud', 'health'], env=env,
                                        capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 2)
                self.assertIn('configured channel credential is required', result.stderr)
                self.assertNotIn(tokens['cloud'], result.stdout + result.stderr)
                legacy_tokens = dict(tokens)
                legacy_tokens['claude'] = legacy_tokens.pop('cloud')
                with self.assertRaisesRegex(ValueError, 'Separate credentials required'):
                    make_server(Path(directory) / 'legacy.sqlite', 'owner', legacy_tokens, port=0)
            finally:
                server.shutdown()
                server.server_close()
                worker.join(3)


if __name__ == '__main__':
    unittest.main()
