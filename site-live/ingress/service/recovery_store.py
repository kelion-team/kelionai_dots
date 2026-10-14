"""Narrow transactional recovery of two completed phases; authorization defaults false."""
import hmac
import json
import math
import time
from store import Store, Conflict, canonical, digest, identity

AUTH_FIELDS={'schema_version','authorized','task_id','runtime_id','account_fingerprint_sha256',
    'discovery_sha256','previous_runtime_sha256','runtime_sha256','journal_sha256','task_input_sha256',
    'existing_completed_turns','additional_turn_requests','max_total_turn_requests','billing_mode',
    'read_only','network_access','human_authorization_ref','expires_at'}
ORIGINAL_PHASES={'kelion_selection','dots_assessment'}


def authorize(auth,task_id,runtime,saved,status,request,previous_runtime):
    if (not isinstance(auth,dict) or set(auth)!=AUTH_FIELDS or auth.get('authorized') is not True
            or auth.get('schema_version')!=1 or auth.get('billing_mode')!='included'
            or auth.get('read_only') is not True or auth.get('network_access') is not False
            or any(type(auth.get(key)) is not int or auth[key]!=value for key,value in
                   [('existing_completed_turns',2),('additional_turn_requests',2),('max_total_turn_requests',4)])
            or not isinstance(auth.get('human_authorization_ref'),str) or not auth['human_authorization_ref'].strip()
            or type(auth.get('expires_at')) not in (int,float) or not math.isfinite(auth['expires_at'])
            or auth['expires_at']<=time.time()):
        raise Conflict('Explicit private human authorization for total four included read-only turns required')
    expected={'task_id':task_id,'runtime_id':runtime['runtime_id'],
        'account_fingerprint_sha256':saved.get('account_fingerprint_sha256'),
        'discovery_sha256':digest(canonical(saved)),'previous_runtime_sha256':status['runtime_hash'],
        'runtime_sha256':digest(canonical(runtime)),'journal_sha256':digest(canonical(status['journal'])),
        'task_input_sha256':digest(request['task'])}
    if not expected['account_fingerprint_sha256'] or any(auth.get(key)!=value for key,value in expected.items()):
        raise Conflict('Recovery authorization scope/hash mismatch')
    if digest(canonical(previous_runtime))!=status['runtime_hash']:
        raise Conflict('Exact previous runtime manifest required for audit')
    # Renewal of local quota authorization expiry/evidence is explicitly audited.
    # Original manifest, account discovery, workspace, policy max3 stay immutable.
    def stable(value):
        result=json.loads(canonical(value));result.pop('verification_evidence',None)
        result.get('usage_authorization',{}).pop('expires_at',None)
        return result
    if stable(previous_runtime)!=stable(runtime):raise Conflict('Recovery cannot change original runtime/model manifest/policy')


def exact_failure(task,row):
    if (not task or not row or task['state']!='interrupted_requires_reconcile' or row['state']!='needs_reconcile'
            or any(task[key] is not None for key in ('decision','receipt','output','lease_hash'))):
        raise Conflict('Only failed assessment with no work/lease/output can resume')
    journal=json.loads(row['journal']);payload=json.loads(task['payload']);request=payload['request']
    if digest(canonical(request))!=task['input_hash']:raise Conflict('Original raw input binding changed')
    if payload['assessment'] is not None or 'role' in request:raise Conflict('Historical assessment must remain unprepared')
    phases=journal.get('phases',{})
    if set(phases)!=ORIGINAL_PHASES:raise Conflict('Unknown phase/work intent prevents recovery')
    if phases['kelion_selection'].get('state')!='readback_complete':raise Conflict('Selection was not read back')
    if (phases['dots_assessment'].get('state')!='needs_reconcile'
            or phases['dots_assessment'].get('failure_type')!='ValueError'):
        raise Conflict('Failure is not the exact original assessment input mismatch')
    ids=set()
    for phase in phases.values():
        if (not all(isinstance(phase.get(key),str) and phase[key] for key in ('thread_id','turn_id','output'))
                or phase.get('output_sha256')!=digest(phase['output'])
                or phase.get('configured_binding_readback') is not True
                or phase.get('read_only_no_network_policy_readback') is not True):
            raise Conflict('Exactly two completed actual readbacks required')
        ids.add(phase['turn_id'])
    if len(ids)!=2:raise Conflict('Two distinct completed turn identities required')
    ledger=journal.get('turn_request_intents',[])
    if ledger:
        if not isinstance(ledger,list) or len(ledger)!=2:raise Conflict('Historical intent ledger is not exactly two')
        for index,name in enumerate(('kelion_selection','dots_assessment'),1):
            entries=[entry for entry in ledger if entry.get('phase')==name]
            original=phases[name]
            if (len(entries)!=1 or entries[0].get('index')!=index
                    or entries[0].get('thread_id')!=original['thread_id']
                    or not original.get('turn_request_sha256')
                    or entries[0].get('turn_request_sha256')!=original['turn_request_sha256']):
                raise Conflict('Historical intent ledger has unknown acceptance/binding')
    def scan(value):
        if isinstance(value,dict):
            if value.get('state')=='turn_start_intent' and not value.get('turn_id'):
                raise Conflict('Unknown turn acceptance requires separate reconciliation')
            if value.get('turn_id') and value['turn_id'] not in ids:raise Conflict('Additional historical turn identity prevents recovery')
            if value.get('turn_request_sha256') and not value.get('turn_id'):
                # New durable ledger references an already completed phase by index.
                if not (value.get('phase') in phases and value.get('index') in (1,2)):
                    raise Conflict('Unknown accepted turn intent prevents recovery')
            for child in value.values():scan(child)
        elif isinstance(value,list):
            for child in value:scan(child)
    scan(journal)
    if 'client_turn_requests' in journal and journal['client_turn_requests']!=2:
        raise Conflict('Historical cumulative count is not exactly two')
    old=json.loads(phases['dots_assessment']['output'])
    if (not isinstance(old,dict) or set(old)!={'task_id','source_agent_id','task_input','difficulty','reason','risk_flags'}
            or old['task_id']!=request['task_id'] or not isinstance(old['task_input'],str)
            or not old['task_input'] or len(old['task_input'])>=len(request['task'])
            or not request['task'].startswith(old['task_input'])):
        raise Conflict('Original failed assessment is not a truncated exact input prefix')
    return request,journal


class RecoveryStore(Store):
    def inspect_recovery(self,task_id,runner_key,auth,saved,previous_runtime):
        identity(task_id,'task_id')
        with self.connect() as db:
            row=db.execute('SELECT * FROM runner_jobs WHERE task_id=?',(task_id,)).fetchone()
            task=db.execute('SELECT * FROM tasks WHERE task_id=?',(task_id,)).fetchone()
            if not row or not isinstance(runner_key,str) or not hmac.compare_digest(row['key_hash'],digest(runner_key)):
                raise Conflict('Existing private operator reservation key required')
            request,journal=exact_failure(task,row)
            status={'runtime_hash':row['runtime_hash'],'journal':journal}
            authorize(auth,task_id,self.runtime,saved,status,request,previous_runtime)
            return {'request':request,'journal':journal,'journal_sha256':digest(canonical(journal)),
                    'runtime_hash':row['runtime_hash']}

    def resume_transaction(self,task_id,runner_key,auth,saved,previous_runtime,fresh_readbacks):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM runner_jobs WHERE task_id=?',(task_id,)).fetchone()
            task=db.execute('SELECT * FROM tasks WHERE task_id=?',(task_id,)).fetchone()
            if not row or not hmac.compare_digest(row['key_hash'],digest(runner_key)):raise Conflict('Operator reservation mismatch')
            request,journal=exact_failure(task,row)
            authorize(auth,task_id,self.runtime,saved,{'runtime_hash':row['runtime_hash'],'journal':journal},request,previous_runtime)
            if db.execute("SELECT 1 FROM runner_jobs WHERE task_id!=? AND state IN ('running','needs_reconcile')",(task_id,)).fetchone():
                raise Conflict('Another worker requires reconciliation')
            if db.execute("SELECT 1 FROM tasks WHERE task_id!=? AND state IN ('leased','interrupted_requires_reconcile')",(task_id,)).fetchone():
                raise Conflict('Another native execution occupies worker')
            if set(fresh_readbacks)!=ORIGINAL_PHASES:raise Conflict('Fresh original readbacks required')
            for name,proof in fresh_readbacks.items():
                original=journal['phases'][name]
                if (proof.get('thread_id')!=original['thread_id'] or proof.get('turn_id')!=original['turn_id']
                        or proof.get('output_sha256')!=original['output_sha256'] or proof.get('completed') is not True
                        or proof.get('configured_binding')!=original['chosen']):
                    raise Conflict('Fresh original readback scope changed')
            # Archive exact bytes logically before changing runtime hash or opening phase.
            original_journal=json.loads(canonical(journal))
            journal['recovery_audit']={'authorization':auth,'authorization_sha256':digest(canonical(auth)),
                'original_journal':original_journal,'original_journal_sha256':digest(canonical(original_journal)),
                'runtime_before':previous_runtime,'runtime_before_sha256':row['runtime_hash'],
                'runtime_after':self.runtime,'runtime_after_sha256':digest(canonical(self.runtime)),
                'fresh_readbacks':fresh_readbacks,'created':time.time(),'max_total_turn_requests':4}
            journal['client_turn_requests']=2
            journal.setdefault('turn_request_intents',[])
            db.execute("UPDATE runner_jobs SET state='running',runtime_hash=?,journal=?,updated=? WHERE task_id=?",
                (digest(canonical(self.runtime)),canonical(journal),time.time(),task_id))
            db.execute("UPDATE tasks SET state='running_kelion',updated=? WHERE task_id=?",(time.time(),task_id))
            return {'task_id':task_id,'runner_key':runner_key,'payload':{'request':request},'client_turn_requests':2}

    def runner_checkpoint(self,task_id,runner_key,phase,data,**options):
        if phase in ORIGINAL_PHASES:raise Conflict('Original selection/failed assessment journal is immutable')
        return super().runner_checkpoint(task_id,runner_key,phase,data,**options)

    def runner_turn_intent(self,task_id,runner_key,phase,data,*,limit=3):
        if limit!=4 or phase not in ('dots_assessment_recovery','dots_work'):raise Conflict('Only two scoped recovery turns permitted')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM runner_jobs WHERE task_id=?',(task_id,)).fetchone()
            if (not row or row['state']!='running' or not hmac.compare_digest(row['key_hash'],digest(runner_key))
                    or row['runtime_hash']!=digest(canonical(self.runtime))):raise Conflict('Active exact recovery identity required')
            journal=json.loads(row['journal']);audit=journal.get('recovery_audit',{});auth=audit.get('authorization',{})
            if (auth.get('authorized') is not True or auth.get('max_total_turn_requests')!=4
                    or auth.get('expires_at',0)<=time.time() or audit.get('authorization_sha256')!=digest(canonical(auth))):
                raise Conflict('Scoped recovery authorization expired or invalid')
            count=journal.get('client_turn_requests')
            if type(count) is not int or not 2<=count<4:raise Conflict('Cumulative four-turn budget exhausted')
            if any(item['phase']==phase for item in journal['turn_request_intents']):raise Conflict('Recovery phase already has intent; no replay')
            index=count+1;data=dict(data,state='turn_start_intent',client_turn_request_index=index)
            journal['phases'][phase]=data;journal['client_turn_requests']=index
            journal['turn_request_intents'].append({'phase':phase,'index':index,'thread_id':data['thread_id'],
                'turn_request_sha256':data['turn_request_sha256']})
            db.execute('UPDATE runner_jobs SET journal=?,updated=? WHERE task_id=?',(canonical(journal),time.time(),task_id))
            return index
