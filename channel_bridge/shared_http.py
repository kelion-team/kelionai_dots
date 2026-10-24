"""Loopback HTTP and Streamable HTTP MCP host for the shared message outbox.

Run behind the existing HTTPS reverse proxy. Tokens identify clients, never
request JSON. This host stores messages and receipts; it cannot execute models.
"""
import argparse
import hmac
import json
import os
import signal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from .shared import SharedChannel, ChannelError, PARTICIPANTS, OPTIONAL_PARTICIPANTS
from .oauth import OAuthServer, OAuthError

MAX_BODY = 262144
VERSIONS = ('2025-03-26', '2025-06-18')
FIELDS = {
    'id': {'type': 'string', 'minLength': 1, 'maxLength': 160},
    'correlation_id': {'type': 'string', 'minLength': 1, 'maxLength': 160},
    'text': {'type': 'string', 'minLength': 1, 'maxLength': 32000},
    'recipients': {'type': 'array', 'items': {'type': 'string'}, 'minItems': 1},
    'reply_to': {'type': 'string', 'minLength': 1, 'maxLength': 160},
    'after': {'type': 'integer', 'minimum': 0},
    'limit': {'type': 'integer', 'minimum': 1, 'maximum': 100},
    'unread_only': {'type': 'boolean'},
    'sha256': {'type': 'string', 'pattern': '^[a-f0-9]{64}$'},
}


def tool(name, description, fields, required, read_only):
    return {'name': name, 'description': description,
            'inputSchema': {'type': 'object', 'properties': {key: FIELDS[key] for key in fields},
                            'required': required, 'additionalProperties': False},
            'annotations': {'readOnlyHint': read_only, 'destructiveHint': False,
                            'idempotentHint': True, 'openWorldHint': False}}


TOOLS = [
    tool('kelion_channel_send', 'Send a message, or reply with reply_to, from this authenticated environment. '
         'Default recipients are all other peers; stored is not delivered or executed.',
         ['id', 'correlation_id', 'text', 'recipients', 'reply_to'], ['id', 'correlation_id', 'text'], False),
    tool('kelion_channel_read', 'Read this authenticated environment inbox. Read new messages at session start; '
         'acknowledge only after receiving the actual text. Does not mark messages read automatically.',
         ['after', 'limit', 'unread_only'], [], True),
    tool('kelion_channel_ack', 'Acknowledge receipt of exact message bytes by hash, for this environment only. '
         'This is receipt, not task completion or an agent result.', ['id', 'sha256'], ['id', 'sha256'], False),
    tool('kelion_channel_get', 'Read a visible message and its independent recipient acknowledgements.',
         ['id'], ['id'], True),
]


def rpc_error(identity, code, message):
    return {'jsonrpc': '2.0', 'id': identity, 'error': {'code': code, 'message': message}}


def inbox(channel, participant, **params):
    rows = channel.read(participant, **params)
    selected, used = [], 0
    # Bound structured JSON so its duplicated MCP text representation also
    # remains below the client response cap, even for escaped control bytes.
    for row in rows:
        size = len(json.dumps(row, ensure_ascii=False).encode())
        if selected and used + size > 1024 * 1024:
            break
        selected.append(row)
        used += size
    after = selected[-1]['sequence'] if selected else params.get('after', 0)
    more = len(selected) < len(rows)
    if selected and not more:
        more = bool(channel.read(participant, after=after, limit=1,
                                 unread_only=params.get('unread_only', False)))
    return {'messages': selected, 'next_after': after, 'has_more': more}


def mcp(channel, participant, message):
    if not isinstance(message, dict) or message.get('jsonrpc') != '2.0' or not isinstance(message.get('method'), str):
        return rpc_error(None, -32600, 'Invalid JSON-RPC request')
    if 'id' not in message:
        return None  # Notifications never execute mutation tools.
    identity = message['id']
    if type(identity) not in (int, str):
        return rpc_error(None, -32600, 'Invalid request identity')
    params = message.get('params', {})
    if not isinstance(params, dict):
        return rpc_error(identity, -32602, 'Params must be an object')
    method = message['method']
    if method == 'initialize':
        if not isinstance(params.get('protocolVersion'), str) or not isinstance(params.get('capabilities'), dict) or not isinstance(params.get('clientInfo'), dict):
            return rpc_error(identity, -32602, 'Initialize requires protocolVersion, capabilities, clientInfo')
        version = params['protocolVersion']
        result = {'protocolVersion': version if version in VERSIONS else VERSIONS[-1],
                  'capabilities': {'tools': {'listChanged': False}},
                  'serverInfo': {'name': 'kelion-shared-channel', 'version': '1.0.0'},
                  'instructions': 'At session start read the inbox and acknowledge exact received messages. '
                    'Use stable IDs and reply_to for responses. Client identity comes from authentication. '
                    'No automatic injection into unrelated ChatGPT/Work conversations or model execution.'}
    elif method == 'ping':
        result = {}
    elif method == 'tools/list':
        if not set(params) <= {'cursor', '_meta'} or params.get('cursor') not in (None, ''):
            return rpc_error(identity, -32602, 'Invalid cursor or fields')
        result = {'tools': TOOLS}
    elif method == 'tools/call':
        if 'name' not in params or not set(params) <= {'name', 'arguments', '_meta'} or not isinstance(params.get('arguments', {}), dict):
            return rpc_error(identity, -32602, 'tools/call requires name and arguments')
        name, args = params['name'], params.get('arguments', {})
        specs = {spec['name']: spec for spec in TOOLS}
        if not isinstance(name, str) or name not in specs:
            return rpc_error(identity, -32602, 'Unknown channel tool')
        schema = specs[name]['inputSchema']
        if not set(schema['required']) <= args.keys() or not set(args) <= schema['properties'].keys():
            return rpc_error(identity, -32602, 'Invalid tool arguments')
        try:
            if name == 'kelion_channel_send':
                data = channel.send(participant, args)
            elif name == 'kelion_channel_read':
                data = inbox(channel, participant, **args)
            elif name == 'kelion_channel_ack':
                data = channel.acknowledge(participant, args['id'], args['sha256'])
            else:
                data = channel.get(participant, args['id'])
            result = {'content': [{'type': 'text', 'text': json.dumps(data, ensure_ascii=False)}],
                      'structuredContent': data, 'isError': False}
        except ChannelError as error:
            result = {'content': [{'type': 'text', 'text': str(error)}], 'isError': True}
    else:
        return rpc_error(identity, -32601, 'Method not found')
    return {'jsonrpc': '2.0', 'id': identity, 'result': result}


def public_host(origin):
    if origin is None:
        return None
    parsed = urlsplit(origin)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.path not in ('', '/') or parsed.query or parsed.fragment:
        raise ValueError('Public origin must be an HTTPS origin without credentials or path')
    return parsed.netloc.lower()


WELL_KNOWN_RESOURCE_PREFIXES = ('/.well-known/oauth-protected-resource/kelion-channel/mcp',
                                '/.well-known/oauth-protected-resource/mcp', '/.well-known/oauth-protected-resource')
MCP_IDENTITY_PATHS = {'/mcp/chatgpt': 'chatgpt', '/mcp/work': 'work', '/mcp/kelion': 'kelion'}
WELL_KNOWN_AS = ('/.well-known/oauth-authorization-server', '/.well-known/oauth-authorization-server/kelion-channel',
                 '/.well-known/openid-configuration', '/.well-known/openid-configuration/kelion-channel')


def make_server(path, owner, tokens, *, port=8778, public_origin=None, oauth=None):
    if not isinstance(tokens, dict) or not set(PARTICIPANTS) <= set(tokens) or not set(tokens) <= set(PARTICIPANTS) | set(OPTIONAL_PARTICIPANTS):
        raise ValueError('Separate credentials required for ' + ', '.join(PARTICIPANTS)
                         + ' (optional, each with its own credential: ' + ', '.join(OPTIONAL_PARTICIPANTS) + ')')
    if any(not isinstance(value, str) or len(value) < 32 or len(value) > 256 or not value.isascii() or any(c.isspace() for c in value) for value in tokens.values()):
        raise ValueError('Each credential must contain 32..256 nonblank ASCII characters')
    if len(set(tokens.values())) != len(tokens):
        raise ValueError('Every environment requires a distinct credential')
    external_host = public_host(public_origin)
    canonical_origin = 'https://' + external_host if external_host else None
    active = tuple(sorted(tokens))
    channel = SharedChannel(path, owner, active)

    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def log_message(self, *_):
            pass  # Never log credentials, message text or URL parameters.

        def respond(self, status, data=None, headers=None, content_type='application/json; charset=utf-8', raw=None):
            body = raw if raw is not None else (b'' if data is None else json.dumps(data, ensure_ascii=False).encode())
            self.send_response(status)
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            if status == 401 and oauth is not None and 'WWW-Authenticate' not in (headers or {}):
                self.send_header('WWW-Authenticate', oauth.www_authenticate(MCP_IDENTITY_PATHS.get(urlsplit(self.path).path)))
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Connection', 'close')
            self.end_headers()
            if body:
                self.wfile.write(body)
            self.close_connection = True

        def process(self):
            self.connection.settimeout(10)
            try:
                host = self.headers.get('Host', '').lower()
                allowed_hosts = {'127.0.0.1:' + str(self.server.server_port), 'localhost:' + str(self.server.server_port)}
                if external_host:
                    allowed_hosts.add(external_host)
                if len(self.headers.get_all('Host', [])) != 1 or host not in allowed_hosts:
                    return self.respond(403, {'error': 'Invalid Host'})
                origin = self.headers.get('Origin')
                if origin is not None and origin not in {'http://127.0.0.1:' + str(self.server.server_port), canonical_origin}:
                    return self.respond(403, {'error': 'Invalid Origin'})
                url = urlsplit(self.path)
                if url.fragment:
                    raise ChannelError('Fragments not allowed')
                if oauth is not None:
                    handled = self.oauth_route(url)
                    if handled:
                        return
                if len(self.headers.get_all('Authorization', [])) != 1:
                    return self.respond(401, {'error': 'Authentication required'})
                authorization = self.headers.get('Authorization', '')
                principal = None
                for name, token in tokens.items():
                    if hmac.compare_digest(authorization.encode(), ('Bearer ' + token).encode()):
                        principal = name
                if principal is None and oauth is not None and authorization.startswith('Bearer '):
                    principal = oauth.principal(authorization[7:])
                if principal is None:
                    return self.respond(401, {'error': 'Authentication required'})
                if self.command == 'GET':
                    if url.path == '/v1/health' and not url.query:
                        return self.respond(200, {'status': 'ok', 'participant': principal,
                            'participants': list(active), 'delivery_mode': 'authenticated_client_readback',
                            'model_execution': False, 'automatic_conversation_injection': False})
                    if url.path == '/v1/inbox':
                        query = parse_qs(url.query, keep_blank_values=True)
                        if not set(query) <= {'after', 'limit', 'unread_only'} or any(len(v) != 1 for v in query.values()):
                            raise ChannelError('Invalid inbox parameters')
                        params = {}
                        for key in ('after', 'limit'):
                            if key in query:
                                if not query[key][0].isdecimal():
                                    raise ChannelError('Integer inbox parameter required')
                                params[key] = int(query[key][0])
                        if 'unread_only' in query:
                            if query['unread_only'][0] not in ('true', 'false'):
                                raise ChannelError('unread_only must be true or false')
                            params['unread_only'] = query['unread_only'][0] == 'true'
                        return self.respond(200, inbox(channel, principal, **params))
                    if url.path.startswith('/v1/message/') and not url.query:
                        return self.respond(200, channel.get(principal, url.path.removeprefix('/v1/message/')))
                    return self.respond(404, {'error': 'Unknown endpoint'})
                if self.command != 'POST':
                    return self.respond(405, {'error': 'Method not allowed'})
                if url.query:
                    raise ChannelError('POST query parameters not allowed')
                if self.headers.get('Transfer-Encoding') is not None or len(self.headers.get_all('Content-Length', [])) != 1:
                    raise ChannelError('Single bounded Content-Length required')
                length = self.headers['Content-Length']
                if not length.isdecimal() or not 0 < int(length) <= MAX_BODY:
                    return self.respond(413, {'error': 'Body size must be 1..262144 bytes'})
                if self.headers.get_content_type() != 'application/json':
                    return self.respond(415, {'error': 'Content-Type application/json required'})
                raw = self.rfile.read(int(length))
                if len(raw) != int(length):
                    raise ChannelError('Incomplete body')
                try:
                    body = json.loads(raw)
                except (ValueError, UnicodeError):
                    raise ChannelError('Invalid JSON') from None
                if not isinstance(body, dict):
                    raise ChannelError('JSON object required')
                if url.path == '/v1/messages':
                    return self.respond(201, channel.send(principal, body))
                if url.path == '/v1/ack':
                    if set(body) != {'id', 'sha256'}:
                        raise ChannelError('Acknowledgement requires id and sha256 only')
                    return self.respond(200, channel.acknowledge(principal, body['id'], body['sha256']))
                if url.path in MCP_IDENTITY_PATHS and principal != MCP_IDENTITY_PATHS[url.path]:
                    return self.respond(403, {'error': 'This connector URL belongs to another identity'})
                if url.path == '/mcp' or url.path in MCP_IDENTITY_PATHS:
                    accept = {part.strip().split(';')[0] for part in self.headers.get('Accept', '').split(',')}
                    if not {'application/json', 'text/event-stream'} <= accept:
                        return self.respond(406, {'error': 'Accept application/json and text/event-stream required'})
                    version = self.headers.get('MCP-Protocol-Version', VERSIONS[0])
                    if version not in VERSIONS:
                        raise ChannelError('Unsupported MCP protocol version')
                    result = mcp(channel, principal, body)
                    return self.respond(202 if result is None else 200, result)
                return self.respond(404, {'error': 'Unknown endpoint'})
            except OAuthError as error:
                self.respond(error.status, {'error': error.error, 'error_description': error.description})
            except ChannelError as error:
                self.respond(400, {'error': str(error)})
            except Exception:
                self.respond(500, {'error': 'Channel service error'})

        def read_form(self):
            if self.headers.get('Transfer-Encoding') is not None or len(self.headers.get_all('Content-Length', [])) != 1:
                raise OAuthError('invalid_request', 'Single bounded Content-Length required')
            length = self.headers['Content-Length']
            if not length.isdecimal() or not 0 < int(length) <= 16384:
                raise OAuthError('invalid_request', 'Body size must be 1..16384 bytes')
            raw = self.rfile.read(int(length))
            kind = self.headers.get_content_type()
            if kind == 'application/x-www-form-urlencoded':
                return parse_qs(raw.decode('utf-8', 'strict'), keep_blank_values=True, max_num_fields=20)
            if kind == 'application/json':
                body = json.loads(raw)
                if not isinstance(body, dict):
                    raise OAuthError('invalid_request', 'JSON object required')
                return body
            raise OAuthError('invalid_request', 'Unsupported Content-Type')

        def oauth_route(self, url):
            # Public discovery and token endpoints; the consent page needs the owner's proxy sign-in.
            path = url.path
            if self.command == 'GET':
                for prefix in WELL_KNOWN_RESOURCE_PREFIXES:
                    if path == prefix or path.startswith(prefix + '/'):
                        rest = path[len(prefix):].strip('/')
                        if rest.startswith('mcp/'):
                            rest = rest[4:]
                        if rest and rest not in MCP_IDENTITY_PATHS.values():
                            break
                        self.respond(200, oauth.protected_resource(rest or None))
                        return True
            if self.command == 'GET' and path in WELL_KNOWN_AS:
                self.respond(200, oauth.authorization_server())
                return True
            if path == '/oauth/register' and self.command == 'POST':
                body = self.read_form()
                if not isinstance(body, dict) or isinstance(body.get('redirect_uris'), str):
                    raise OAuthError('invalid_client_metadata', 'JSON client metadata required')
                self.respond(201, oauth.register(body))
                return True
            if path == '/oauth/token' and self.command == 'POST':
                form = self.read_form()
                if not isinstance(form, dict) or not all(isinstance(v, list) for v in form.values()):
                    raise OAuthError('invalid_request', 'Form-encoded body required')
                self.respond(200, oauth.token(form), headers={'Pragma': 'no-cache'})
                return True
            if path == '/oauth/authorize' and self.command == 'GET':
                if not oauth.owner_ok(self.headers):
                    self.respond(403, {'error': 'access_denied', 'error_description': 'Owner sign-in through kelionai.app required'})
                    return True
                request = oauth.validate_request(parse_qs(url.query, keep_blank_values=True, max_num_fields=20))
                self.respond(302, headers={'Location': oauth.approve(request)})
                return True
            return False

        do_GET = do_POST = do_PUT = do_DELETE = do_OPTIONS = process

    return ThreadingHTTPServer(('127.0.0.1', port), Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', required=True, type=Path)
    parser.add_argument('--owner', required=True)
    parser.add_argument('--port', type=int, default=8778)
    parser.add_argument('--public-origin')
    args = parser.parse_args()
    tokens = {peer: os.environ.get('KELION_CHANNEL_' + peer.upper() + '_TOKEN', '') for peer in PARTICIPANTS}
    for peer in OPTIONAL_PARTICIPANTS:   # an optional identity is enabled only by its own configured credential
        if os.environ.get('KELION_CHANNEL_' + peer.upper() + '_TOKEN', ''):
            tokens[peer] = os.environ['KELION_CHANNEL_' + peer.upper() + '_TOKEN']
    os.umask(0o077)
    oauth = None
    if args.public_origin:
        oauth = OAuthServer(args.state.with_name(args.state.stem + '.oauth.sqlite'), args.public_origin,
                            proxy_secret=os.environ.get('KELION_CHANNEL_PROXY_SECRET', ''),
                            owner_emails=os.environ.get('KELION_CHANNEL_OWNER_EMAILS', '').split(','))
    server = make_server(args.state, args.owner, tokens, port=args.port, public_origin=args.public_origin, oauth=oauth)
    # Keep signal handling in the main thread; serve_forever runs in a child thread.
    import threading
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    print(json.dumps({'status': 'listening', 'host': '127.0.0.1', 'port': server.server_port,
                      'model_execution': False, 'clients_must_connect': True}), flush=True)
    try:
        stop.wait()
    finally:
        server.shutdown()
        server.server_close()
        worker.join(10)


if __name__ == '__main__':
    main()
