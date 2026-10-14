"""Explicit LOCAL recovery. False by default; total4 requires separate human-scoped authorization."""
import argparse
import hmac
import json
import time
from pathlib import Path
from appserver_transport import AppServer, Protocol, ProtocolError, RPCRejected, Attention, discover
from local_runner import Runner, check_eligibility, configured_binding, output_items, bind_assessment, private_json
from recovery_store import RecoveryStore, exact_failure, ORIGINAL_PHASES
from store import Conflict, canonical, digest
from kelion_brain import _router


def false_template(store,task_id,runner_key,saved,previous_runtime):
    with store.connect() as db:
        row=db.execute('SELECT * FROM runner_jobs WHERE task_id=?',(task_id,)).fetchone()
        task=db.execute('SELECT * FROM tasks WHERE task_id=?',(task_id,)).fetchone()
        if not row or not hmac.compare_digest(row['key_hash'],digest(runner_key)):
            raise Conflict('Existing private operator reservation key required')
        request,journal=exact_failure(task,row)
        if digest(canonical(previous_runtime))!=row['runtime_hash']:raise Conflict('Previous runtime audit mismatch')
        return {'schema_version':1,'authorized':False,'task_id':task_id,'runtime_id':store.runtime['runtime_id'],
            'account_fingerprint_sha256':saved.get('account_fingerprint_sha256'),'discovery_sha256':digest(canonical(saved)),
            'previous_runtime_sha256':row['runtime_hash'],'runtime_sha256':digest(canonical(store.runtime)),
            'journal_sha256':digest(canonical(journal)),'task_input_sha256':digest(request['task']),
            'existing_completed_turns':2,'additional_turn_requests':2,'max_total_turn_requests':4,
            'billing_mode':'included','read_only':True,'network_access':False,'human_authorization_ref':None,'expires_at':0}


class RecoveryRunner(Runner):
    def __init__(self,*args,authorization,previous_runtime,operator_key,**kwargs):
        super().__init__(*args,**kwargs)
        self.authorization=authorization;self.previous_runtime=previous_runtime;self.operator_key=operator_key
        # Limit changes only after the transactional authorization below succeeds.

    def gate(self,chosen):
        if self.authorization.get('authorized') is not True or self.authorization.get('expires_at',0)<=time.time():
            raise Conflict('Recovery human authorization is absent/expired')
        return super().gate(chosen)

    def fresh_original(self,inspection):
        request=inspection['request']
        registry=[{key:role.get(key) for key in ('role','description','scope','guard','requires_logic_validation')}
                  for role in self.store.registry['roles']]
        expected_selection_prompt=canonical({'task_id':request['task_id'],'task':request['task'],'profiles':registry})
        if inspection['journal']['phases']['kelion_selection'].get('prompt_sha256')!=digest(expected_selection_prompt):
            raise ProtocolError('Original selection prompt is not bound to immutable Store input')
        proofs={};outputs={}
        for name in ('kelion_selection','dots_assessment'):
            original=inspection['journal']['phases'][name]
            check_eligibility(self.store.runtime,self.saved,self.current,chosen=original['chosen'])
            thread=self.client.rpc('thread/read',{'threadId':original['thread_id'],'includeTurns':True}).get('thread',{})
            if thread.get('id')!=original['thread_id']:raise ProtocolError('Fresh historical thread identity mismatch')
            configured_binding(thread,original['chosen'])
            turns=thread.get('turns',[])
            if len(turns)!=1 or turns[0].get('id')!=original['turn_id'] or turns[0].get('status')!='completed':
                raise ProtocolError('Historical acceptance/completion is not exactly one known turn')
            text=output_items(turns[0].get('items',[]))
            if digest(text)!=original['output_sha256'] or text!=original['output']:
                raise ProtocolError('Fresh historical output hash differs; no recovery')
            proofs[name]={'thread_id':thread['id'],'turn_id':turns[0]['id'],'output_sha256':digest(text),
                          'completed':True,'configured_binding':original['chosen']}
            outputs[name]=text
        selection=json.loads(outputs['kelion_selection'])
        if (not isinstance(selection,dict) or set(selection)!={'role','reason','logic_validation_required'}
                or not isinstance(selection['reason'],str) or not selection['reason'].strip()
                or type(selection['logic_validation_required']) is not bool):
            raise ProtocolError('Actual original selection is invalid')
        role=next((item for item in self.store.registry['roles'] if item['role']==selection['role']),None)
        if not role or (role.get('requires_logic_validation') and selection['logic_validation_required'] is not True):
            raise ProtocolError('Actual selection role/logic guard invalid')
        old=json.loads(outputs['dots_assessment'])
        if old['source_agent_id']!=role['source_agent_id']:raise ProtocolError('Original target profile differs')
        expected_prompt=canonical({'phase':'assessment','task_id':request['task_id'],
                                  'source_agent_id':role['source_agent_id'],'task_input':request['task']})
        original=inspection['journal']['phases']['dots_assessment']
        if (original.get('prompt_sha256')!=digest(expected_prompt)
                or original.get('profile_instructions_sha256')!=digest(role['developer_instructions'])):
            raise ProtocolError('Original assessment prompt/profile provenance differs')
        # Validate historical evaluation type/scope only; NEVER feed it to prepare.
        bind_assessment(inspection['request'],role,canonical({key:value for key,value in old.items() if key!='task_input'}))
        return selection,role,proofs

    def resume(self,task_id):
        inspection=self.store.inspect_recovery(task_id,self.operator_key,self.authorization,self.saved,self.previous_runtime)
        check_eligibility(self.store.runtime,self.saved,self.current)
        selection,role,proofs=self.fresh_original(inspection)
        self.job=self.store.resume_transaction(task_id,self.operator_key,self.authorization,self.saved,self.previous_runtime,proofs)
        self.turn_count=2;self.turn_limit=4
        request=self.job['payload']['request']
        self.phase='recovery_prepared';self.phase_data={'state':'prepared','existing_completed_turn_requests':2}
        try:
            self.checkpoint()
            chosen,decision=self.controller_bootstrap('Clasifica dificultatea cererii pentru profilul DOTS ales')
            schema={'type':'object','properties':{'task_id':{'type':'string','const':task_id},
                'source_agent_id':{'type':'string','const':role['source_agent_id']},
                'difficulty':{'type':'integer','minimum':1,'maximum':4},'reason':{'type':'string','minLength':1},
                'risk_flags':{'type':'array','items':{'type':'string','enum':sorted(_router.HIGH_RISK)}}},
                'required':['task_id','source_agent_id','difficulty','reason','risk_flags'],'additionalProperties':False}
            prompt=canonical({'phase':'assessment','task_id':task_id,'source_agent_id':role['source_agent_id'],
                              'task_input':request['task']})
            text,thread_id,turn_id=self.phase_run('dots_assessment_recovery',chosen,role['developer_instructions'],prompt,schema,decision)
            assessment,binding=bind_assessment(request,role,text)
            binding.update(assessment_prompt_sha256=digest(prompt),thread_id=thread_id,turn_id=turn_id)
            self.checkpoint(assessment_parent_binding=binding)
            prepared=self.store.prepare(task_id,role['role'],assessment,selection['logic_validation_required'],runner_key=self.operator_key)
            if prepared['state']!='queued':raise ProtocolError('Original work controller blocked recovery')
            claim=self.store.claim('kelion-manual-recovery',task_id=task_id,runner_key=self.operator_key)
            if not claim or claim['task_id']!=task_id:raise ProtocolError('Exact recovery work lease required')
            private_json(self.private/(task_id+'.recovery-work-lease.json'),{'task_id':task_id,'lease_token':claim['lease_token']})
            spawn=claim['decision']['spawn_request'];chosen={key:spawn[key] for key in ('model','reasoning_effort')}
            output,thread_id,turn_id=self.phase_run('dots_work',chosen,role['developer_instructions'],spawn['message'],
                                                  controller_decision=claim['decision'])
            receipt={'adapter':'codex-app-server','runtime_id':self.store.runtime['runtime_id'],'native_agent_id':thread_id,
                'turn_id':turn_id,'model':chosen['model'],'reasoning_effort':chosen['reasoning_effort'],'status':'completed',
                'readback_output_sha256':digest(output)}
            result=self.store.complete(task_id,claim['lease_token'],output,receipt)
            self.store.runner_checkpoint(task_id,self.operator_key,'finished',
                {'output_sha256':result['output_hash'],'turn_id':turn_id,'thread_id':thread_id,
                 'client_turn_requests':self.turn_count,'recovery':True},finished=True)
            return {'status':result['state'],'task_id':task_id,'cumulative_client_turn_requests':self.turn_count,
                    'new_client_turn_requests':2,'output_sha256':result['output_hash'],'verified':False,'hosted':False}
        except Exception as exc:
            data=dict(self.phase_data,state='needs_reconcile',failure_type=type(exc).__name__)
            if isinstance(exc,RPCRejected):private_json(self.private/(task_id+'.recovery-rpc-error.json'),exc.private_error)
            if isinstance(exc,Attention):private_json(self.private/(task_id+'.recovery-attention.json'),exc.request)
            if data.get('thread_id') and data.get('turn_id'):
                try:self.client.send_request('turn/interrupt',{'threadId':data['thread_id'],'turnId':data['turn_id']})
                except Exception:pass
            self.store.runner_checkpoint(task_id,self.operator_key,self.phase,data,needs_reconcile=True)
            raise


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('prepare','check','resume'))
    for name in ('runtime','previous-runtime','database','discovery','authorization','reservation'):
        parser.add_argument('--'+name,required=name!='previous-runtime',type=Path)
    parser.add_argument('--task-id',required=True)
    parser.add_argument('--existing-codex-dir',type=Path)
    parser.add_argument('--turn-timeout',type=int,default=120)
    args=parser.parse_args()
    private=Path(__file__).resolve().parent/'private'
    # Preserve the original operator DB. Never clone it into private to satisfy a guard.
    for name in ('runtime','previous_runtime','discovery','authorization','reservation'):
        value=getattr(args,name)
        if value is not None and not value.resolve().is_relative_to(private):parser.error('Recovery artifacts must remain service/private')
    original_database=private.parent.parent/'.runtime/appserver-native-live/tasks.sqlite3'
    if (not args.database.is_file() or not (args.database.resolve().is_relative_to(private)
            or args.database.resolve()==original_database.resolve())):
        parser.error('Existing private DB or exact original .runtime/appserver-native-live/tasks.sqlite3 required; no clone')
    try:
        runtime=json.loads(args.runtime.read_text(encoding='utf-8'))
        previous=json.loads((args.previous_runtime or args.runtime).read_text(encoding='utf-8'))
        saved=json.loads(args.discovery.read_text(encoding='utf-8'))
        reservation=json.loads(args.reservation.read_text(encoding='utf-8'))
        if reservation.get('task_id')!=args.task_id:raise Conflict('Operator reservation belongs to another task')
        key=reservation.get('runner_key');store=RecoveryStore(args.database,runtime)
        if args.action=='prepare':
            if args.authorization.exists():raise Conflict('Never overwrite an existing authorization artifact')
            template=false_template(store,args.task_id,key,saved,previous)
            private_json(args.authorization,template)
            print(json.dumps({'status':'private_template_prepared','authorized':False,'RPC_requests':0,
                              'cumulative_existing_turns':2,'proposed_total_limit':4}))
            return
        auth=json.loads(args.authorization.read_text(encoding='utf-8'))
        store.inspect_recovery(args.task_id,key,auth,saved,previous) # BEFORE AppServer initialize; false => zero RPC.
        check_eligibility(runtime,saved,saved)
        if args.action=='check':
            print(json.dumps({'status':'scoped_authorization_checked','RPC_requests':0,'inference_started':False}));return
        workspace=Path(runtime.get('workspace',''))
        if not workspace.is_absolute() or not workspace.is_dir():raise Conflict('Existing absolute read-only workspace required')
        protocol=Protocol(private/'appserver-protocol')
        with AppServer(protocol,private/'appserver-state',args.existing_codex_dir) as client:
            current=discover(client,runtime['runtime_id'],protocol.hashes,client.executable)
            result=RecoveryRunner(store,client,saved,current,private/'runner',authorization=auth,
                previous_runtime=previous,operator_key=key,turn_timeout=args.turn_timeout).resume(args.task_id)
            print(json.dumps(result))
    except (OSError,ValueError,ProtocolError,TimeoutError,KeyError) as exc:
        if isinstance(exc,RPCRejected):private_json(private/'last-recovery-rpc-error.json',exc.private_error)
        if isinstance(exc,Attention):private_json(private/'last-recovery-attention.json',exc.request)
        print(json.dumps({'status':'blocked','failure_type':type(exc).__name__,'reason':str(exc),
                          'inference_success_claimed':False,'hosted':False}));raise SystemExit(2)


if __name__=='__main__':main()
