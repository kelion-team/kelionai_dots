"""Loopback-only JSON API; invoke explicitly. Native work is performed by its parent."""
import argparse
import hmac
import ipaddress
import json
import os
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from store import Store, Conflict
from mcp_protocol import MCP, VERSIONS, MAX_BODY, error as rpc_error


def validated_public_origin(value):
    """One explicit HTTPS origin; no path, wildcard, userinfo or implicit proxy trust."""
    if (not isinstance(value,str) or not value or value != value.strip()
            or any(ord(char) < 33 or ord(char) > 126 for char in value)
            or any(char in value for char in ('%','\\','*','?','#'))):
        raise ValueError('Public origin must be one strict HTTPS DNS origin')
    parsed=urlsplit(value)
    if (parsed.scheme != 'https' or not parsed.netloc or parsed.path or parsed.query or parsed.fragment
            or parsed.username is not None or parsed.password is not None):
        raise ValueError('Public origin requires HTTPS and no path, credentials, query or fragment')
    host=parsed.hostname
    if (not host or len(host) > 253 or '.' not in host
            or not all(re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?',label)
                       for label in host.split('.'))):
        raise ValueError('Public origin requires an exact DNS hostname without wildcard')
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError('Public origin requires a DNS hostname, not an IP address')
    try:
        port=parsed.port
    except ValueError:
        raise ValueError('Invalid public origin port') from None
    if port is not None and not 1 <= port <= 65535:
        raise ValueError('Invalid public origin port')
    authority=host + (':'+str(port) if port is not None else '')
    if parsed.netloc.lower() != authority:
        raise ValueError('Invalid public origin authority')
    return 'https://' + host + (':'+str(port) if port not in (None,443) else '')


def handler_for(store, client_token, worker_token, public_origin=None):
    public_origin=validated_public_origin(public_origin) if public_origin is not None else None
    protocol = MCP(store)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Do not put task data or authorization headers into logs.

        def respond(self, status, data):
            # Drain a bounded already-declared POST body on early rejection. Closing
            # a Windows socket with unread body bytes can reset the response itself.
            if status >= 400 and self.command == 'POST' and not getattr(self,'body_consumed',False):
                length=self.headers.get('Content-Length','')
                if length.isdecimal() and 0 < int(length) <= MAX_BODY:
                    try:
                        self.connection.settimeout(1)
                        self.rfile.read(int(length))
                    except (OSError,TimeoutError):
                        pass
                    self.body_consumed=True
            raw = json.dumps(data, ensure_ascii=False, allow_nan=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(raw)

        def respond_empty(self, status):
            self.send_response(status)
            self.send_header('Content-Length','0')
            if status == 405:
                self.send_header('Allow','POST')
            self.end_headers()

        def mcp(self):
            # Only explicit configuration can add a public authority; forwarded headers are ignored.
            port=self.server.server_port
            allowed_hosts={'127.0.0.1:'+str(port),'localhost:'+str(port)}
            if public_origin is not None:
                public=urlsplit(public_origin)
                allowed_hosts.add(public.netloc)
                if public.port is None:
                    allowed_hosts.add(public.netloc+':443')
            if self.headers.get('Host','').lower() not in allowed_hosts:
                return self.respond(403,{'error':'Invalid Host'})
            origin=self.headers.get('Origin')
            # Public HTTPS is allowed only at the configured origin, never HTTP on that domain.
            allowed_origins={'http://127.0.0.1:'+str(port),'http://localhost:'+str(port)}
            if public_origin is not None:
                allowed_origins.add(public_origin)
            if origin is not None:
                if origin not in allowed_origins:
                    try:
                        normalized=validated_public_origin(origin)
                    except ValueError:
                        return self.respond(403,{'error':'Invalid Origin'})
                    if normalized not in allowed_origins:
                        return self.respond(403,{'error':'Invalid Origin'})
            version=self.headers.get('MCP-Protocol-Version','2025-03-26')
            if version not in VERSIONS:
                return self.respond(400,{'error':'Unsupported MCP-Protocol-Version'})
            if self.command != 'POST':
                return self.respond_empty(405)  # No SSE stream or MCP session is offered.
            accept={value.strip().split(';',1)[0] for value in self.headers.get('Accept','').split(',')}
            if not {'application/json','text/event-stream'}.issubset(accept):
                return self.respond(406,{'error':'Accept must include application/json and text/event-stream'})
            if self.headers.get_content_type() != 'application/json':
                return self.respond(415,{'error':'Content-Type application/json required'})
            length=self.headers.get('Content-Length')
            if length is None or not length.isdecimal() or not 0 < int(length) <= MAX_BODY:
                return self.respond(400,{'error':'Bounded Content-Length required'})
            self.connection.settimeout(10)
            raw=self.rfile.read(int(length))
            self.body_consumed=True
            if len(raw) != int(length):
                return self.respond(400,{'error':'Incomplete body'})
            try:
                message=json.loads(raw)
            except (ValueError,UnicodeError):
                return self.respond(400,rpc_error(None,-32700,'Parse error'))
            response=protocol.handle(message)
            if response is None:
                return self.respond_empty(202)
            return self.respond(200,response)

        def route(self):
            path = urlsplit(self.path)
            if path.query or path.fragment:
                raise ValueError('Query and fragment are not accepted')
            worker = path.path.startswith('/v1/worker/')
            if worker:
                # Worker capabilities are local even when another route is exposed
                # behind an explicitly configured reverse proxy.
                expected_host='127.0.0.1:'+str(self.server.server_port)
                if (self.client_address[0] not in ('127.0.0.1','::1')
                        or self.headers.get('Host','').lower()!=expected_host
                        or self.headers.get('Origin') is not None
                        or any(self.headers.get(k) is not None for k in ('Forwarded','X-Forwarded-For','X-Forwarded-Host'))):
                    return self.respond(403, {'error':'Worker API requires direct loopback access'})
            expected = worker_token if worker else client_token
            authorization = self.headers.get('Authorization', '')
            if not hmac.compare_digest(authorization.encode('utf-8'), ('Bearer ' + expected).encode('utf-8')):
                return self.respond(401, {'error': 'Unauthorized'})
            if path.path == '/mcp':
                return self.mcp()
            if self.command == 'GET' and path.path == '/v1/health':
                execution=('bounded_local_appserver_runner_required' if store.runtime['adapter']=='codex-app-server'
                           else 'external_native_parent_required')
                return self.respond(200, {'adapter':store.runtime['adapter'],'runtime_id':store.runtime['runtime_id'],
                                         'execution':execution,'hosted':False})
            if self.command == 'GET' and path.path.startswith('/v1/tasks/'):
                return self.respond(200, store.get(path.path.removeprefix('/v1/tasks/')))
            if self.command == 'GET' and path.path == '/v1/worker/awaiting':
                return self.respond(200, {'task':store.awaiting()})
            if self.command != 'POST':
                return self.respond(404, {'error': 'Unknown endpoint'})
            length = self.headers.get('Content-Length')
            if length is None or not length.isdecimal() or not 0 < int(length) <= 1200000:
                raise ValueError('Bounded Content-Length required')
            if self.headers.get_content_type() != 'application/json':
                raise ValueError('Content-Type application/json required')
            self.connection.settimeout(10)
            raw = self.rfile.read(int(length))
            self.body_consumed=True
            if len(raw) != int(length):
                raise ValueError('Incomplete body')
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError('JSON object required')
            if path.path == '/v1/worker/magistrala/take' and set(data) == {'worker_id', 'wait_seconds'}:
                # Long-poll: răspunde imediat ce apare o cerere nouă (sau după wait_seconds, maxim 25).
                wait = data['wait_seconds'] if type(data['wait_seconds']) is int and 0 <= data['wait_seconds'] <= 25 else 0
                deadline = time.time() + wait
                while True:
                    task = store.magistrala_take(data['worker_id'])
                    if task is not None or time.time() >= deadline:
                        return self.respond(200, {'task': task})
                    time.sleep(0.5)
            if path.path == '/v1/worker/magistrala/finish' and set(data) == {'task_id','take_token','status','output','hops'}:
                return self.respond(200, store.magistrala_finish(**data))
            if path.path.startswith('/v1/worker/magentic/'):
                return self.respond(200,store.magentic_worker(path.path.removeprefix('/v1/worker/magentic/'),data))
            if path.path == '/v1/worker/runner/reserve' and set(data)=={'worker_id','task_id','authorization'}:
                return self.respond(200,{'reservation':store.reserve_runner(data['worker_id'],data['task_id'],worker_authorization=data['authorization'])})
            if path.path == '/v1/worker/runner/status' and set(data)=={'task_id','runner_key'}:
                return self.respond(200,store.private_runner_status(**data))
            if path.path == '/v1/worker/runner/checkpoint' and set(data)=={'task_id','runner_key','phase','data','needs_reconcile','finished'}:
                if (not isinstance(data['phase'],str) or data['phase'] not in ('kelion_selection','dots_assessment','dots_work','finished','bootstrap')
                        or not isinstance(data['data'],dict) or type(data['needs_reconcile']) is not bool or type(data['finished']) is not bool):
                    raise ValueError('Exact bounded runner checkpoint required')
                store.runner_checkpoint(**data)
                return self.respond(200,{'checkpointed':True})
            if path.path == '/v1/worker/runner/turn-intent' and set(data)=={'task_id','runner_key','phase','data'}:
                if (data['phase'] not in ('kelion_selection','dots_assessment','dots_work') or not isinstance(data['data'],dict)
                        or not isinstance(data['data'].get('thread_id'),str) or not data['data']['thread_id']
                        or not isinstance(data['data'].get('turn_request_sha256'),str)
                        or not re.fullmatch(r'[a-f0-9]{64}',data['data']['turn_request_sha256'])):
                    raise ValueError('Exact bounded turn intent required')
                return self.respond(200,{'index':store.runner_turn_intent(**data)})
            if path.path == '/v1/worker/runner/prepare' and set(data)=={'task_id','runner_key','role','assessment','logic_validation_required'}:
                return self.respond(200,store.prepare(**data))
            if path.path == '/v1/worker/runner/claim' and set(data)=={'task_id','runner_key','worker_id'}:
                return self.respond(200,{'claim':store.claim(**data)})
            if path.path == '/v1/tasks':
                result = store.intake(data)
                return self.respond(202 if result['state'] == 'awaiting_kelion' else 200, result)
            if path.path == '/v1/worker/prepared-tasks':
                result = store.submit(data)
                return self.respond(202 if result['state'] == 'queued' else 200, result)
            if path.path == '/v1/worker/prepare' and set(data) in (
                    {'task_id','role','assessment'}, {'task_id','role','assessment','logic_validation_required'}):
                return self.respond(200, store.prepare(**data))
            if path.path == '/v1/worker/claim' and set(data) == {'worker_id'}:
                return self.respond(200, {'claim': store.claim(data['worker_id'])})
            if path.path == '/v1/worker/complete' and set(data) == {'task_id','lease_token','output','receipt'}:
                return self.respond(200, store.complete(**data))
            if path.path == '/v1/worker/fail' and set(data) == {'task_id','lease_token','reason'}:
                return self.respond(200, store.fail(**data))
            return self.respond(404, {'error': 'Unknown endpoint or fields'})

        def process(self):
            try:
                self.route()
            except Conflict as exc:
                self.respond(409, {'error': str(exc)})
            except KeyError:
                self.respond(404, {'error': 'Unknown task_id'})
            except (ValueError, TypeError, UnicodeError) as exc:
                self.respond(400, {'error': str(exc)})
            except Exception:
                self.respond(500, {'error': 'Internal service error'})

        do_GET = process
        do_POST = process
        do_DELETE = process
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', required=True, type=Path)
    parser.add_argument('--runtime', type=Path, default=Path(__file__).with_name('runtime.unverified.json'))
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--public-origin',type=validated_public_origin,
                        help='One explicit HTTPS origin accepted by MCP Host/Origin checks; bind stays loopback')
    args = parser.parse_args()
    tokens = [os.environ.get(name, '') for name in ('KELION_CLIENT_TOKEN','KELION_WORKER_TOKEN')]
    if any(len(value) < 32 for value in tokens) or tokens[0] == tokens[1]:
        parser.error('Two distinct tokens of at least 32 characters required in environment')
    store = Store(args.database, json.loads(args.runtime.read_text(encoding='utf-8')))
    server = ThreadingHTTPServer(('127.0.0.1', args.port), handler_for(store, *tokens, public_origin=args.public_origin))
    print(json.dumps({'listen': '127.0.0.1', 'port': server.server_port, 'adapter': store.runtime['adapter'],
                      'public_listener': False, 'native_parent_required': True,
                      'allowed_public_origin':args.public_origin}), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
