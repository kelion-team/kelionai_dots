"""Atomic HTTP contract for one finite Magentic job in the existing Store.

No framework import, provider call, alternate planner, or separate task database.
All mutable state uses the existing runner_jobs journal of the original raw task.
"""
import hmac
import json
import re
import secrets
import time

from store import Conflict, canonical, digest, identity

COMMIT = '2d58876e49d7569dafeac6b385a120514c1e6a12'
SHA = re.compile(r'[a-f0-9]{64}')


def gateway_policy(store):
    p=store.runtime.get('siwc_magentic',{})
    now=time.time()
    if (p.get('enabled') is not True or p.get('mode')!='owner_gateway' or not store.runtime.get('verification_evidence')
            or p.get('dedicated_owner_gateway_client') is not True
            or not isinstance(p.get('gateway_client_token_sha256'),str) or not SHA.fullmatch(p['gateway_client_token_sha256'])
            or p.get('frontend_receipt_client_token_sha256')!=p['gateway_client_token_sha256']
            or not isinstance(p.get('grant_fingerprint'),str) or not SHA.fullmatch(p['grant_fingerprint'])
            or not 0<p.get('activated_at',0)<=now<p.get('expires_at',0)<=p['activated_at']+3600
            or type(p.get('max_turns')) is not int or not 1<=p['max_turns']<=128
            or type(p.get('max_jobs')) is not int or not 1<=p['max_jobs']<=100
            or type(p.get('max_session_turns')) is not int or not p['max_turns']<=p['max_session_turns']<=512):
        raise Conflict('Current private dedicated owner gateway policy required')
    return p


def admit(store,data):
    if set(data)!={'worker_id','policy_sha256'}:raise ValueError('Exact admission fields required')
    identity(data['worker_id'],'worker_id')
    p=gateway_policy(store);ph=digest(canonical(p))
    if data['policy_sha256']!=ph:raise Conflict('Exact session policy required')
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE');store._runner_guard(db)
        if db.execute("SELECT 1 FROM tasks WHERE state IN ('leased','interrupted_requires_reconcile') LIMIT 1").fetchone():
            raise Conflict('Existing native execution requires reconciliation')
        previous=[json.loads(r['journal']).get('magentic',{}).get('authorization',{}) for r in db.execute('SELECT journal FROM runner_jobs')]
        previous=[a for a in previous if a.get('policy_sha256')==ph]
        if len(previous)>=p['max_jobs'] or sum(a['max_turns'] for a in previous)+p['max_turns']>p['max_session_turns']:
            return {'admission':None,'stop_reason':'finite_session_budget_exhausted'}
        task=None
        for candidate in db.execute("SELECT * FROM tasks WHERE state='awaiting_kelion' AND created>=? ORDER BY created,task_id",(p['activated_at'],)):
            marker=json.loads(candidate['payload']).get('private_ingress',{})
            if marker.get('authenticated_client_sha256')==p['gateway_client_token_sha256'] and marker.get('received_at',0)>=p['activated_at']:
                task=candidate;break
        if task is None:return {'admission':None,'stop_reason':'no_new_owner_gateway_task'}
        if db.execute('SELECT 1 FROM runner_jobs WHERE task_id=?',(task['task_id'],)).fetchone():raise Conflict('Existing task journal cannot replay')
        raw=json.loads(task['payload'])['request'];template=p.get('framework_template',{})
        if not isinstance(template,dict) or any(k in template for k in ('task_id','objective','roles','framework_commit')):raise Conflict('Task-free original framework template required')
        config={**template,'enabled':True,'mode':'native_host','task_id':task['task_id'],'objective':raw['task']}
        roles=[next((r for r in store.registry['roles'] if r['name']==name),None) for name in config.get('participants',[])]
        if not roles or any(r is None for r in roles) or len({r['name'] for r in roles})!=len(roles):raise Conflict('Canonical framework participants required')
        bound={**config,'roles':roles,'framework_commit':COMMIT}
        scope={k:v for k,v in store.runtime.items() if k not in ('siwc_worker','siwc_magentic')}
        a={'kind':'operator_bounded_siwc_job','mode':'magentic','task_id':task['task_id'],'input_sha256':task['input_hash'],'runtime_scope_sha256':digest(canonical(scope)),
           'grant_fingerprint':p['grant_fingerprint'],'max_turns':p['max_turns'],'framework_config_sha256':digest(canonical(bound)),'allowance_authorized':True,
           'billing_mode':'included','read_only':True,'network_access':False,'no_new_spend':True,'new_task_only':True,'expires_at':p['expires_at'],'policy_sha256':ph}
        auth={k:a[k] for k in ('task_id','input_sha256','max_turns','framework_config_sha256','expires_at','policy_sha256')}
        auth.update(runtime_sha256=digest(canonical(store.runtime)),authorization_sha256=digest(canonical(a)))
        key=secrets.token_urlsafe(32);now=time.time()
        journal={'magentic':{'authorization':auth,'requests':{},'operations':[]},'phases':{},'client_turn_requests':0}
        db.execute('INSERT INTO runner_jobs VALUES (?,?,?,?,?,?,?,?)',(task['task_id'],digest(key),digest(canonical(store.runtime)),data['worker_id'],'running',canonical(journal),now,now))
        db.execute("UPDATE tasks SET state='running_kelion',worker_id=?,updated=? WHERE task_id=?",(data['worker_id'],now,task['task_id']))
        reservation=store._view(db.execute('SELECT * FROM tasks WHERE task_id=?',(task['task_id'],)).fetchone());reservation['runner_key']=key
        return {'admission':{'reservation':reservation,'authorization':a,'framework_config':config,'runtime_sha256':digest(canonical(store.runtime))}}


def authorization(store, value, task):
    keys = {'task_id','input_sha256','runtime_sha256','authorization_sha256','framework_config_sha256','max_turns','expires_at'}
    cfg = store.runtime.get('siwc_magentic', {})
    if cfg.get('mode')=='owner_gateway':
        p=gateway_policy(store)
        if (set(value)!=keys|{'policy_sha256'} or value['policy_sha256']!=digest(canonical(p))
                or value['task_id']!=task['task_id'] or value['input_sha256']!=task['input_hash']
                or value['runtime_sha256']!=digest(canonical(store.runtime)) or value['max_turns']!=p['max_turns'] or value['expires_at']!=p['expires_at']):
            raise Conflict('Admitted owner gateway task binding required')
        return
    if (not isinstance(value, dict) or set(value) != keys or cfg.get('enabled') is not True
            or not store.runtime.get('verification_evidence')
            or value['task_id'] != task['task_id'] or value['input_sha256'] != task['input_hash']
            or value['runtime_sha256'] != digest(canonical(store.runtime))
            or type(value['max_turns']) is not int or not 1 <= value['max_turns'] <= 128
            or type(value['expires_at']) not in (int, float) or not time.time() < value['expires_at'] < float('inf')
            or any(not isinstance(value[k], str) or not SHA.fullmatch(value[k]) for k in ('input_sha256','runtime_sha256','authorization_sha256','framework_config_sha256'))
            or any(value[k] != cfg.get(k) for k in keys - {'runtime_sha256'})):
        raise Conflict('Exact enabled finite Magentic job binding required')


def request_payload(request):
    return {k:v for k,v in request.items() if k not in ('request_id','input_sha256','dispatch_state')}


def operate(store, operation, data):
    if operation=='admit':return admit(store,data)
    identity(data.get('task_id'), 'task_id')
    task_id = data['task_id']
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        task = db.execute('SELECT * FROM tasks WHERE task_id=?', (task_id,)).fetchone()
        if not task:
            raise KeyError('Unknown task_id')
        if operation == 'reserve':
            if store.runtime.get('siwc_magentic',{}).get('mode')=='owner_gateway':raise Conflict('Owner gateway requires atomic admission')
            if set(data) != {'task_id','worker_id','authorization'}:
                raise ValueError('Exact Magentic reservation fields required')
            identity(data['worker_id'], 'worker_id')
            authorization(store, data['authorization'], task)
            store._runner_guard(db)
            if task['state'] != 'awaiting_kelion' or db.execute('SELECT 1 FROM runner_jobs WHERE task_id=?',(task_id,)).fetchone():
                raise Conflict('New raw task required; no replay or journal reset')
            if db.execute("SELECT 1 FROM tasks WHERE state IN ('leased','interrupted_requires_reconcile') LIMIT 1").fetchone():
                raise Conflict('Existing native execution requires reconciliation')
            key = secrets.token_urlsafe(32); now = time.time()
            journal = {'magentic': {'authorization':data['authorization'],'requests':{},'operations':[]}, 'phases':{}, 'client_turn_requests':0}
            db.execute('INSERT INTO runner_jobs VALUES (?,?,?,?,?,?,?,?)', (task_id,digest(key),digest(canonical(store.runtime)),data['worker_id'],'running',canonical(journal),now,now))
            db.execute("UPDATE tasks SET state='running_kelion',worker_id=?,updated=? WHERE task_id=?",(data['worker_id'],now,task_id))
            out = store._view(db.execute('SELECT * FROM tasks WHERE task_id=?',(task_id,)).fetchone()); out['runner_key']=key
            return {'reservation':out}
        row = db.execute('SELECT * FROM runner_jobs WHERE task_id=?',(task_id,)).fetchone()
        if (not row or not isinstance(data.get('runner_key'),str) or not hmac.compare_digest(row['key_hash'],digest(data['runner_key']))
                or row['runtime_hash'] != digest(canonical(store.runtime)) or row['worker_id'] != data.get('worker_id')):
            raise Conflict('Exact Magentic task/key/worker/runtime required')
        journal = json.loads(row['journal']); m = journal.get('magentic')
        if not m:
            raise Conflict('Magentic journal required; normal runner is separate')
        base = {'task_id','runner_key','worker_id'}
        if operation == 'status' and set(data) == base:
            return {'task_id':task_id,'state':row['state'],'journal':journal}
        if row['state'] != 'running':
            raise Conflict('Magentic journal sealed; reconciliation required')
        authorization(store,m['authorization'],task)
        state = 'running'; out = {'recorded':True}
        if operation == 'request' and set(data) == base | {'request'}:
            r = data['request']; payload = request_payload(r); rid = r.get('request_id')
            if (not isinstance(rid,str) or not SHA.fullmatch(rid) or rid != r.get('input_sha256') or rid != digest(canonical(payload))
                    or r.get('mode') != 'native_host' or r.get('task_id') != task_id or r.get('framework_commit') != COMMIT
                    or r.get('config_sha256') != m['authorization']['framework_config_sha256'] or r.get('dispatch_state') != 'awaiting_native_host'
                    or r.get('kind') not in ('manager_reasoning','participant_execution')):
                raise Conflict('Original pending framework request binding required')
            if r['kind'] == 'participant_execution':
                role = next((x for x in store.registry['roles'] if x['name']==r['role']),None)
                if role is None or role != r.get('native_profile'):
                    raise Conflict('Frozen canonical participant profile required')
            elif r.get('role') != 'kelion_manager':
                raise Conflict('Original manager role required')
            if rid in m['requests']:
                raise Conflict('Request already registered; no automatic replay')
            if len(m['requests']) >= m['authorization']['max_turns']:
                raise Conflict('Finite job request bound exhausted')
            m['requests'][rid]={'request':r,'readback':None}
        elif operation in ('checkpoint','turn-intent') and set(data) == base | {'request_id','phase','data'}:
            rid, phase, update = data['request_id'],data['phase'],data['data']
            r = m['requests'].get(rid)
            if not r or phase not in ('manager','assessment','work') or not isinstance(update,dict):
                raise Conflict('Known request and bounded phase required')
            if (r['request']['kind']=='manager_reasoning') != (phase=='manager'):
                raise Conflict('Phase differs from original framework actor')
            key = 'magentic/'+rid+'/'+phase
            if operation == 'turn-intent':
                if (journal['client_turn_requests'] >= m['authorization']['max_turns']
                        or any(x['phase']==key for x in journal.get('turn_request_intents',[]))):
                    raise Conflict('Finite cumulative budget exhausted or phase already consumed')
                if not isinstance(update.get('thread_id'),str) or not update['thread_id'] or not SHA.fullmatch(update.get('turn_request_sha256','')):
                    raise ValueError('Durable thread and exact turn hash required')
                journal['client_turn_requests'] += 1
                journal.setdefault('turn_request_intents',[]).append({'phase':key,'index':journal['client_turn_requests'],'thread_id':update['thread_id'],'turn_request_sha256':update['turn_request_sha256']})
                update = dict(update,state='turn_start_intent',client_turn_request_index=journal['client_turn_requests'])
                out={'index':journal['client_turn_requests']}
            prior = journal['phases'].get(key,{})
            if prior.get('state')=='readback_complete':
                raise Conflict('Completed phase proof is immutable')
            if update.get('state')=='readback_complete':
                if (not any(x['phase']==key for x in journal.get('turn_request_intents',[]))
                        or update.get('thread_id')!=prior.get('thread_id') or update.get('turn_id')!=prior.get('turn_id')
                        or not isinstance(update.get('output'),str) or digest(update['output'])!=update.get('output_sha256')
                        or update.get('configured_binding_source')!='thread/start + thread/resume + thread/read'
                        or update.get('per_turn_model_attestation') is not False):
                    raise Conflict('Exact completed turn readback required')
            journal['phases'][key]=update
        elif operation == 'readback' and set(data) == base | {'request_id','receipt','response'}:
            rid=data['request_id']; r=m['requests'].get(rid)
            if not r or r['readback'] is not None:
                raise Conflict('Known unfinished request required')
            phase='manager' if r['request']['kind']=='manager_reasoning' else 'work'
            proof=journal['phases'].get('magentic/'+rid+'/'+phase,{})
            receipt,response=data['receipt'],data['response']
            if (proof.get('state')!='readback_complete' or proof.get('prompt_sha256')!=rid
                    or response.get('request_id')!=rid or response.get('input_sha256')!=rid or response.get('task_id')!=task_id
                    or response.get('text')!=proof['output'] or response.get('output_sha256')!=proof['output_sha256']
                    or response.get('host_run_id')!=proof['thread_id'] or response.get('execution_kind')!='native_host'
                    or receipt.get('request_id')!=rid or receipt.get('role')!=r['request']['role']
                    or receipt.get('host_run_id')!=proof['thread_id'] or receipt.get('dispatch_ref')!=proof['turn_id']
                    or receipt.get('model')!=proof['configured_model'] or receipt.get('reasoning_effort')!=proof['configured_effort']):
                raise Conflict('Framework readback must match actual request-bound SIWC proof')
            r['readback']={'receipt':receipt,'response':response}
        elif operation == 'operation' and set(data) == base | {'operation','result_sha256'}:
            if data['operation'] not in ('init','advance','pending','status') or not SHA.fullmatch(data['result_sha256']):
                raise ValueError('Finite framework operation required')
            m['operations'].append({'operation':data['operation'],'result_sha256':data['result_sha256']})
            if len(m['operations'])>4*m['authorization']['max_turns']+8:
                raise Conflict('Finite framework operation bound exhausted')
        elif operation == 'fail' and set(data)==base | {'reason'}:
            state='needs_reconcile';m['failure']=str(data['reason'])[:200]
            db.execute("UPDATE tasks SET state='interrupted_requires_reconcile',updated=? WHERE task_id=?",(time.time(),task_id))
        elif operation == 'complete' and set(data)==base | {'final','status_readback'}:
            final,status=data['final'],data['status_readback']
            if (final.get('status')!='framework_completed_requires_independent_verification' or final.get('mode')!='native_host'
                    or final.get('task_id')!=task_id or final.get('output_sha256')!=digest(final.get('text','')) or not final.get('text')
                    or status.get('final')!=final or status.get('pending_count')!=0 or status.get('status')!=final['status']
                    or not m['requests'] or any(r['readback'] is None for r in m['requests'].values())):
                raise Conflict('Actual framework final and all request readbacks required')
            m['final']=final; state='completed'
            receipt={'adapter':'codex-app-server','execution_kind':'magentic_native_host','framework_commit':COMMIT,'runtime_id':store.runtime['runtime_id'],'framework_readback':True,'model_execution_attested':False,'actual_monetary_cost':None}
            db.execute("UPDATE tasks SET state='result_received',receipt=?,output=?,output_hash=?,updated=? WHERE task_id=?",(canonical(receipt),final['text'],final['output_sha256'],time.time(),task_id))
            out=store._view(db.execute('SELECT * FROM tasks WHERE task_id=?',(task_id,)).fetchone())
        else:
            raise ValueError('Exact Magentic operation fields required')
        db.execute('UPDATE runner_jobs SET state=?,journal=?,updated=? WHERE task_id=?',(state,canonical(journal),time.time(),task_id))
        return out
