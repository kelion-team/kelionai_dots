"""Isolated channel transport core. No network, shell, model or worker execution."""
from dataclasses import dataclass, asdict
import fcntl
import hashlib
import json
import re
import sqlite3
import time

CHANNELS = frozenset({'keliondots', 'brain', 'cloud'})
ID = re.compile(r'^[A-Za-z0-9_.:-]{1,160}$')


class Blocked(Exception):
    pass


class NotSent(Exception):
    """Adapter guarantees no remote effect occurred; only this error is retryable."""


@dataclass(frozen=True)
class Endpoint:
    name: str
    verified: bool = False
    enabled: bool = False
    evidence: str = ''
    principal: str = ''
    blocker: str = 'adapter_not_configured'


@dataclass(frozen=True)
class Message:
    id: str
    correlation_id: str
    source: str
    target: str
    text: str

    def encode(self):
        if not ID.fullmatch(self.id) or not ID.fullmatch(self.correlation_id):
            raise ValueError('invalid_id')
        if self.source not in CHANNELS or self.target not in CHANNELS or self.source == self.target:
            raise ValueError('invalid_route')
        if not isinstance(self.text, str) or not self.text or len(self.text.encode()) > 32000:
            raise ValueError('invalid_text')
        return json.dumps(asdict(self), sort_keys=True, ensure_ascii=False)


class Bridge:
    """One process owns a durable ledger. Adapters are trusted code, never config imports.

    submit/receive take a principal authenticated by the future host adapter, NOT an
    identity accepted from message text. Current CLI has no ingress or live adapters.
    """
    def __init__(self, path, endpoints, adapters=None, enabled=False, clock=time.time,
                 max_attempts=3, retry_seconds=5, result_timeout=300):
        if not 1 <= max_attempts <= 5 or retry_seconds < 1 or result_timeout < 1:
            raise ValueError('invalid_limits')
        self.endpoints = {e.name: e for e in endpoints}
        if set(self.endpoints) != CHANNELS or len(endpoints) != len(CHANNELS):
            raise ValueError('explicit_registry_required')
        self.adapters = adapters or {}
        self.enabled, self.clock = enabled, clock
        self.max_attempts, self.retry_seconds = max_attempts, retry_seconds
        self.result_timeout = result_timeout
        self.lock = open(str(path) + '.lock', 'a')
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.lock.close()
            raise Blocked('ledger_already_owned') from None
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('''CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY, envelope TEXT NOT NULL, sha TEXT NOT NULL,
            state TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
            due REAL NOT NULL, reason TEXT NOT NULL DEFAULT '', result TEXT)''')
        # A crash could have happened after delivery but before saving its receipt.
        self.db.execute("UPDATE messages SET state='uncertain', reason='restart_during_send' WHERE state='sending'")
        self.db.commit()

    def close(self):
        self.db.close()
        self.lock.close()

    def _endpoint(self, name, principal=None):
        e = self.endpoints.get(name)
        if e is None:
            raise Blocked('endpoint_not_registered')
        if not (e.verified and e.enabled and e.evidence and e.principal):
            raise Blocked(e.blocker or 'endpoint_not_verified')
        if principal is not None and principal != e.principal:
            raise Blocked('unauthorized_principal')
        return e

    def status(self, mid):
        row = self.db.execute('SELECT * FROM messages WHERE id=?', (mid,)).fetchone()
        if row is None:
            raise ValueError('unknown_message')
        return dict(row)

    def submit(self, message, principal):
        if not self.enabled:
            raise Blocked('bridge_disabled')
        if not isinstance(principal, str) or not principal.strip():
            raise Blocked('authenticated_principal_required')
        self._endpoint(message.source, principal)
        self._endpoint(message.target)
        if message.target not in self.adapters:
            raise Blocked('adapter_not_configured')
        body = message.encode()
        digest = hashlib.sha256(body.encode()).hexdigest()
        with self.db:
            old = self.db.execute('SELECT sha FROM messages WHERE id=?', (message.id,)).fetchone()
            if old and old['sha'] != digest:
                raise ValueError('id_content_conflict')
            self.db.execute('INSERT OR IGNORE INTO messages (id,envelope,sha,state,due) VALUES (?,?,?,?,?)',
                            (message.id, body, digest, 'pending', self.clock()))
        # Local acceptance is never downstream ACK or result.
        return {'kind': 'accepted_local', 'id': message.id, 'correlation_id': message.correlation_id,
                'state': self.status(message.id)['state']}

    def _state(self, mid, state, reason='', due=None, result=None):
        with self.db:
            self.db.execute('UPDATE messages SET state=?,reason=?,due=?,result=? WHERE id=?',
                            (state, reason, self.clock() if due is None else due, result, mid))

    def receive(self, mid, correlation_id, kind, principal, result=None):
        if not isinstance(principal, str) or not principal.strip():
            raise Blocked('authenticated_principal_required')
        row = self.status(mid)
        msg = json.loads(row['envelope'])
        self._endpoint(msg['target'], principal)
        if correlation_id != msg['correlation_id'] or kind not in ('ack', 'result'):
            raise ValueError('invalid_receipt')
        if row['state'] not in ('sending', 'uncertain', 'awaiting_result', 'completed'):
            raise ValueError('receipt_before_delivery')
        if kind == 'ack':
            if row['state'] == 'completed' or row['state'] == 'awaiting_result':
                return  # Duplicate ACK must not extend the result deadline.
            self._state(mid, 'awaiting_result', due=self.clock() + self.result_timeout)
            return
        if not isinstance(result, str) or not result or len(result.encode()) > 64000:
            raise ValueError('actual_result_required')
        if row['state'] == 'completed':
            if result != row['result']:
                raise ValueError('result_conflict')
            return
        self._state(mid, 'completed', result=result)

    def tick(self):
        if not self.enabled:
            return
        now = self.clock()
        for row in self.db.execute("SELECT * FROM messages WHERE state='awaiting_result' AND due<=?", (now,)).fetchall():
            self._state(row['id'], 'uncertain', 'result_timeout_no_resend')
        rows = self.db.execute("SELECT * FROM messages WHERE state='pending' AND due<=?", (now,)).fetchall()
        for row in rows:
            msg = Message(**json.loads(row['envelope']))
            try:
                self._endpoint(msg.source)
                self._endpoint(msg.target)
                adapter = self.adapters.get(msg.target)
                if adapter is None:
                    raise Blocked('adapter_not_configured')
            except Blocked as error:
                self._state(msg.id, 'blocked', str(error))
                continue
            # Commit BEFORE any possible side effect. Restart never blindly resends.
            with self.db:
                self.db.execute("UPDATE messages SET state='sending',attempts=attempts+1 WHERE id=?", (msg.id,))
            try:
                receipt = adapter.send(msg)
                if not isinstance(receipt, dict):
                    raise ValueError('invalid_receipt')
                self.receive(msg.id, receipt['correlation_id'], receipt['kind'],
                             receipt['principal'], receipt.get('result'))
            except NotSent:
                attempt = row['attempts'] + 1
                self._state(msg.id, 'failed' if attempt >= self.max_attempts else 'pending',
                            'not_sent_retry_exhausted' if attempt >= self.max_attempts else 'not_sent',
                            now + self.retry_seconds * (2 ** (attempt - 1)))
            except Exception:
                # Do not copy exception text: it may contain tokens or message content.
                self._state(msg.id, 'uncertain', 'delivery_outcome_unknown')

    def health(self):
        endpoints = {}
        for name in sorted(CHANNELS):
            try:
                self._endpoint(name)
                adapter = self.adapters.get(name)
                if adapter is None:
                    raise Blocked('adapter_not_configured')
                if adapter.health() is not True:
                    raise Blocked('adapter_unavailable')
                endpoints[name] = 'ready'
            except Blocked as error:
                endpoints[name] = str(error)
            except Exception:
                endpoints[name] = 'health_check_failed'
        counts = dict(self.db.execute('SELECT state,count(*) FROM messages GROUP BY state').fetchall())
        ready = self.enabled and all(x == 'ready' for x in endpoints.values())
        return {'liveness': 'ok', 'readiness': 'ready' if ready else 'blocked',
                'enabled': self.enabled, 'endpoints': endpoints, 'messages': counts}
