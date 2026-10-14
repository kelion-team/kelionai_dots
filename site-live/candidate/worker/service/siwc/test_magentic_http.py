"""Actual HTTP + temporary SQLite; only explicitly synthetic framework data."""
import concurrent.futures
import json
import time
import unittest
import test_worker_http as helpers
from store import Store, canonical, digest
from siwc.magentic_store import COMMIT


class MagenticHTTPTests(unittest.TestCase):
    call=helpers.AtomicWorkerHTTPTests.call
    tearDown=helpers.AtomicWorkerHTTPTests.tearDown

    def setUp(self):
        helpers.AtomicWorkerHTTPTests.setUp(self)
        self.runtime['siwc_magentic']={'enabled':True,'task_id':self.raw['task_id'],'input_sha256':digest(canonical(self.raw)),'authorization_sha256':'b'*64,'framework_config_sha256':'c'*64,'max_turns':4,'expires_at':time.time()+300}
        self.auth={k:v for k,v in self.runtime['siwc_magentic'].items() if k!='enabled'}
        self.auth['runtime_sha256']=digest(canonical(self.runtime))
        self.worker_id='SYNTHETIC-magentic-worker'

    def reserve(self,worker=None,auth=None):
        return self.call('/v1/worker/magentic/reserve',{'task_id':self.raw['task_id'],'worker_id':worker or self.worker_id,'authorization':auth or self.auth})

    def own(self):
        status,result=self.reserve();self.assertEqual(status,200)
        self.base={'task_id':self.raw['task_id'],'worker_id':self.worker_id,'runner_key':result['reservation']['runner_key']}

    def op(self,operation,**kwargs):return self.call('/v1/worker/magentic/'+operation,{**self.base,**kwargs})

    def request(self,n):
        payload={'schema_version':1,'task_id':self.raw['task_id'],'mode':'native_host','kind':'manager_reasoning','role':'kelion_manager','framework_commit':COMMIT,'config_sha256':'c'*64,'system_instructions':'SYNTHETIC instructions','messages':[{'role':'user','text':'SYNTHETIC '+str(n),'author_name':None}],'host_requirements':{}}
        rid=digest(canonical(payload));r={**payload,'request_id':rid,'input_sha256':rid,'dispatch_state':'awaiting_native_host'}
        self.assertEqual(self.op('request',request=r)[0],200);return rid

    def intent(self,rid):return self.op('turn-intent',request_id=rid,phase='manager',data={'thread_id':'SYNTHETIC-thread-'+rid,'turn_request_sha256':'d'*64})

    def test_concurrent_exact_task_owner_and_client_separation(self):
        payload={'task_id':self.raw['task_id'],'worker_id':self.worker_id,'authorization':self.auth}
        self.assertEqual(self.call('/v1/worker/magentic/reserve',payload,self.client)[0],401)
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            results=list(pool.map(self.reserve,['SYNTHETIC-one','SYNTHETIC-two']))
        self.assertEqual(sorted(x[0] for x in results),[200,409])

    def test_binding_and_worker_identity(self):
        for k,v in [('input_sha256','e'*64),('framework_config_sha256','e'*64),('max_turns',5),('runtime_sha256','e'*64)]:self.assertEqual(self.reserve(auth={**self.auth,k:v})[0],409)
        self.own()
        self.assertEqual(self.op('status',worker_id='SYNTHETIC-wrong')[0],409)
        self.assertEqual(self.op('status',task_id='SYNTHETIC-wrong')[0],404)
        self.assertEqual(self.op('status',runner_key='wrong')[0],409)

    def test_many_requests_share_one_cumulative_budget_and_restart_cannot_reset(self):
        self.own()
        for i in range(4):
            rid=self.request(i);code,result=self.intent(rid);self.assertEqual(code,200);self.assertEqual(result['index'],i+1)
            self.assertEqual(self.intent(rid)[0],409)
        restarted=Store(self.store.database,self.runtime)
        self.assertEqual(restarted.runner_status(self.raw['task_id'])['journal']['client_turn_requests'],4)
        self.assertEqual(self.reserve()[0],409)
        self.assertEqual(self.op('fail',reason='SYNTHETIC timeout unknown acceptance')[0],200)
        self.assertEqual(self.intent(rid)[0],409)
        self.assertEqual(self.op('status')[1]['state'],'needs_reconcile')

    def test_normal_runner_contract_cannot_spend_magentic_budget(self):
        self.own();data={k:v for k,v in self.base.items() if k!='worker_id'}
        self.assertEqual(self.call('/v1/worker/runner/turn-intent',{**data,'phase':'kelion_selection','data':{'thread_id':'SYNTHETIC','turn_request_sha256':'d'*64}})[0],409)

    def policy(self,**changes):
        p={'enabled':True,'mode':'owner_gateway','dedicated_owner_gateway_client':True,'gateway_client_token_sha256':digest(self.client),
           'frontend_receipt_client_token_sha256':digest(self.client),'grant_fingerprint':'a'*64,'activated_at':time.time()-0.1,'expires_at':time.time()+300,
           'max_turns':4,'max_jobs':2,'max_session_turns':8,'framework_template':{'participants':[self.store.registry['roles'][0]['name']],'max_rounds':2,'max_resets':1,'max_stalls':1,'max_requests':4},**changes}
        self.runtime['siwc_magentic']=p
        return {'worker_id':self.worker_id,'policy_sha256':digest(canonical(p))}

    def test_owner_gateway_admission_ignores_unmarked_tasks_and_preserves_raw_hash(self):
        data=self.policy()
        self.assertIsNone(self.call('/v1/worker/magentic/admit',data)[1]['admission'])
        raw={**self.raw,'task_id':'SYNTHETIC-owner-web-new'}
        code,created=self.call('/v1/tasks',raw,self.client);self.assertEqual(code,202)
        self.assertEqual(created['input_hash'],digest(canonical(raw)));self.assertNotIn('private_ingress',created['payload'])
        self.assertEqual(self.call('/v1/worker/magentic/admit',data,self.client)[0],401)
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            results=list(pool.map(lambda w:self.call('/v1/worker/magentic/admit',{**data,'worker_id':w}),['SYNTHETIC-poll-one','SYNTHETIC-poll-two']))
        self.assertEqual(sorted(x[0] for x in results),[200,409])
        admitted=next(x[1]['admission'] for x in results if x[0]==200)
        self.assertEqual(admitted['reservation']['task_id'],raw['task_id']);self.assertEqual(admitted['authorization']['input_sha256'],digest(canonical(raw)))
        restarted=Store(self.store.database,self.runtime)
        self.assertEqual(restarted.runner_status(raw['task_id'])['journal']['client_turn_requests'],0)
        self.assertEqual(self.call('/v1/worker/magentic/admit',data)[0],409)

    def test_owner_policy_client_receipt_binding_and_session_budget_survive_restart(self):
        data=self.policy(frontend_receipt_client_token_sha256='b'*64)
        self.assertEqual(self.call('/v1/worker/magentic/admit',data)[0],409)
        data=self.policy(max_jobs=1,max_session_turns=4)
        raw={**self.raw,'task_id':'SYNTHETIC-owner-budget'};self.call('/v1/tasks',raw,self.client)
        admitted=self.call('/v1/worker/magentic/admit',data)[1]['admission']
        # Fixture-only completed state to isolate admission accounting. No turn
        # or framework completion is claimed by this test setup.
        with self.store.connect() as db:
            db.execute("UPDATE runner_jobs SET state='completed' WHERE task_id=?",(raw['task_id'],))
            db.execute("UPDATE tasks SET state='result_received' WHERE task_id=?",(raw['task_id'],))
        restarted=Store(self.store.database,self.runtime)
        result=restarted.magentic_worker('admit',data)
        self.assertEqual(result,{'admission':None,'stop_reason':'finite_session_budget_exhausted'})
        self.assertEqual(admitted['authorization']['max_turns'],4)

    def test_completion_requires_exact_actual_proof_and_framework_readback(self):
        self.own();rid=self.request(1);self.intent(rid)
        tid='SYNTHETIC-thread-'+rid
        self.op('checkpoint',request_id=rid,phase='manager',data={'state':'turn_started','thread_id':tid,'turn_id':'SYNTHETIC-turn'})
        proof={'state':'readback_complete','thread_id':tid,'turn_id':'SYNTHETIC-turn','prompt_sha256':rid,'output':'SYNTHETIC text','output_sha256':digest('SYNTHETIC text'),'configured_model':'fixture-economic','configured_effort':'low','configured_binding_source':'thread/start + thread/resume + thread/read','per_turn_model_attestation':False}
        self.assertEqual(self.op('checkpoint',request_id=rid,phase='manager',data=proof)[0],200)
        response={'request_id':rid,'input_sha256':rid,'task_id':self.raw['task_id'],'text':proof['output'],'output_sha256':proof['output_sha256'],'host_run_id':tid,'execution_kind':'native_host'}
        receipt={'request_id':rid,'role':'kelion_manager','host_run_id':tid,'dispatch_ref':'SYNTHETIC-turn','model':'fixture-economic','reasoning_effort':'low'}
        self.assertEqual(self.op('readback',request_id=rid,receipt=receipt,response={**response,'text':'wrong'})[0],409)
        self.assertEqual(self.op('readback',request_id=rid,receipt=receipt,response=response)[0],200)
        final={'status':'framework_completed_requires_independent_verification','mode':'native_host','task_id':self.raw['task_id'],'text':proof['output'],'output_sha256':proof['output_sha256']}
        status={'final':final,'pending_count':0,'status':final['status']}
        self.assertEqual(self.op('complete',final=final,status_readback={**status,'pending_count':1})[0],409)
        code,result=self.op('complete',final=final,status_readback=status);self.assertEqual(code,200);self.assertEqual(result['output_hash'],proof['output_sha256'])
        self.assertEqual(self.op('status')[1]['state'],'completed')

if __name__=='__main__':unittest.main()
