"""Authenticated hosts share a durable message outbox, never a model executor."""
import hashlib
import json
import re
from pathlib import Path
from orchestration.report_outbox import ReportOutbox

IDENTITY = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}$')
PARTICIPANTS = ('chatgpt', 'work', 'kelion', 'claude', 'contabo')


class ChannelError(ValueError):
    pass


def identifier(value):
    if not isinstance(value, str) or not IDENTITY.fullmatch(value):
        raise ChannelError('Invalid identifier')
    return value


class SharedChannel:
    """The host supplies participant identity from authentication, never request JSON.

    Each operation opens its own SQLite connection so HTTP threads do not share
    connections. The existing ReportOutbox owns atomic fanout and acknowledgement.
    Reading does not imply acknowledgement, task completion, or model execution.
    """
    def __init__(self, path, owner, participants=PARTICIPANTS):
        self.path = Path(path)
        self.owner = identifier(owner)
        self.participants = tuple(sorted(set(participants)))
        if len(self.participants) < 2:
            raise ChannelError('At least two participants required')
        for participant in self.participants:
            identifier(participant)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._open().close()

    def _open(self):
        return ReportOutbox(self.path)

    def _participant(self, participant):
        if participant not in self.participants:
            raise ChannelError('Unknown authenticated participant')

    def _get(self, box, participant, message_id):
        row = box.db.execute('SELECT rowid,event_id,task_id,payload,digest FROM reports '
                             'WHERE owner=? AND event_id=?', (self.owner, identifier(message_id))).fetchone()
        if row is None:
            raise ChannelError('Message not available to this participant')
        sequence, event_id, correlation_id, encoded, digest = row
        payload = json.loads(encoded)
        if not isinstance(payload, dict) or not {'id', 'correlation_id', 'sender', 'recipients', 'text', 'reply_to'} <= payload.keys():
            raise ChannelError('Dedicated shared-channel database required; incompatible stored message')
        if payload['id'] != event_id or payload['correlation_id'] != correlation_id:
            raise ChannelError('Stored message identity or correlation integrity check failed')
        if participant != payload['sender'] and participant not in payload['recipients']:
            raise ChannelError('Message not available to this participant')
        if hashlib.sha256(encoded.encode()).hexdigest() != digest:
            raise ChannelError('Stored message integrity check failed')
        acknowledgements = box.db.execute('SELECT destination FROM recipients '
            'WHERE owner=? AND event_id=? AND acknowledged=1 ORDER BY destination',
            (self.owner, message_id)).fetchall()
        return dict(payload, id=event_id, correlation_id=correlation_id, sequence=sequence,
                    sha256=digest, acknowledged_by=[row[0] for row in acknowledgements], state='stored')

    def get(self, participant, message_id):
        self._participant(participant)
        box = self._open()
        try:
            return self._get(box, participant, message_id)
        finally:
            box.close()

    def send(self, participant, message):
        self._participant(participant)
        required = {'id', 'correlation_id', 'text'}
        if not isinstance(message, dict) or not required <= message.keys() or not set(message) <= required | {'recipients', 'reply_to'}:
            raise ChannelError('Send requires id, correlation_id, text; optional recipients and reply_to only')
        message_id, correlation_id = identifier(message['id']), identifier(message['correlation_id'])
        text = message['text']
        if not isinstance(text, str) or not text.strip():
            raise ChannelError('Message text must contain 1..32000 UTF-8 bytes')
        try:
            size = len(text.encode('utf-8'))
        except UnicodeError:
            raise ChannelError('Message text must be valid UTF-8') from None
        if size > 32000:
            raise ChannelError('Message text must contain 1..32000 UTF-8 bytes')
        reply_to = message.get('reply_to')
        original = self.get(participant, reply_to) if reply_to is not None else None
        if original and original['correlation_id'] != correlation_id:
            raise ChannelError('Reply correlation must match the original message')
        default_recipients = (set(original['recipients']) | {original['sender']} if original
                              else set(self.participants)) - {participant}
        recipients = message.get('recipients', sorted(default_recipients))
        if not isinstance(recipients, list) or not recipients or not all(isinstance(x, str) for x in recipients):
            raise ChannelError('Explicit recipients must be a nonempty list')
        recipients = sorted(set(recipients))
        if any(peer not in self.participants or peer == participant for peer in recipients):
            raise ChannelError('Recipients must be registered peers other than the sender')
        if original and not set(recipients) <= default_recipients:
            raise ChannelError('A reply cannot expand access to the original conversation')
        payload = {'id': message_id, 'correlation_id': correlation_id, 'sender': participant,
                   'recipients': recipients, 'text': text, 'reply_to': reply_to}
        box = self._open()
        try:
            try:
                box.publish(self.owner, message_id, correlation_id, payload, recipients)
            except ValueError as error:
                raise ChannelError(str(error)) from None
            return self._get(box, participant, message_id)
        finally:
            box.close()

    def read(self, participant, *, after=0, limit=50, unread_only=False):
        self._participant(participant)
        if type(after) is not int or after < 0 or type(limit) is not int or not 1 <= limit <= 100 or type(unread_only) is not bool:
            raise ChannelError('after must be a nonnegative integer; limit 1..100; unread_only boolean')
        box = self._open()
        try:
            # Bind destination in SQL; a caller cannot enumerate another inbox.
            rows = box.db.execute('''SELECT r.event_id FROM reports r
                JOIN recipients d ON r.owner=d.owner AND r.event_id=d.event_id
                WHERE r.owner=? AND d.destination=? AND r.rowid>?
                AND (?=0 OR d.acknowledged=0) ORDER BY r.rowid LIMIT ?''',
                (self.owner, participant, after, int(unread_only), limit)).fetchall()
            return [self._get(box, participant, row[0]) for row in rows]
        finally:
            box.close()

    def acknowledge(self, participant, message_id, digest):
        self._participant(participant)
        box = self._open()
        try:
            message = self._get(box, participant, message_id)
            if participant not in message['recipients'] or digest != message['sha256']:
                raise ChannelError('Acknowledgement requires recipient identity and exact message hash')
            box.acknowledge(self.owner, participant, message_id, digest)
            return {'id': message_id, 'sha256': digest, 'participant': participant, 'state': 'read_acknowledged'}
        finally:
            box.close()
