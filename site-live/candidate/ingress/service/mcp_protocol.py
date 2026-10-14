"""Minimal stateless MCP JSON-RPC: raw intake and readback, never worker tools."""
from store import Conflict

VERSIONS = ('2025-03-26','2025-06-18')
MAX_BODY = 1200000
TOOLS = [
    {'name':'kelion_submit','description':'Submit a raw task to the shared Kelion queue. '
        'Kelion chooses the profile internally. Acceptance awaits a native parent; it is not execution.',
     'inputSchema':{'type':'object','properties':{
        'task_id':{'type':'string','pattern':'^[A-Za-z0-9][A-Za-z0-9_.-]{3,127}$'},
        'task':{'type':'string','minLength':1,'maxLength':100000},
        'origin':{'type':'string','enum':['chat','work','codex']},
        'input_mode':{'type':'string','enum':['text','voice_transcript']}},
        'required':['task_id','task','origin','input_mode'],'additionalProperties':False},
     'annotations':{'readOnlyHint':False,'destructiveHint':False,'idempotentHint':True,'openWorldHint':False}},
    {'name':'kelion_get','description':'Read a shared task by its exact task_id, including actual output '
        'when the native parent has returned it. verified=false is not a completion certificate.',
     'inputSchema':{'type':'object','properties':{'task_id':{'type':'string',
        'pattern':'^[A-Za-z0-9][A-Za-z0-9_.-]{3,127}$'}},'required':['task_id'],'additionalProperties':False},
     'annotations':{'readOnlyHint':True,'destructiveHint':False,'idempotentHint':True,'openWorldHint':False}}
]


def error(identity, code, message):
    return {'jsonrpc':'2.0','id':identity,'error':{'code':code,'message':message}}


class MCP:
    def __init__(self, store):
        self.store = store

    def handle(self, message):
        if (not isinstance(message,dict) or message.get('jsonrpc') != '2.0'
                or not isinstance(message.get('method'),str)):
            return error(None,-32600,'Invalid JSON-RPC request')
        if 'id' not in message:
            # Notifications are accepted without executing a tools/call mutation.
            return None
        identity = message['id']
        if type(identity) not in (int,str):
            return error(None,-32600,'Request id must be a string or integer')
        method = message['method']
        params = message.get('params',{})
        if not isinstance(params,dict):
            return error(identity,-32602,'Params must be an object')
        if method == 'initialize':
            requested = params.get('protocolVersion')
            if not isinstance(requested,str) or not isinstance(params.get('clientInfo'),dict) or not isinstance(params.get('capabilities'),dict):
                return error(identity,-32602,'initialize requires protocolVersion, clientInfo and capabilities')
            result = {'protocolVersion':requested if requested in VERSIONS else VERSIONS[-1],
                      'capabilities':{'tools':{'listChanged':False}},
                      'serverInfo':{'name':'kelion-common-service','version':'0.1.0'},
                      'instructions':'Submit raw user requests without choosing a role/model. '
                        'The native Kelion parent performs selection and assessment. '
                        'Use kelion_get with the same task_id for handoff/readback. '
                        'Queue acceptance is not execution; no automatic chat interception or audio processing is provided.'}
        elif method == 'ping':
            result = {}
        elif method == 'tools/list':
            if not set(params).issubset({'cursor','_meta'}) or params.get('cursor') not in (None,''):
                return error(identity,-32602,'Invalid tools/list cursor or fields')
            result = {'tools':TOOLS}
        elif method == 'tools/call':
            if (not {'name','arguments'}.issubset(params) or not set(params).issubset({'name','arguments','_meta'})
                    or not isinstance(params['arguments'],dict)):
                return error(identity,-32602,'tools/call requires name and arguments')
            name,args = params['name'],params['arguments']
            if name not in ('kelion_submit','kelion_get'):
                return error(identity,-32602,'Unknown tool; native worker endpoints are not MCP tools')
            try:
                if name == 'kelion_submit':
                    data = self.store.intake(args)
                else:
                    if set(args) != {'task_id'}:
                        raise ValueError('kelion_get requires task_id only')
                    data = self.store.get(args['task_id'])
                import json
                result = {'content':[{'type':'text','text':json.dumps(data,ensure_ascii=False)}],
                          'structuredContent':data,'isError':False}
            except (ValueError,Conflict,KeyError,TypeError) as exc:
                result = {'content':[{'type':'text','text':'Unknown task_id' if isinstance(exc,KeyError) else str(exc)}],
                          'isError':True}
        else:
            return error(identity,-32601,'Method not found')
        return {'jsonrpc':'2.0','id':identity,'result':result}
