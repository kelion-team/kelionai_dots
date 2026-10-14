"""Real loopback HTTP/SQLite; all authority/model data are synthetic fixtures."""
import concurrent.futures
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request

SERVICE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE))
from store import Store, canonical, digest
from server import handler_for, ThreadingHTTPServer


class AtomicWorkerHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.raw = {'task_id':'SYNTHETIC-http-one','task':'List entries','origin':'codex','input_mode':'text'}
        self.runtime = {'adapter':'codex-app-server','runtime_id':'SYNTHETIC-http-runtime','execution_surface':'codex','verification_evidence':'SYNTHETIC ONLY',
            'manifest':{'schema_version':1,'connectors':[],'models':[{'id':'fixture-economic','surface':'codex','enabled':True,'verified':True,'billing_mode':'included','capability_tier':1,'cost_rank':1,'reasoning_levels':['low'],'native_spawn_supported':True}]},
            'siwc_worker':{'enabled':True,'task_id':self.raw['task_id'],'input_sha256':digest(canonical(self.raw)),'authorization_sha256':'a'*64,'max_turns':3,'expires_at':time.time()+300}}
        self.store = Store(Path(self.temp.name)/'fixture.sqlite3', self.runtime)
        self.store.intake(self.raw)
        self.client='SYNTHETIC-client-'+'c'*32; self.worker='SYNTHETIC-worker-'+'w'*32
        self.server=ThreadingHTTPServer(('127.0.0.1',0),handler_for(self.store,self.client,self.worker))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.url='http://127.0.0.1:'+str(self.server.server_port)
        self.authorization={k:v for k,v in self.runtime['siwc_worker'].items() if k!='enabled'}
        self.authorization['runtime_sha256']=digest(canonical(self.runtime))

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.temp.cleanup()

    def call(self, route, data, token=None, headers=None):
        request=urllib.request.Request(self.url+route,data=json.dumps(data).encode(),headers={'Authorization':'Bearer '+(token or self.worker),'Content-Type':'application/json',**(headers or {})})
        try:
            with urllib.request.urlopen(request,timeout=5) as response:return response.status,json.load(response)
        except urllib.error.HTTPError as e:return e.code,json.load(e)

    def reserve(self, worker='worker-synthetic-one', authorization=None):
        return self.call('/v1/worker/runner/reserve',{'task_id':self.raw['task_id'],'worker_id':worker,'authorization':authorization or self.authorization})

    def test_client_token_origin_and_forwarded_headers_cannot_reserve(self):
        payload={'task_id':self.raw['task_id'],'worker_id':'worker-synthetic-one','authorization':self.authorization}
        self.assertEqual(self.call('/v1/worker/runner/reserve',payload,self.client)[0],401)
        for headers in ({'Origin':self.url},{'X-Forwarded-For':'127.0.0.1'},{'Host':'attacker.invalid'}):
            self.assertEqual(self.call('/v1/worker/runner/reserve',payload,headers=headers)[0],403)
        self.assertEqual(self.store.get(self.raw['task_id'])['state'],'awaiting_kelion')

    def test_two_workers_only_one_atomic_raw_owner(self):
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            outcomes=list(pool.map(self.reserve,['worker-synthetic-one','worker-synthetic-two']))
        self.assertEqual(sorted(s for s,_ in outcomes),[200,409])
        self.assertEqual(self.store.get(self.raw['task_id'])['state'],'running_kelion')

    def test_exact_input_authorization_runtime_and_budget_required(self):
        for field,value in [('task_id','SYNTHETIC-other'),('input_sha256','b'*64),('runtime_sha256','b'*64),('authorization_sha256','b'*64),('max_turns',4),('expires_at',0)]:
            wrong=dict(self.authorization,**{field:value});self.assertEqual(self.reserve(authorization=wrong)[0],409)
        self.assertEqual(self.store.get(self.raw['task_id'])['state'],'awaiting_kelion')

    def test_private_journal_requires_exact_key_and_never_client_token(self):
        _,result=self.reserve();key=result['reservation']['runner_key'];data={'task_id':self.raw['task_id'],'runner_key':key}
        self.assertEqual(self.call('/v1/worker/runner/status',data,self.client)[0],401)
        self.assertEqual(self.call('/v1/worker/runner/status',dict(data,runner_key='wrong'))[0],409)
        self.assertEqual(self.call('/v1/worker/runner/status',data)[1]['state'],'running')

    def test_claim_wrong_task_cannot_dequeue_another_task(self):
        _,reserved=self.reserve();key=reserved['reservation']['runner_key']
        result=self.call('/v1/worker/runner/claim',{'task_id':'SYNTHETIC-other','runner_key':key,'worker_id':'worker-synthetic-one'})
        self.assertEqual(result[0],409)

    def test_cumulative_intents_durable_before_any_rpc_and_no_replay(self):
        _,reserved=self.reserve();key=reserved['reservation']['runner_key']
        for index,phase in enumerate(['kelion_selection','dots_assessment','dots_work'],1):
            payload={'task_id':self.raw['task_id'],'runner_key':key,'phase':phase,'data':{'thread_id':'fixture-thread-'+str(index),'turn_request_sha256':'b'*64}}
            code,result=self.call('/v1/worker/runner/turn-intent',payload);self.assertEqual(code,200);self.assertEqual(result['index'],index)
            self.assertEqual(self.store.runner_status(self.raw['task_id'])['journal']['client_turn_requests'],index)
            self.assertEqual(self.call('/v1/worker/runner/turn-intent',payload)[0],409)
        self.assertEqual(self.store.runner_status(self.raw['task_id'])['journal']['client_turn_requests'],3)

    def test_crash_restart_reservation_cannot_reset_cumulative_budget(self):
        _,reserved=self.reserve();key=reserved['reservation']['runner_key']
        self.call('/v1/worker/runner/turn-intent',{'task_id':self.raw['task_id'],'runner_key':key,'phase':'kelion_selection','data':{'thread_id':'fixture-thread','turn_request_sha256':'b'*64}})
        restarted=Store(self.store.database,self.runtime)
        self.assertEqual(restarted.runner_status(self.raw['task_id'])['journal']['client_turn_requests'],1)
        self.assertEqual(self.reserve('worker-after-crash')[0],409)
        code,_=self.call('/v1/worker/runner/checkpoint',{'task_id':self.raw['task_id'],'runner_key':key,'phase':'kelion_selection','data':{'state':'needs_reconcile'},'needs_reconcile':True,'finished':False})
        self.assertEqual(code,200);self.assertEqual(self.store.get(self.raw['task_id'])['state'],'interrupted_requires_reconcile')
        self.assertEqual(self.reserve('worker-after-crash')[0],409)


if __name__=='__main__':unittest.main()
