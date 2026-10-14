"""Finite LOCAL official AppServer executor. discover never starts a thread or turn."""
import argparse
import hashlib
import json
import math
import time
from pathlib import Path
from appserver_transport import AppServer, Protocol, ProtocolError, RPCRejected, Attention, discover, account_fingerprint
from store import Store, canonical, digest
from kelion_brain import _router


def private_json(path, data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    temporary.replace(path)


def discovery_scope(snapshot):
    return {key:snapshot.get(key) for key in ('runtime_id','adapter','account_type','plan_type','account_fingerprint_sha256',
                                            'catalog','protocol_sha256','executable_sha256')}


def check_eligibility(runtime, saved_discovery, current, *, chosen=None):
    """Positive backend included-usage permission is required; unknown is blocked."""
    if (runtime.get('adapter') != 'codex-app-server' or runtime.get('execution_surface') != 'codex'
            or runtime.get('runtime_id') != current.get('runtime_id') or not runtime.get('verification_evidence')):
        raise ProtocolError('Exact local AppServer runtime scope required')
    if runtime.get('discovery_sha256') != digest(canonical(saved_discovery)):
        raise ProtocolError('Authorized manifest is not bound to the saved official discovery')
    if discovery_scope(saved_discovery) != discovery_scope(current):
        raise ProtocolError('Current account/catalog/executable/protocol scope changed; no inference')
    authorization=runtime.get('usage_authorization') or {}
    if (authorization.get('included_usage_authorized') is not True or authorization.get('billing_mode') != 'included'
            or type(authorization.get('expires_at')) not in (int,float) or not math.isfinite(authorization['expires_at'])
            or authorization['expires_at'] <= time.time() or type(authorization.get('max_turns')) is not int
            or authorization['max_turns'] != 3):
        raise ProtocolError('Explicit finite existing-quota authorization required; no paid fallback')
    if (current.get('account_type') != 'chatgpt' or current.get('ordinary_usage_allowed') is not True
            or not current.get('account_fingerprint_sha256')):
        raise ProtocolError('Backend ordinary included usage is not positively verified for ChatGPT')
    catalog={item['model']:set(item['reasoning_levels']) for item in current.get('catalog',[])}
    models=_router._validated_models(runtime['manifest'])
    if not models:raise ProtocolError('No verified included local models in the authorized manifest')
    for item in models:
        if (item['surface'] != 'codex' or item['billing_mode'] != 'included'
                or not item['verified'] or not item['enabled'] or item.get('native_spawn_supported') is not True
                or item['id'] not in catalog or not set(item['reasoning_levels']).issubset(catalog[item['id']])):
            raise ProtocolError('Manifest model/effort eligibility does not match the official local catalog')
    if chosen and (chosen['model'] not in catalog or chosen['reasoning_effort'] not in catalog[chosen['model']]):
        raise ProtocolError('Exact Kelion model/effort not advertised in this runtime')


def configured_binding(thread, chosen):
    if (thread.get('model') != chosen['model'] or thread.get('reasoningEffort') != chosen['reasoning_effort']
            or thread.get('modelProvider') != 'openai'):
        raise ProtocolError('Effective configured model/effort/provider differs from Kelion selection')


def output_items(items):
    messages=[item for item in items if item.get('type')=='agentMessage']
    final=[item for item in messages if item.get('phase')=='final_answer']
    chosen=final or [item for item in messages if item.get('phase') is None]
    texts=[item.get('text') for item in chosen]
    if not texts or not all(isinstance(text,str) for text in texts):
        raise ProtocolError('Completed turn has no actual final output')
    output='\n'.join(texts)
    if not output.strip():raise ProtocolError('Completed turn has empty output')
    return output


def bind_assessment(request,role,text):
    """Future jobs: model evaluates; immutable parent supplies exact task provenance.

    Profile contract has five fields. Never repair an old assessment output or
    fabricate difficulty/reason/risks; this applies before Store.prepare only.
    """
    result=json.loads(text)
    if (not isinstance(result,dict) or set(result)!={'task_id','source_agent_id','difficulty','reason','risk_flags'}
            or result['task_id']!=request['task_id'] or result['source_agent_id']!=role['source_agent_id']
            or type(result['difficulty']) is not int or not 1<=result['difficulty']<=4
            or not isinstance(result['reason'],str) or not result['reason'].strip()
            or not isinstance(result['risk_flags'],list)
            or any(not isinstance(flag,str) or flag not in _router.HIGH_RISK for flag in result['risk_flags'])):
        raise ProtocolError('Invalid real task-bound DOTS assessment')
    assessment=dict(result,task_input=request['task'])
    provenance={'binding':'immutable_parent_input_not_model_echo','task_input_sha256':digest(request['task']),
                'model_assessment_output_sha256':digest(text),'task_id':request['task_id'],
                'source_agent_id':role['source_agent_id'],'historical_output_repaired':False}
    return assessment,provenance


class Runner:
    def __init__(self, store, client, saved_discovery, current, private_directory, *, turn_timeout=120):
        self.store=store;self.client=client;self.saved=saved_discovery;self.current=current
        self.private=Path(private_directory);self.timeout=turn_timeout
        if not 1 <= turn_timeout <= 300:raise ValueError('Turn timeout must be bounded to 1..300 seconds')
        self.phase=None;self.phase_data={};self.job=None;self.turn_count=0
        self.turn_limit=3

    def checkpoint(self, **fields):
        self.phase_data.update(fields)
        self.store.runner_checkpoint(self.job['task_id'],self.job['runner_key'],self.phase,self.phase_data)

    def gate(self, chosen):
        account=self.client.rpc('account/read',{'refreshToken':False}).get('account') or {}
        quota=self.client.rpc('account/rateLimits/read',{})
        current=dict(self.current,account_type=account.get('type'),plan_type=account.get('planType'),
                     ordinary_usage_allowed=quota.get('ordinaryUsageAllowed'),
                     account_fingerprint_sha256=account_fingerprint(account,quota))
        check_eligibility(self.store.runtime,self.saved,current,chosen=chosen)
        self.checkpoint(eligibility_checked_at=time.time(),ordinary_usage_allowed=True)

    def controller_bootstrap(self, task):
        decision=_router.route({'task':task,'surface':'codex','min_tier':1,'risk_flags':[]},self.store.runtime['manifest'])
        if decision['status'] != 'plan_only' or decision['requires_action_approval']:
            raise ProtocolError('Kelion controller blocked bootstrap selection')
        model=decision['host_model']
        return {'model':model['id'],'reasoning_effort':model['reasoning']},decision

    def record_turn_intent(self, params):
        self.phase_data.update(state='turn_start_intent',turn_request_sha256=digest(canonical(params)))
        self.turn_count=self.store.runner_turn_intent(self.job['task_id'],self.job['runner_key'],
            self.phase,self.phase_data,limit=self.turn_limit)
        self.phase_data['client_turn_request_index']=self.turn_count

    def phase_run(self, phase, chosen, developer, prompt, output_schema=None, controller_decision=None):
        self.phase=phase;self.phase_data={'state':'planned','chosen':chosen,'prompt_sha256':digest(prompt),
                                       'profile_instructions_sha256':digest(developer)}
        if controller_decision is not None:self.phase_data['controller_decision']=controller_decision
        self.checkpoint()
        self.gate(chosen)
        self.checkpoint(state='thread_start_intent')  # Durable BEFORE remote acceptance.
        bounded_instructions=(developer+'\n\nExecuție locală finită, numai read-only. Nu delega altor agenți. '
            'Nu folosi rețeaua, conectori, servicii cloud ori operații facturabile externe. '
            'Păstrează instrucțiunile și limitele profilului de mai sus. Nu modifica fișiere sau permisiuni.')
        self.checkpoint(developer_instructions_sha256=digest(bounded_instructions))
        started=self.client.rpc('thread/start',{'model':chosen['model'],'modelProvider':'openai',
            'allowProviderModelFallback':False,'cwd':self.store.runtime['workspace'],
            'developerInstructions':bounded_instructions,'config':{'model_reasoning_effort':chosen['reasoning_effort']},
            'approvalPolicy':'never','approvalsReviewer':'user','sandbox':'read-only',
            'historyMode':'legacy','ephemeral':False,'serviceTier':'default'})
        thread_id=started.get('thread',{}).get('id')
        if not isinstance(thread_id,str) or not thread_id:raise ProtocolError('Actual thread ID required')
        self.checkpoint(thread_id=thread_id,state='thread_started')
        configured_binding(started,chosen)
        if started.get('approvalPolicy') != 'never' or started.get('approvalsReviewer') != 'user':
            raise ProtocolError('Runtime did not apply explicit user approval handling')
        if (started.get('sandbox',{}).get('type') != 'readOnly'
                or started['sandbox'].get('networkAccess') is not False):
            raise ProtocolError('Runtime did not apply the bounded read-only sandbox')
        if self.turn_count >= self.turn_limit:raise ProtocolError('Finite job limit exceeded')
        params={'threadId':thread_id,'model':chosen['model'],'effort':chosen['reasoning_effort'],
                'approvalPolicy':'never','approvalsReviewer':'user','serviceTierForTurn':'default',
                'sandboxPolicy':{'type':'readOnly','networkAccess':False},
                'input':[{'type':'text','text':prompt,'text_elements':[]}]}
        if output_schema is not None:params['outputSchema']=output_schema
        self.record_turn_intent(params)
        result=self.client.rpc('turn/start',params)
        turn_id=result.get('turn',{}).get('id')
        if not isinstance(turn_id,str) or not turn_id:raise ProtocolError('Actual turn ID required')
        self.checkpoint(turn_id=turn_id,state='turn_started')
        end=time.monotonic()+self.timeout;items=[];completed=None
        while time.monotonic()<end:
            event=self.client.event(end-time.monotonic())
            data=event.get('params',{})
            if data.get('threadId') != thread_id:continue
            if event.get('method')=='item/completed' and data.get('turnId')==turn_id:
                item=data.get('item',{})
                if item.get('type')=='agentMessage':items.append(item)
            if event.get('method')=='turn/completed' and data.get('turn',{}).get('id')==turn_id:
                completed=data['turn'];break
        if not completed or completed.get('status') != 'completed':
            raise ProtocolError('Turn failed, interrupted, or did not complete within bound')
        event_output=output_items(completed.get('items') or items)
        resumed=self.client.rpc('thread/resume',{'threadId':thread_id,'excludeTurns':True})
        configured_binding(resumed,chosen)
        if (resumed.get('approvalPolicy') != 'never' or resumed.get('approvalsReviewer') != 'user'
                or resumed.get('sandbox',{}).get('type') != 'readOnly'
                or resumed['sandbox'].get('networkAccess') is not False):
            raise ProtocolError('Readback of bounded read-only/no-network policy failed')
        read=self.client.rpc('thread/read',{'threadId':thread_id,'includeTurns':True}).get('thread',{})
        if read.get('id') != thread_id:raise ProtocolError('Thread readback identity mismatch')
        configured_binding(read,chosen)  # Config provenance, not hidden per-turn inference telemetry.
        turns=[turn for turn in read.get('turns',[]) if turn.get('id')==turn_id]
        if len(turns)!=1 or turns[0].get('status') != 'completed':raise ProtocolError('Actual completed turn readback required')
        read_output=output_items(turns[0].get('items',[]))
        if read_output != event_output:raise ProtocolError('Actual output event/readback mismatch')
        self.checkpoint(state='readback_complete',output=read_output,output_sha256=digest(read_output),
                        configured_binding_readback=True,read_only_no_network_policy_readback=True)
        self.last_readback_turn=turns[0]
        if phase in ('dots_work','dots_work_repair'):
            from native_success_guard import TASK_ID, verify_official
            if self.job['task_id']==TASK_ID:
                # Keep actual failed output in the journal before rejecting it.
                self.checkpoint(command_items=[item for item in turns[0].get('items',[])
                                               if item.get('type')=='commandExecution'])
                proof,commands=verify_official(self.client,read,turns[0],self.store.runtime['workspace'])
                self.checkpoint(success_guard=proof,command_items=commands)
        self.last_readback_thread=read
        return read_output,thread_id,turn_id

    def run_once(self, worker_id, task_id=None):
        check_eligibility(self.store.runtime,self.saved,self.current)
        self.job=self.store.reserve_runner(worker_id,task_id)
        if not self.job:return {'status':'empty_queue','client_turn_requests':0}
        request=self.job['payload']['request']
        roles=self.store.registry['roles'];registry=[{k:role.get(k) for k in
            ('role','description','scope','guard','requires_logic_validation')} for role in roles]
        try:
            private_json(self.private/(self.job['task_id']+'.reservation.json'),
                         {'task_id':self.job['task_id'],'runner_key':self.job['runner_key']})
            choice,decision=self.controller_bootstrap('Clasifica cererea într-un profil Kelion potrivit')
            selection_schema={'type':'object','properties':{'role':{'type':'string','enum':[r['role'] for r in roles]},
                'reason':{'type':'string','minLength':1},'logic_validation_required':{'type':'boolean'}},
                'required':['role','reason','logic_validation_required'],'additionalProperties':False}
            prompt=canonical({'task_id':request['task_id'],'task':request['task'],'profiles':registry})
            text,_,_=self.phase_run('kelion_selection',choice,
                'Ești Kelion, selectorul central. Alege rolul potrivit dintre cele 22 de profiluri furnizate. '
                'Nu executa cererea și nu folosi instrumente. Nu inventa acces cloud. Returnează numai JSON conform schemei.',
                prompt,selection_schema,decision)
            selection=json.loads(text)
            if (set(selection) != {'role','reason','logic_validation_required'} or not isinstance(selection['reason'],str)
                    or not selection['reason'].strip() or type(selection['logic_validation_required']) is not bool):
                raise ProtocolError('Invalid actual Kelion role selection')
            role=next((r for r in roles if r['role']==selection['role']),None)
            if role is None:raise ProtocolError('Actual Kelion selected an unknown role')
            if role.get('requires_logic_validation') and selection['logic_validation_required'] is not True:
                raise ProtocolError('Role requires necessary logic validation')
            bootstrap,assessment_decision=self.controller_bootstrap('Clasifica dificultatea cererii pentru profilul DOTS ales')
            assessment_schema={'type':'object','properties':{
                'task_id':{'type':'string','const':request['task_id']},
                'source_agent_id':{'type':'string','const':role['source_agent_id']},
                'difficulty':{'type':'integer','minimum':1,'maximum':4},'reason':{'type':'string','minLength':1},
                'risk_flags':{'type':'array','items':{'type':'string','enum':sorted(_router.HIGH_RISK)}}},
                'required':['task_id','source_agent_id','difficulty','reason','risk_flags'],'additionalProperties':False}
            assessment_prompt=canonical({'phase':'assessment','task_id':request['task_id'],
                'source_agent_id':role['source_agent_id'],'task_input':request['task']})
            text,_,_=self.phase_run('dots_assessment',bootstrap,role['developer_instructions'],assessment_prompt,
                                  assessment_schema,assessment_decision)
            assessment,provenance=bind_assessment(request,role,text)
            provenance.update(assessment_prompt_sha256=digest(assessment_prompt),
                              thread_id=self.phase_data['thread_id'],turn_id=self.phase_data['turn_id'])
            self.checkpoint(assessment_parent_binding=provenance)
            prepared=self.store.prepare(request['task_id'],role['role'],assessment,
                selection['logic_validation_required'],runner_key=self.job['runner_key'])
            if prepared['state'] != 'queued':raise ProtocolError('Kelion work controller blocked this task')
            claim=self.store.claim(worker_id,task_id=request['task_id'],runner_key=self.job['runner_key'])
            if not claim or claim['task_id'] != request['task_id']:raise ProtocolError('Exact durable work lease required')
            private_json(self.private/(self.job['task_id']+'.work-lease.json'),
                         {'task_id':self.job['task_id'],'lease_token':claim['lease_token']})
            spawn=claim['decision']['spawn_request'];chosen={k:spawn[k] for k in ('model','reasoning_effort')}
            output,thread_id,turn_id=self.phase_run('dots_work',chosen,role['developer_instructions'],spawn['message'],
                                                   controller_decision=claim['decision'])
            receipt={'adapter':'codex-app-server','runtime_id':self.store.runtime['runtime_id'],
                'native_agent_id':thread_id,'turn_id':turn_id,'model':chosen['model'],
                'reasoning_effort':chosen['reasoning_effort'],'status':'completed','readback_output_sha256':digest(output)}
            result=self.store.complete(request['task_id'],claim['lease_token'],output,receipt)
            self.store.runner_checkpoint(request['task_id'],self.job['runner_key'],'finished',
                {'output_sha256':result['output_hash'],'turn_id':turn_id,'thread_id':thread_id,'client_turn_requests':self.turn_count},finished=True)
            return {'status':result['state'],'task_id':request['task_id'],'output_sha256':result['output_hash'],
                    'client_turn_requests':self.turn_count,'verified':False,'hosted':False}
        except Exception as exc:
            data=dict(self.phase_data,state='needs_reconcile',failure_type=type(exc).__name__)
            if isinstance(exc,RPCRejected):
                private_json(self.private/(request['task_id']+'.rpc-error.json'),exc.private_error)
            if isinstance(exc,Attention):
                # Sensitive request params stay only in private operator artifact, never API/log output.
                private_json(self.private/(request['task_id']+'.attention.json'),exc.request)
                data['attention_method']=exc.request.get('method')
            if data.get('thread_id') and data.get('turn_id'):
                try:self.client.send_request('turn/interrupt',{'threadId':data['thread_id'],'turnId':data['turn_id']})
                except Exception:pass  # No approval response is sent; interruption itself is not completion proof.
            self.store.runner_checkpoint(request['task_id'],self.job['runner_key'],self.phase or 'bootstrap',data,needs_reconcile=True)
            raise


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('discover','run-once'))
    parser.add_argument('--runtime-id',required=True)
    parser.add_argument('--protocol',type=Path,default=Path(__file__).parent/'private/appserver-protocol')
    parser.add_argument('--existing-codex-dir',type=Path)
    parser.add_argument('--runtime',type=Path)
    parser.add_argument('--database',type=Path)
    parser.add_argument('--discovery',type=Path,default=Path(__file__).parent/'private/appserver-discovery.json')
    parser.add_argument('--task-id')
    parser.add_argument('--worker-id',default='kelion-local-runner')
    parser.add_argument('--turn-timeout',type=int,default=120)
    args=parser.parse_args()
    private=Path(__file__).resolve().parent/'private'
    if not args.discovery.resolve().is_relative_to(private):parser.error('Discovery must stay under service/private')
    try:
        protocol=Protocol(args.protocol)
        with AppServer(protocol,private/'appserver-state',args.existing_codex_dir) as client:
            current=discover(client,args.runtime_id,protocol.hashes,client.executable)
            if args.action=='discover':
                private_json(args.discovery,current)
                print(json.dumps({'status':'discovered','runtime_id':args.runtime_id,'account_type':current['account_type'],
                    'ordinary_usage_allowed':current['ordinary_usage_allowed'],'catalog_count':len(current['catalog']),
                    'discovery_sha256':digest(canonical(current)),'client_turn_requests':0,'hosted':False}))
            else:
                if not args.runtime or not args.database:parser.error('run-once requires runtime and database')
                runtime=json.loads(args.runtime.read_text(encoding='utf-8'))
                saved=json.loads(args.discovery.read_text(encoding='utf-8'))
                workspace=Path(runtime.get('workspace',''))
                if not workspace.is_absolute() or not workspace.is_dir():
                    raise ProtocolError('Existing absolute authorized workspace required')
                store=Store(args.database,runtime)
                result=Runner(store,client,saved,current,private/'runner',turn_timeout=args.turn_timeout).run_once(args.worker_id,args.task_id)
                print(json.dumps(result))
    except (OSError,ValueError,ProtocolError,TimeoutError) as exc:
        if isinstance(exc,RPCRejected):private_json(private/'last-rpc-error.json',exc.private_error)
        print(json.dumps({'status':'blocked','failure_type':type(exc).__name__,'reason':str(exc),
                          'inference_success_claimed':False,'hosted':False}))
        raise SystemExit(2)


if __name__=='__main__':main()
