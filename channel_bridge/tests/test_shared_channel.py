import tempfile
import unittest
from pathlib import Path

try:
    from channel_bridge.shared import SharedChannel, ChannelError
except ImportError:
    SharedChannel = None
    ChannelError = ValueError

PARTICIPANTS = ('chatgpt', 'work', 'kelion', 'cloud', 'contabo')


class SharedChannelTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'channel.sqlite'

    def channel(self):
        self.assertIsNotNone(SharedChannel, 'The authenticated shared transport is missing')
        return SharedChannel(self.path, 'kelion-owner', PARTICIPANTS)

    def test_broadcast_has_independent_readback_and_ack_for_every_recipient(self):
        channel = self.channel()
        sent = channel.send('kelion', {'id': 'message-1', 'correlation_id': 'task-1', 'text': 'Mesaj comun'})
        self.assertEqual(sent['state'], 'stored')
        self.assertEqual(sent['sender'], 'kelion')
        self.assertEqual(sent['recipients'], ['chatgpt', 'cloud', 'contabo', 'work'])
        for peer in sent['recipients']:
            inbox = channel.read(peer, unread_only=True)
            self.assertEqual(len(inbox), 1)
            self.assertEqual(inbox[0]['text'], 'Mesaj comun')
            self.assertEqual(inbox[0]['sha256'], sent['sha256'])
        channel.acknowledge('work', sent['id'], sent['sha256'])
        self.assertEqual(channel.read('work', unread_only=True), [])
        self.assertEqual(len(channel.read('cloud', unread_only=True)), 1)
        status = channel.get('kelion', sent['id'])
        self.assertEqual(status['acknowledged_by'], ['work'])
        self.assertNotIn('completed', status)

    def test_reply_returns_actual_text_and_is_preserved_after_restart(self):
        channel = self.channel()
        original = channel.send('cloud', {'id': 'original', 'correlation_id': 'task-1', 'text': 'Salut', 'recipients': ['contabo']})
        reply = channel.send('contabo', {'id': 'reply', 'correlation_id': 'task-1', 'text': 'Am primit', 'reply_to': 'original'})
        channel.acknowledge('contabo', original['id'], original['sha256'])
        restarted = self.channel()
        self.assertEqual(restarted.get('cloud', reply['id'])['text'], 'Am primit')
        self.assertEqual(restarted.get('cloud', reply['id'])['reply_to'], original['id'])
        self.assertEqual(restarted.get('cloud', original['id'])['acknowledged_by'], ['contabo'])

    def test_sender_cannot_be_spoofed_and_private_messages_are_isolated(self):
        channel = self.channel()
        with self.assertRaises(ChannelError):
            channel.send('cloud', {'id': 'spoof', 'correlation_id': 'task-1', 'text': 'bad', 'sender': 'contabo'})
        private = channel.send('cloud', {'id': 'private', 'correlation_id': 'task-1', 'text': 'Scoped', 'recipients': ['contabo']})
        self.assertEqual(channel.read('work'), [])
        with self.assertRaises(ChannelError):
            channel.get('work', private['id'])
        with self.assertRaises(ChannelError):
            channel.acknowledge('work', private['id'], private['sha256'])
        with self.assertRaises(ChannelError):
            channel.send('unknown', {'id': 'bad', 'correlation_id': 'task-1', 'text': 'bad'})

    def test_retry_is_idempotent_and_id_content_conflict_is_rejected(self):
        channel = self.channel()
        message = {'id': 'same-id', 'correlation_id': 'task-1', 'text': 'Original', 'recipients': ['contabo']}
        first = channel.send('cloud', message)
        self.assertEqual(channel.send('cloud', message)['sha256'], first['sha256'])
        self.assertEqual(len(channel.read('contabo')), 1)
        for change in [{'text': 'Changed'}, {'recipients': ['work']}, {'correlation_id': 'other'}]:
            with self.assertRaises(ChannelError):
                channel.send('cloud', message | change)
        with self.assertRaises(ChannelError):
            channel.send('work', message)

    def test_ack_requires_correct_hash_and_receipt_is_not_a_task_result(self):
        channel = self.channel()
        message = channel.send('cloud', {'id': 'ack-test', 'correlation_id': 'task-1', 'text': 'Hello'})
        with self.assertRaises(ChannelError):
            channel.acknowledge('contabo', message['id'], 'wrong')
        receipt = channel.acknowledge('contabo', message['id'], message['sha256'])
        self.assertEqual(receipt['participant'], 'contabo')
        self.assertEqual(receipt['state'], 'read_acknowledged')
        self.assertNotIn('result', receipt)
        channel.acknowledge('contabo', message['id'], message['sha256'])
        self.assertEqual(channel.get('cloud', message['id'])['acknowledged_by'], ['contabo'])

    def test_reply_must_reference_visible_message_and_same_correlation(self):
        channel = self.channel()
        channel.send('cloud', {'id': 'private', 'correlation_id': 'task-1', 'text': 'Hi', 'recipients': ['contabo']})
        for peer, ref, correlation in [('work', 'private', 'task-1'), ('contabo', 'absent', 'task-1'), ('contabo', 'private', 'different')]:
            with self.assertRaises(ChannelError):
                channel.send(peer, {'id': 'invalid-reply', 'correlation_id': correlation, 'text': 'reply', 'reply_to': ref})

    def test_integrity_hash_binds_id_and_original_correlation(self):
        channel = self.channel()
        channel.send('cloud', {'id': 'bound-message', 'correlation_id': 'original-task', 'text': 'Payload'})
        import sqlite3
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE reports SET task_id='different-task' WHERE event_id='bound-message'")
        with self.assertRaises(ChannelError):
            channel.get('cloud', 'bound-message')

    def test_owner_isolation_pagination_and_bounds(self):
        channel = self.channel()
        for i in range(3):
            channel.send('cloud', {'id': f'item-{i}', 'correlation_id': 'task-1', 'text': 'Message'})
        page = channel.read('contabo', limit=2)
        self.assertEqual(len(page), 2)
        self.assertEqual([x['id'] for x in channel.read('contabo', after=page[-1]['sequence'])], ['item-2'])
        other = SharedChannel(self.path, 'other-owner', PARTICIPANTS)
        self.assertEqual(other.read('contabo'), [])
        for invalid in [0, 101, True, '2']:
            with self.assertRaises(ChannelError):
                channel.read('contabo', limit=invalid)
        with self.assertRaises(ChannelError):
            channel.send('cloud', {'id': 'huge', 'correlation_id': 'task-1', 'text': 'x' * 32001})


if __name__ == '__main__':
    unittest.main()
