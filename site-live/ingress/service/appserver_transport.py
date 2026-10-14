"""Official CLI AppServer stdio lifecycle. No shell, auth copy, or automatic approvals."""
import hashlib
import json
import queue
import shutil
import subprocess
import threading
import time
from pathlib import Path
from probe_runtime import child_environment

METHOD_SCHEMAS={
    'initialize':'v1/InitializeParams.json','account/read':'v2/GetAccountParams.json',
    'account/rateLimits/read':'v2/NullableGetAccountRateLimitsParams.json',
    'model/list':'v2/ModelListParams.json','thread/start':'v2/ThreadStartParams.json',
    'thread/resume':'v2/ThreadResumeParams.json',
    'turn/start':'v2/TurnStartParams.json','thread/read':'v2/ThreadReadParams.json',
    'turn/interrupt':'v2/TurnInterruptParams.json'}


class ProtocolError(RuntimeError):
    pass


class RPCRejected(ProtocolError):
    """Public text is bounded; backend message/data are private operator evidence."""
    def __init__(self, method, error):
        super().__init__('RPC '+method+' rejected, code '+str(error.get('code')))
        self.private_error={'method':method,'error':error}


class Attention(ProtocolError):
    def __init__(self, request):
        super().__init__('AppServer requested an explicit external decision; no automatic approval')
        self.request=request


class Protocol:
    def __init__(self, directory):
        self.directory=Path(directory)
        self.schemas={};self.hashes={}
        for method,name in METHOD_SCHEMAS.items():
            raw=(self.directory/name).read_bytes()
            self.schemas[method]=json.loads(raw)
            self.hashes[name]=hashlib.sha256(raw).hexdigest()
        # Validate the exact protocol feature contract before allowing methods.
        for method,fields in {'thread/start':{'model','modelProvider','config','allowProviderModelFallback','historyMode'},
                              'turn/start':{'threadId','input','model','effort','outputSchema'},
                              'thread/read':{'threadId','includeTurns'}}.items():
            if not fields.issubset(self.schemas[method].get('properties',{})):
                raise ProtocolError('Generated CLI protocol does not support required fields: '+method)

    def check(self, method, params):
        if method not in self.schemas:
            raise ProtocolError('Method not supported by this bounded adapter')
        schema=self.schemas[method]
        # Nullable empty params are represented by anyOf in the generated schema.
        if 'anyOf' in schema:
            schema=next((item for item in schema['anyOf'] if item.get('type')=='object'),schema)
        if not isinstance(params,dict):
            raise ProtocolError('RPC params must be an object')
        if not set(schema.get('required',[])).issubset(params):
            raise ProtocolError('Missing protocol parameters: '+method)
        if 'properties' in schema and not set(params).issubset(schema['properties']):
            raise ProtocolError('Unsupported protocol parameters: '+method)


class AppServer:
    def __init__(self, protocol, state_directory, existing_codex_dir=None, *, rpc_timeout=20, experimental_api=True):
        self.protocol=protocol;self.state=Path(state_directory);self.rpc_timeout=rpc_timeout
        self.environment=child_environment(existing_codex_dir)
        self.executable=shutil.which('codex')
        if not self.executable:
            raise ProtocolError('Existing official Codex executable not found')
        self.process=None;self.messages=queue.Queue();self.events=[];self.counter=0
        self.warnings={'access_denied':False,'sqlite_initialization_failed':False}
        self.experimental_api=experimental_api

    def __enter__(self):
        self.state.mkdir(parents=True,exist_ok=True)
        args=[self.executable,'app-server','--stdio','--disable','multi_agent',
              '--disable','multi_agent_v2','--disable','multi_agent_v2_dynamic_tools',
              '-c','sqlite_home='+json.dumps(str(self.state)),
              '-c','log_dir='+json.dumps(str(self.state/'logs'))]
        self.process=subprocess.Popen(args,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            text=True,encoding='utf-8',errors='replace',env=self.environment)
        def stdout():
            for line in self.process.stdout:
                try:self.messages.put(json.loads(line))
                except ValueError:self.messages.put({'transport_error':'non_json_stdout'})
            self.messages.put({'transport_error':'process_eof'})
        def stderr():
            for line in self.process.stderr:
                self.warnings['access_denied'] |= 'Access is denied' in line
                self.warnings['sqlite_initialization_failed'] |= 'failed to initialize sqlite state runtime' in line
            # Raw stderr/auth identifiers are never retained or printed.
        self.readers=[threading.Thread(target=stdout,daemon=True),threading.Thread(target=stderr,daemon=True)]
        for reader in self.readers:reader.start()
        try:
            params={'clientInfo':{'name':'kelion_local_runner',
                'title':'Kelion bounded local runner','version':'0.1.0'}}
            if self.experimental_api:params['capabilities']={'experimentalApi':True}
            initialized=self.rpc('initialize',params)
            self.notify('initialized',{})
            self.initialized=initialized
            return self
        except Exception:
            self.close();raise

    def close(self):
        if self.process is None:return
        if self.process.stdin and not self.process.stdin.closed:self.process.stdin.close()
        try:self.process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.process.terminate();self.process.wait(timeout=3)
        for reader in self.readers:reader.join(timeout=1)
        for stream in (self.process.stdout,self.process.stderr):
            if stream and not stream.closed:stream.close()

    def __exit__(self, *args):
        self.close()

    def _send(self, data):
        if self.process is None or self.process.poll() is not None:
            raise ProtocolError('AppServer is not running')
        self.process.stdin.write(json.dumps(data,ensure_ascii=False)+'\n');self.process.stdin.flush()

    def notify(self, method, params):
        if method!='initialized':raise ProtocolError('Unsupported client notification')
        self._send({'jsonrpc':'2.0','method':method,'params':params})

    def send_request(self, method, params):
        self.protocol.check(method,params)
        self.counter+=1
        self._send({'jsonrpc':'2.0','id':self.counter,'method':method,'params':params})
        return self.counter

    def _receive(self, timeout):
        try:message=self.messages.get(timeout=max(0.01,timeout))
        except queue.Empty:raise TimeoutError('Bounded AppServer wait expired') from None
        if 'transport_error' in message:raise ProtocolError(message['transport_error'])
        if 'method' in message and 'id' in message:raise Attention(message)
        return message

    def rpc(self, method, params, timeout=None):
        request=self.send_request(method,params);end=time.monotonic()+(timeout or self.rpc_timeout)
        while time.monotonic()<end:
            message=self._receive(end-time.monotonic())
            if message.get('id')==request and 'method' not in message:
                if 'error' in message:
                    raise RPCRejected(method,message['error'])
                if not isinstance(message.get('result'),dict):raise ProtocolError('Invalid RPC result')
                return message['result']
            self.events.append(message)
        raise TimeoutError('Bounded RPC wait expired')

    def event(self, timeout):
        if self.events:return self.events.pop(0)
        return self._receive(timeout)


def account_fingerprint(account, limits):
    data={'account_id':limits.get('accountId'),'email':account.get('email')}
    return hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest() if any(data.values()) else None


def discover(client, runtime_id, protocol_hashes, executable=None):
    account=client.rpc('account/read',{'refreshToken':False})
    info=account.get('account') or {}
    catalog=[];cursor=None
    for page in range(10):
        params={'limit':100,'includeHidden':False}
        if cursor is not None:params['cursor']=cursor
        result=client.rpc('model/list',params)
        catalog.extend({'id':item['id'],'model':item['model'],
            'reasoning_levels':[effort['reasoningEffort'] for effort in item.get('supportedReasoningEfforts',[])],
            'default_reasoning_effort':item.get('defaultReasoningEffort'),'hidden':item.get('hidden')}
            for item in result.get('data',[]))
        cursor=result.get('nextCursor')
        if not cursor:break
    else:raise ProtocolError('Catalog pagination exceeded finite bound')
    limits=client.rpc('account/rateLimits/read',{})
    def clean_limit(value):
        if not isinstance(value,dict):return None
        return {key:value.get(key) for key in ('primary','secondary','planType','normalModelSlug',
                                             'rateLimitReachedType','spendControlReached')}
    fingerprint=account_fingerprint(info,limits)
    snapshot={'schema_version':1,'runtime_id':runtime_id,'adapter':'codex-app-server',
        'discovered_at':time.time(),'account_type':info.get('type'),'plan_type':info.get('planType'),
        'account_fingerprint_sha256':fingerprint,
        'ordinary_usage_allowed':limits.get('ordinaryUsageAllowed'),'catalog':catalog,
        'rate_limits':clean_limit(limits.get('rateLimits')),
        'rate_limits_by_id':{key:clean_limit(value) for key,value in (limits.get('rateLimitsByLimitId') or {}).items()},
        'protocol_sha256':protocol_hashes,'client_turn_requests':0,
        'catalog_is_execution_proof':False,'hosted_auth_eligibility':False}
    if executable:
        snapshot['executable_sha256']=hashlib.sha256(Path(executable).read_bytes()).hexdigest()
    # Account email, accountId, routing overrides, credits balance and auth are not persisted.
    return snapshot
