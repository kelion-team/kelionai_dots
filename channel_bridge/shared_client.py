"""Authenticated CLI and MCP stdio relay. Credentials come only from environment.

There is no automatic retry of mutations: after a transport failure reconcile
with the original message ID. This client never invokes an AI model or executor.
"""
import argparse
import json
import os
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlencode
from urllib.request import Request, build_opener, HTTPRedirectHandler, ProxyHandler
from channel_bridge.shared import PARTICIPANTS

MAX_RESPONSE = 8 * 1024 * 1024
MAX_REQUEST = 262144


class ChannelClientError(ValueError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        raise ChannelClientError('Channel redirects are refused; verify the configured endpoint')


class ChannelClient:
    def __init__(self, base_url, token, *, expected_participant=None, timeout=15):
        if not isinstance(base_url, str):
            raise ChannelClientError('A channel base URL is required')
        parsed = urlsplit(base_url)
        local = parsed.scheme == 'http' and parsed.hostname in ('127.0.0.1', 'localhost')
        if (parsed.scheme != 'https' and not local) or not parsed.hostname or parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment:
            raise ChannelClientError('Use HTTPS, or HTTP loopback for local development, without URL credentials/query/fragment')
        if not isinstance(token, str) or not 32 <= len(token) <= 256 or not token.isascii() or any(c.isspace() for c in token):
            raise ChannelClientError('A configured channel credential is required')
        self.base = base_url.rstrip('/')
        self.token = token
        self.expected_participant = expected_participant
        self.timeout = timeout
        self._identity_checked = False
        # Direct connections are restricted to loopback. HTTPS always preserves
        # the environment proxy and CA trust used for injected credentials.
        self.http = build_opener(ProxyHandler({}), NoRedirect()) if local else build_opener(NoRedirect())

    def request(self, path, body=None, *, mcp=False):
        if self.expected_participant and not self._identity_checked and path != '/v1/health':
            self.health()
        headers = {'Authorization': 'Bearer ' + self.token, 'Accept': 'application/json'}
        encoded = None
        if body is not None:
            encoded = json.dumps(body, ensure_ascii=False).encode()
            if len(encoded) > MAX_REQUEST:
                raise ChannelClientError('Channel request exceeds size limit')
            headers['Content-Type'] = 'application/json'
        if mcp:
            headers['Accept'] = 'application/json, text/event-stream'
        try:
            with self.http.open(Request(self.base + path, data=encoded, headers=headers), timeout=self.timeout) as response:
                if response.status == 202:
                    return None
                raw = response.read(MAX_RESPONSE + 1)
                if len(raw) > MAX_RESPONSE:
                    raise ChannelClientError('Channel response exceeds size limit')
                try:
                    value = json.loads(raw)
                except (ValueError, UnicodeError):
                    raise ChannelClientError('Channel returned invalid JSON') from None
                if not isinstance(value, dict):
                    raise ChannelClientError('Channel returned an invalid response')
                return value
        except HTTPError as error:
            # Do not print URL, headers, body or server exception text.
            raise ChannelClientError('Channel request rejected: HTTP ' + str(error.code)) from None
        except (URLError, TimeoutError, OSError):
            raise ChannelClientError('Channel transport failed; delivery outcome unknown. Reconcile using the original message ID before retrying.') from None

    def health(self):
        health = self.request('/v1/health')
        if self.expected_participant and health.get('participant') != self.expected_participant:
            raise ChannelClientError('Authenticated channel participant does not match configuration')
        self._identity_checked = True
        return health

    def send(self, message):
        if self.expected_participant:
            self.health()
        sent = self.request('/v1/messages', message)
        if self.expected_participant and sent.get('sender') != self.expected_participant:
            raise ChannelClientError('Channel sender identity mismatch')
        return sent

    def read(self, *, after=0, limit=50, unread_only=False):
        return self.request('/v1/inbox?' + urlencode({'after': after, 'limit': limit,
                                                    'unread_only': str(unread_only).lower()}))

    def get(self, message_id):
        from channel_bridge.shared import identifier
        return self.request('/v1/message/' + identifier(message_id))

    def ack(self, message_id, sha256):
        return self.request('/v1/ack', {'id': message_id, 'sha256': sha256})

    def stdio(self):
        while True:
            raw = sys.stdin.buffer.readline(MAX_REQUEST + 1)
            if not raw:
                return
            if len(raw) > MAX_REQUEST:
                while raw and not raw.endswith(b'\n'):
                    raw = sys.stdin.buffer.readline(MAX_REQUEST + 1)
                value = {'jsonrpc': '2.0', 'id': None, 'error': {'code': -32600, 'message': 'Message size limit exceeded'}}
            else:
                identity = None
                try:
                    message = json.loads(raw)
                    if not isinstance(message, dict):
                        raise ValueError
                    identity = message.get('id')
                    value = self.request('/mcp', message, mcp=True)
                except (ValueError, UnicodeError) as error:
                    value = {'jsonrpc': '2.0', 'id': identity if type(identity) in (int, str) else None,
                             'error': {'code': -32000 if isinstance(error, ChannelClientError) else -32700,
                                       'message': str(error) if isinstance(error, ChannelClientError) else 'Invalid JSON'}}
            if value is not None:
                print(json.dumps(value, ensure_ascii=False), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default=os.environ.get('KELION_CHANNEL_URL'))
    parser.add_argument('--token-env', help='Private credential variable; defaults to the selected participant')
    parser.add_argument('--participant', required=True, choices=PARTICIPANTS)
    commands = parser.add_subparsers(dest='operation', required=True)
    commands.add_parser('health')
    commands.add_parser('stdio')
    read = commands.add_parser('read')
    read.add_argument('--after', type=int, default=0)
    read.add_argument('--limit', type=int, default=50)
    read.add_argument('--unread-only', action='store_true')
    get = commands.add_parser('get')
    get.add_argument('id')
    ack = commands.add_parser('ack')
    ack.add_argument('id')
    ack.add_argument('sha256')
    send = commands.add_parser('send')
    send.add_argument('--id', required=True)
    send.add_argument('--correlation-id', required=True)
    send.add_argument('--text', required=True)
    send.add_argument('--recipient', action='append')
    send.add_argument('--reply-to')
    args = parser.parse_args()
    try:
        token_env = args.token_env or 'KELION_CHANNEL_' + args.participant.upper() + '_TOKEN'
        client = ChannelClient(args.base_url, os.environ.get(token_env, ''), expected_participant=args.participant)
        if args.operation == 'stdio':
            client.stdio()
            return 0
        if args.operation == 'health':
            value = client.health()
        elif args.operation == 'read':
            value = client.read(after=args.after, limit=args.limit, unread_only=args.unread_only)
        elif args.operation == 'get':
            value = client.get(args.id)
        elif args.operation == 'ack':
            value = client.ack(args.id, args.sha256)
        else:
            body = {'id': args.id, 'correlation_id': args.correlation_id, 'text': args.text}
            if args.recipient:
                body['recipients'] = args.recipient
            if args.reply_to:
                body['reply_to'] = args.reply_to
            value = client.send(body)
        print(json.dumps(value, ensure_ascii=False))
        return 0
    except ChannelClientError as error:
        print(str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
