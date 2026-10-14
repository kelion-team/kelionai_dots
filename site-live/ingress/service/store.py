"""Durable single-worker native-parent handoff; no inference or shell execution."""
import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import sys
import time
from contextlib import contextmanager
from pathlib import Path

CORE = Path(__file__).resolve().parent / 'core'
sys.path.insert(0, str(CORE / 'orchestration'))
from native_dispatch import plan


class Conflict(ValueError):
    pass


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def identity(value, label):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{3,127}', value):
        raise ValueError('Invalid ' + label)
    return value


class Store:
    def __init__(self, database, runtime, *, lease_seconds=900):
        self.database = Path(database)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self.runtime = runtime
        self.lease_seconds = lease_seconds
        if runtime.get('adapter') not in ('native-parent','codex-app-server') or not runtime.get('runtime_id'):
            raise ValueError('Exact native runtime scope required')
        if runtime.get('execution_surface') not in ('codex', 'work'):
            raise ValueError('Native execution surface required')
        self.registry = json.loads((CORE / 'orchestration/native_roles.json').read_text(encoding='utf-8'))
        provenance = json.loads((CORE.parent / 'PROVENANCE.json').read_text(encoding='utf-8'))
        for source in provenance['files']:
            actual = hashlib.sha256((CORE.parent / source['path']).read_bytes()).hexdigest()
            if actual != source['sha256']:
                raise ValueError('Controller bundle integrity mismatch: ' + source['path'])
        with self.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY, input_hash TEXT NOT NULL, payload TEXT NOT NULL,
                state TEXT NOT NULL, decision TEXT, block_reason TEXT,
                created REAL NOT NULL, updated REAL NOT NULL, worker_id TEXT,
                lease_hash TEXT, lease_expires REAL, receipt TEXT, output TEXT,
                output_hash TEXT, failure TEXT)''')
            db.execute('''CREATE TABLE IF NOT EXISTS runner_jobs (
                task_id TEXT PRIMARY KEY, key_hash TEXT NOT NULL, runtime_hash TEXT NOT NULL,
                worker_id TEXT NOT NULL, state TEXT NOT NULL, journal TEXT NOT NULL,
                created REAL NOT NULL, updated REAL NOT NULL)''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.database, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA busy_timeout=10000')
        db.execute('PRAGMA synchronous=FULL')
        try:
            with db:
                yield db
        finally:
            db.close()

    def _view(self, row):
        if row is None:
            raise KeyError('Unknown task_id')
        out = dict(row)
        out.pop('lease_hash', None)
        for key in ('payload', 'decision', 'receipt'):
            out[key] = json.loads(out[key]) if out[key] else None
        provenance = None
        if out['output'] is not None:
            provenance = ('official_appserver_readback_local_runner' if out['receipt'].get('adapter') == 'codex-app-server'
                          else 'trusted_native_parent_attestation')
        out.update(result_retrieved=out['output'] is not None, verified=False, output_provenance=provenance)
        return out

    def intake(self, request):
        """Client sends raw text; only the trusted Kelion parent chooses a role."""
        if not isinstance(request, dict) or set(request) != {'task_id','task','origin','input_mode'}:
            raise ValueError('Raw intake requires task_id, task, origin and input_mode only')
        task_id = identity(request['task_id'], 'task_id')
        if request['origin'] not in ('chat','work','codex'):
            raise ValueError('Invalid origin')
        if request['input_mode'] not in ('text','voice_transcript'):
            raise ValueError('Already transcribed voice or text required')
        if not isinstance(request['task'], str) or not request['task'].strip() or len(request['task']) > 100000:
            raise ValueError('Invalid task text')
        fingerprint = digest(canonical(request))
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            existing = db.execute('SELECT * FROM tasks WHERE task_id=?', (task_id,)).fetchone()
            if existing:
                if existing['input_hash'] != fingerprint:
                    raise Conflict('task_id already binds different input')
                return self._view(existing)
            now = time.time()
            db.execute('INSERT INTO tasks (task_id,input_hash,payload,state,created,updated) VALUES (?,?,?,?,?,?)',
                       (task_id, fingerprint, canonical({'request':request,'assessment':None}), 'awaiting_kelion', now, now))
            return self._view(db.execute('SELECT * FROM tasks WHERE task_id=?', (task_id,)).fetchone())

    def awaiting(self):
        with self.connect() as db:
            row = db.execute("SELECT * FROM tasks WHERE state='awaiting_kelion' ORDER BY created,task_id LIMIT 1").fetchone()
            return self._view(row) if row else None

    def prepare(self, task_id, role, assessment, logic_validation_required=None, *, runner_key=None):
        """Internal Kelion-selected role + actual task-bound DOTS assessment."""
        identity(task_id, 'task_id')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self._runner_guard(db, task_id, runner_key)
            row = db.execute('SELECT * FROM tasks WHERE task_id=?', (task_id,)).fetchone()
            if not row:
                raise KeyError('Unknown task_id')
            payload = json.loads(row['payload'])
            request = {k:v for k,v in payload['request'].items() if k != 'role'}
            request['role'] = role
            if logic_validation_required is not None:
                if type(logic_validation_required) is not bool:
                    raise ValueError('Boolean logic validation flag required')
                request['logic_validation_required'] = logic_validation_required
            prepared = {'request':request,'assessment':assessment}
            if row['state'] not in ('awaiting_kelion','running_kelion'):
                if canonical(prepared) == row['payload']:
                    return self._view(row)
                raise Conflict('Prepared task binding is immutable')
            native_request = {k:v for k,v in request.items() if k not in ('origin','input_mode')}
            native_request['surface'] = self.runtime['execution_surface']
            decision, state, reason = self._plan(native_request, assessment)
            db.execute('UPDATE tasks SET payload=?,decision=?,state=?,block_reason=?,updated=? WHERE task_id=?',
                       (canonical(prepared),canonical(decision) if decision else None,state,reason,time.time(),task_id))
            return self._view(db.execute('SELECT * FROM tasks WHERE task_id=?', (task_id,)).fetchone())

    def _plan(self, native_request, assessment):
        try:
            decision = plan(native_request, assessment, self.runtime['manifest'], self.registry)
            if not self.runtime.get('verification_evidence'):
                raise ValueError('Runtime evidence required')
            decision['runtime_binding'] = {'runtime_id':self.runtime['runtime_id'],
                                           'runtime_sha256':digest(canonical(self.runtime))}
            return decision, 'queued', None
        except ValueError as exc:
            if str(exc) not in ('blocked_no_verified_included_model', 'Runtime evidence required'):
                raise
            return None, 'blocked_runtime', str(exc)

    def submit(self, payload):
        if not isinstance(payload, dict) or set(payload) != {'request', 'assessment'}:
            raise ValueError('Expected request and assessment only')
        request, assessment = payload['request'], payload['assessment']
        if not isinstance(request, dict):
            raise ValueError('Request must be an object')
        required = {'task_id', 'task', 'role', 'origin', 'input_mode'}
        allowed = required | {'logic_validation_required'}
        if not required.issubset(request) or not set(request).issubset(allowed):
            raise ValueError('Invalid request fields; runtime/model/command overrides are forbidden')
        task_id = identity(request['task_id'], 'task_id')
        if request['origin'] not in ('chat', 'work', 'codex'):
            raise ValueError('Invalid origin')
        if request['input_mode'] not in ('text', 'voice_transcript'):
            raise ValueError('Only text or an already transcribed voice request is accepted')
        if not isinstance(request['task'], str) or not request['task'].strip() or len(request['task']) > 100000:
            raise ValueError('Invalid task text')
        source = canonical(payload)
        fingerprint = digest(source)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            existing = db.execute('SELECT * FROM tasks WHERE task_id=?', (task_id,)).fetchone()
            if existing:
                if existing['input_hash'] != fingerprint:
                    raise Conflict('task_id already binds different input; read existing task for handoff')
                return self._view(existing)
            native_request = {k: v for k, v in request.items() if k not in ('origin', 'input_mode')}
            native_request['surface'] = self.runtime['execution_surface']
            decision, state, reason = self._plan(native_request, assessment)
            now = time.time()
            db.execute('INSERT INTO tasks (task_id,input_hash,payload,state,decision,block_reason,created,updated) '
                       'VALUES (?,?,?,?,?,?,?,?)', (task_id, fingerprint, source, state,
                       canonical(decision) if decision else None, reason, now, now))
            return self._view(db.execute('SELECT * FROM tasks WHERE task_id=?', (task_id,)).fetchone())

    def get(self, task_id):
        identity(task_id, 'task_id')
        with self.connect() as db:
            return self._view(db.execute('SELECT * FROM tasks WHERE task_id=?', (task_id,)).fetchone())

    def claim(self, worker_id, *, task_id=None, runner_key=None):
        identity(worker_id, 'worker_id')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self._runner_guard(db, task_id, runner_key)
            active = db.execute("SELECT * FROM tasks WHERE state IN ('leased','interrupted_requires_reconcile') LIMIT 1").fetchone()
            if active:
                if active['state'] == 'leased' and active['lease_expires'] <= time.time():
                    db.execute("UPDATE tasks SET state='interrupted_requires_reconcile',updated=? WHERE task_id=?",
                               (time.time(), active['task_id']))
                    db.commit()
                raise Conflict('Single worker occupied; reconcile the existing native execution before another claim')
            if task_id is None:
                row = db.execute("SELECT * FROM tasks WHERE state='queued' ORDER BY created,task_id LIMIT 1").fetchone()
            else:
                identity(task_id,'task_id')
                row = db.execute("SELECT * FROM tasks WHERE state='queued' AND task_id=?",(task_id,)).fetchone()
            if row is None:
                return None
            binding = json.loads(row['decision'])['runtime_binding']
            if binding['runtime_sha256'] != digest(canonical(self.runtime)):
                raise Conflict('Queued decision belongs to another runtime; no dispatch')
            token = secrets.token_urlsafe(32)
            now = time.time()
            db.execute("UPDATE tasks SET state='leased',worker_id=?,lease_hash=?,lease_expires=?,updated=? WHERE task_id=?",
                       (worker_id, digest(token), now + self.lease_seconds, now, row['task_id']))
            out = self._view(db.execute('SELECT * FROM tasks WHERE task_id=?', (row['task_id'],)).fetchone())
            out['lease_token'] = token
            out['runtime_id'] = self.runtime['runtime_id']
            out['instructions'] = 'Execute spawn_request once with the native tool. Do not replay a claim after restart. Read actual output before completion.'
            return out

    def complete(self, task_id, lease_token, output, receipt):
        identity(task_id, 'task_id')
        if not isinstance(output, str) or not output.strip() or len(output.encode('utf-8')) > 1048576:
            raise ValueError('Actual nonempty output required (maximum 1 MiB)')
        if not isinstance(lease_token, str) or not isinstance(receipt, dict):
            raise ValueError('Lease and native receipt required')
        required = {'adapter', 'runtime_id', 'native_agent_id', 'model', 'reasoning_effort', 'status'}
        if receipt.get('adapter') == 'codex-app-server':
            required |= {'turn_id','readback_output_sha256'}
            if (not isinstance(receipt.get('turn_id'),str) or not receipt['turn_id']
                    or receipt.get('readback_output_sha256') != digest(output)):
                raise ValueError('Exact app-server turn identity and output readback hash required')
        if set(receipt) != required or receipt['adapter'] != self.runtime['adapter'] or receipt['status'] != 'completed':
            raise ValueError('Completed receipt matching native runtime adapter required')
        if not isinstance(receipt['native_agent_id'], str) or not receipt['native_agent_id'].strip():
            raise ValueError('Actual native execution identity required')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM tasks WHERE task_id=?', (task_id,)).fetchone()
            if row is None:
                raise KeyError('Unknown task_id')
            if not row['lease_hash'] or not hmac.compare_digest(row['lease_hash'], digest(lease_token)):
                raise Conflict('Lease mismatch')
            stored_decision = json.loads(row['decision'])
            decision = stored_decision['spawn_request']
            if (stored_decision['runtime_binding']['runtime_sha256'] != digest(canonical(self.runtime))
                    or receipt['runtime_id'] != self.runtime['runtime_id'] or receipt['model'] != decision['model']
                    or receipt['reasoning_effort'] != decision['reasoning_effort']):
                raise Conflict('Receipt must match exact Kelion selection and runtime')
            encoded_receipt = canonical(receipt)
            if row['state'] == 'result_received':
                if row['output'] != output or row['receipt'] != encoded_receipt:
                    raise Conflict('Completed result is immutable')
                return self._view(row)
            if row['state'] not in ('leased', 'interrupted_requires_reconcile'):
                raise Conflict('Task has no active native execution')
            db.execute("UPDATE tasks SET state='result_received',receipt=?,output=?,output_hash=?,updated=? WHERE task_id=?",
                       (encoded_receipt, output, digest(output), time.time(), task_id))
            return self._view(db.execute('SELECT * FROM tasks WHERE task_id=?', (task_id,)).fetchone())

    def _runner_guard(self, db, task_id=None, runner_key=None):
        active=db.execute("SELECT * FROM runner_jobs WHERE state IN ('running','needs_reconcile') LIMIT 1").fetchone()
        if active:
            if (active['task_id'] != task_id or not isinstance(runner_key,str)
                    or not hmac.compare_digest(active['key_hash'],digest(runner_key))
                    or active['state'] != 'running'):
                raise Conflict('Local runner reservation requires reconciliation; no native replay or second worker')

    def reserve_runner(self, worker_id, task_id=None, *, worker_authorization=None):
        """Reserve the entire selector/assessment/work cycle before any inference intent."""
        identity(worker_id,'worker_id')
        if self.runtime['adapter'] != 'codex-app-server':
            raise ValueError('AppServer runtime scope required for local runner')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self._runner_guard(db)
            if db.execute("SELECT 1 FROM tasks WHERE state IN ('leased','interrupted_requires_reconcile') LIMIT 1").fetchone():
                raise Conflict('Existing native execution requires reconciliation')
            if task_id is None:
                row=db.execute("SELECT * FROM tasks WHERE state='awaiting_kelion' ORDER BY created,task_id LIMIT 1").fetchone()
            else:
                identity(task_id,'task_id')
                row=db.execute("SELECT * FROM tasks WHERE state='awaiting_kelion' AND task_id=?",(task_id,)).fetchone()
            if row is None:
                return None
            if worker_authorization is not None:
                self._worker_authorization(worker_authorization, row)
            if db.execute('SELECT 1 FROM runner_jobs WHERE task_id=?',(row['task_id'],)).fetchone():
                raise Conflict('This task already has a runner journal; no replay')
            key=secrets.token_urlsafe(32);now=time.time()
            journal={'phases':{}}
            if worker_authorization is not None:
                journal['worker_authorization']=worker_authorization
            db.execute('INSERT INTO runner_jobs VALUES (?,?,?,?,?,?,?,?)',
                       (row['task_id'],digest(key),digest(canonical(self.runtime)),worker_id,'running',canonical(journal),now,now))
            db.execute("UPDATE tasks SET state='running_kelion',updated=? WHERE task_id=?",(now,row['task_id']))
            result=self._view(db.execute('SELECT * FROM tasks WHERE task_id=?',(row['task_id'],)).fetchone())
            result['runner_key']=key
            return result

    def runner_checkpoint(self, task_id, runner_key, phase, data, *, needs_reconcile=False, finished=False):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM runner_jobs WHERE task_id=?',(task_id,)).fetchone()
            if (not row or not isinstance(runner_key,str) or not hmac.compare_digest(row['key_hash'],digest(runner_key))
                    or row['runtime_hash'] != digest(canonical(self.runtime))):
                raise Conflict('Runner journal identity/runtime mismatch')
            if row['state'] != 'running':
                raise Conflict('Runner journal is sealed; reconciliation required')
            journal=json.loads(row['journal'])
            if 'magentic' in journal:raise Conflict('Magentic requires its separate atomic contract')
            journal['phases'][phase]=data
            state='needs_reconcile' if needs_reconcile else 'completed' if finished else 'running'
            if finished:
                task=db.execute('SELECT state FROM tasks WHERE task_id=?',(task_id,)).fetchone()
                if not task or task['state'] != 'result_received':
                    raise Conflict('Runner completion requires durable actual output')
            db.execute('UPDATE runner_jobs SET state=?,journal=?,updated=? WHERE task_id=?',
                       (state,canonical(journal),time.time(),task_id))
            if needs_reconcile:
                db.execute("UPDATE tasks SET state='interrupted_requires_reconcile',updated=? WHERE task_id=? AND state NOT IN ('result_received','failed')",
                           (time.time(),task_id))

    def runner_status(self, task_id):
        identity(task_id,'task_id')
        with self.connect() as db:
            row=db.execute('SELECT * FROM runner_jobs WHERE task_id=?',(task_id,)).fetchone()
            if not row:
                raise KeyError('No runner journal')
            return {'task_id':task_id,'state':row['state'],'runtime_hash':row['runtime_hash'],
                    'journal':json.loads(row['journal'])}

    def runner_turn_intent(self, task_id, runner_key, phase, data, *, limit=3):
        """Persist cumulative client request count BEFORE turn/start; never replay."""
        if limit != 3:raise Conflict('Normal runner is limited to three client turn requests')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM runner_jobs WHERE task_id=?',(task_id,)).fetchone()
            if (not row or row['state']!='running' or not isinstance(runner_key,str)
                    or not hmac.compare_digest(row['key_hash'],digest(runner_key))
                    or row['runtime_hash']!=digest(canonical(self.runtime))):
                raise Conflict('Turn intent requires exact active runner identity')
            journal=json.loads(row['journal'])
            if 'magentic' in journal:raise Conflict('Magentic requires its separate cumulative budget contract')
            if 'worker_authorization' in journal:
                task=db.execute('SELECT * FROM tasks WHERE task_id=?',(task_id,)).fetchone()
                self._worker_authorization(journal['worker_authorization'], task)
            count=journal.get('client_turn_requests',0)
            if type(count) is not int or count<0 or count>=3:raise Conflict('Durable three-turn budget exhausted')
            if any(item['phase']==phase for item in journal.get('turn_request_intents',[])):
                raise Conflict('Phase already has a turn intent; no replay')
            index=count+1
            data=dict(data,state='turn_start_intent',client_turn_request_index=index)
            journal['phases'][phase]=data;journal['client_turn_requests']=index
            journal.setdefault('turn_request_intents',[]).append({'phase':phase,'index':index,
                'thread_id':data['thread_id'],'turn_request_sha256':data['turn_request_sha256']})
            db.execute('UPDATE runner_jobs SET journal=?,updated=? WHERE task_id=?',
                       (canonical(journal),time.time(),task_id))
            return index

    def _worker_authorization(self, authorization, task):
        """Bind HTTP worker ownership to one raw input and configured human manifest.

        This validates control-plane scope, not inference entitlement. The SIWC
        worker independently validates signed entitlement and grant evidence.
        Existing local runners do not use this additional HTTP-only contract.
        """
        import math
        required={'task_id','input_sha256','runtime_sha256','authorization_sha256','max_turns','expires_at'}
        configured=self.runtime.get('siwc_worker',{})
        if (not isinstance(authorization,dict) or set(authorization)!=required
                or configured.get('enabled') is not True or not self.runtime.get('verification_evidence')
                or authorization.get('task_id')!=task['task_id']
                or authorization.get('input_sha256')!=task['input_hash']
                or authorization.get('runtime_sha256')!=digest(canonical(self.runtime))
                or any(not isinstance(authorization.get(k),str) or not re.fullmatch(r'[a-f0-9]{64}',authorization[k])
                       for k in ('input_sha256','runtime_sha256','authorization_sha256'))
                or type(authorization.get('max_turns')) is not int or authorization['max_turns']!=3
                or type(authorization.get('expires_at')) not in (int,float)
                or not math.isfinite(authorization['expires_at']) or authorization['expires_at']<=time.time()
                or any(authorization.get(k)!=configured.get(k) for k in ('task_id','input_sha256','authorization_sha256','max_turns','expires_at'))):
            raise Conflict('Exact enabled one-task SIWC worker authorization required')

    def private_runner_status(self, task_id, runner_key):
        identity(task_id,'task_id')
        with self.connect() as db:
            row=db.execute('SELECT * FROM runner_jobs WHERE task_id=?',(task_id,)).fetchone()
            if (not row or not isinstance(runner_key,str)
                    or not hmac.compare_digest(row['key_hash'],digest(runner_key))
                    or row['runtime_hash']!=digest(canonical(self.runtime))):
                raise Conflict('Private runner journal requires exact reservation key')
            return {'task_id':task_id,'state':row['state'],'runtime_hash':row['runtime_hash'],
                    'journal':json.loads(row['journal'])}

    def magentic_worker(self, operation, data):
        from siwc.magentic_store import operate
        return operate(self, operation, data)

    def fail(self, task_id, lease_token, reason):
        identity(task_id, 'task_id')
        if not isinstance(lease_token, str) or not isinstance(reason, str) or not reason.strip() or len(reason) > 4000:
            raise ValueError('Lease and bounded failure reason required')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM tasks WHERE task_id=?', (task_id,)).fetchone()
            if not row:
                raise KeyError('Unknown task_id')
            if (row['state'] not in ('leased','interrupted_requires_reconcile') or not row['lease_hash']
                    or not hmac.compare_digest(row['lease_hash'], digest(lease_token))):
                raise Conflict('Active lease mismatch')
            db.execute("UPDATE tasks SET state='failed',failure=?,updated=? WHERE task_id=?", (reason, time.time(), task_id))
            return self._view(db.execute('SELECT * FROM tasks WHERE task_id=?', (task_id,)).fetchone())
