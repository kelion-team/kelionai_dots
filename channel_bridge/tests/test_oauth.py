import json
import secrets
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit, parse_qs
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler

from channel_bridge.oauth import OAuthServer, s256
from channel_bridge.shared_http import make_server

PEERS = ('chatgpt', 'work', 'kelion', 'cloud', 'contabo')
CALLBACK = 'https://chatgpt.com/connector/oauth/abc123'
SECRET = 'proxy-secret-' + 'x' * 40
OWNER = 'adrian@example.com'


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class OAuthTests(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.tokens = {p: secrets.token_urlsafe(32) for p in PEERS}
        self.now = [1000.0]
        self.oauth = OAuthServer(Path(d.name) / 'o.sqlite', 'https://kelionai.app', proxy_secret=SECRET,
                                 owner_emails=[OWNER], clock=lambda: self.now[0])
        self.server = make_server(Path(d.name) / 'c.sqlite', 'kelion', self.tokens, port=0,
                                  public_origin='https://kelionai.app', oauth=self.oauth)
        t = threading.Thread(target=self.server.serve_forever, daemon=True)
        t.start()
        self.addCleanup(lambda: (self.server.shutdown(), self.server.server_close(), t.join(3)))
        self.base = 'http://127.0.0.1:%d' % self.server.server_port
        self.http = build_opener(ProxyHandler({}), NoRedirect())

    def call(self, method, path, body=None, headers=None, form=False):
        h = dict(headers or {})
        data = None
        if body is not None:
            data = urlencode(body, doseq=True).encode() if form else json.dumps(body).encode()
            h['Content-Type'] = 'application/x-www-form-urlencoded' if form else 'application/json'
        try:
            with self.http.open(Request(self.base + path, data=data, headers=h, method=method), timeout=5) as r:
                raw = r.read()
                return r.status, dict(r.headers), raw
        except HTTPError as e:
            return e.code, dict(e.headers), e.read()

    def owner(self):
        return {'X-Kelion-Proxy-Auth': SECRET, 'X-Auth-Request-Email': OWNER}

    def register(self):
        st, _, raw = self.call('POST', '/oauth/register', {'redirect_uris': [CALLBACK], 'client_name': 'ChatGPT'})
        self.assertEqual(st, 201, raw)
        return json.loads(raw)['client_id']

    def authorize(self, client_id, verifier, resource='https://kelionai.app/kelion-channel/mcp', headers=None):
        params = {'response_type': 'code', 'client_id': client_id, 'redirect_uri': CALLBACK, 'state': 'st1',
                  'code_challenge': s256(verifier), 'code_challenge_method': 'S256'}
        if resource:
            params['resource'] = resource
        st, h, _ = self.call('GET', '/oauth/authorize?' + urlencode(params), headers=headers or self.owner())
        return st, h.get('Location')

    def connect(self, resource):
        client = self.register()
        verifier = secrets.token_urlsafe(48)
        st, location = self.authorize(client, verifier, resource)
        self.assertEqual(st, 302)
        code = parse_qs(urlsplit(location).query)['code'][0]
        st, _, raw = self.call('POST', '/oauth/token', {'grant_type': 'authorization_code', 'code': code, 'client_id': client,
                                                        'redirect_uri': CALLBACK, 'code_verifier': verifier}, form=True)
        self.assertEqual(st, 200, raw)
        return json.loads(raw)['access_token']

    def test_discovery_and_401_points_to_metadata(self):
        st, h, _ = self.call('POST', '/mcp', {'jsonrpc': '2.0', 'id': 1, 'method': 'ping'})
        self.assertEqual(st, 401)
        self.assertIn('resource_metadata="https://kelionai.app/kelion-channel/.well-known/oauth-protected-resource"',
                      h['WWW-Authenticate'])
        for path in ('/.well-known/oauth-protected-resource', '/.well-known/oauth-protected-resource/kelion-channel/mcp'):
            st, _, raw = self.call('GET', path)
            self.assertEqual(json.loads(raw)['authorization_servers'], ['https://kelionai.app/kelion-channel'])
        st, _, raw = self.call('GET', '/.well-known/oauth-authorization-server/kelion-channel')
        meta = json.loads(raw)
        self.assertEqual(meta['code_challenge_methods_supported'], ['S256'])
        self.assertEqual(meta['token_endpoint'], 'https://kelionai.app/kelion-channel/oauth/token')

    def test_full_flow_identity_refresh_and_mcp(self):
        client = self.register()
        verifier = secrets.token_urlsafe(48)
        _, location = self.authorize(client, verifier, 'https://kelionai.app/kelion-channel/mcp/work')
        params = parse_qs(urlsplit(location).query)
        self.assertTrue(location.startswith(CALLBACK + '?'))
        self.assertEqual(params['state'], ['st1'])
        self.assertEqual(params['iss'], ['https://kelionai.app/kelion-channel'])
        code = params['code'][0]
        st, _, raw = self.call('POST', '/oauth/token', {'grant_type': 'authorization_code', 'code': code, 'client_id': client,
                                                        'redirect_uri': CALLBACK, 'code_verifier': verifier}, form=True)
        self.assertEqual(st, 200, raw)
        tok = json.loads(raw)
        auth = {'Authorization': 'Bearer ' + tok['access_token']}
        st, _, raw = self.call('GET', '/v1/health', headers=auth)
        self.assertEqual(json.loads(raw)['participant'], 'work')
        st, _, raw = self.call('POST', '/mcp', {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'},
                               headers={**auth, 'Accept': 'application/json, text/event-stream'})
        self.assertEqual(st, 200)
        # code is single use
        st, _, _ = self.call('POST', '/oauth/token', {'grant_type': 'authorization_code', 'code': code, 'client_id': client,
                                                      'redirect_uri': CALLBACK, 'code_verifier': verifier}, form=True)
        self.assertEqual(st, 400)
        # refresh rotates and old refresh stops working
        st, _, raw = self.call('POST', '/oauth/token', {'grant_type': 'refresh_token', 'refresh_token': tok['refresh_token'],
                                                        'client_id': client}, form=True)
        self.assertEqual(st, 200)
        st, _, _ = self.call('POST', '/oauth/token', {'grant_type': 'refresh_token', 'refresh_token': tok['refresh_token'],
                                                      'client_id': client}, form=True)
        self.assertEqual(st, 400)
        # access token expires
        self.now[0] += 3601
        st, _, _ = self.call('GET', '/v1/health', headers=auth)
        self.assertEqual(st, 401)

    def test_wrong_verifier_rejected(self):
        client = self.register()
        _, location = self.authorize(client, secrets.token_urlsafe(48))
        code = parse_qs(urlsplit(location).query)['code'][0]
        st, _, _ = self.call('POST', '/oauth/token', {'grant_type': 'authorization_code', 'code': code, 'client_id': client,
                                                      'redirect_uri': CALLBACK, 'code_verifier': secrets.token_urlsafe(48)}, form=True)
        self.assertEqual(st, 400)

    def test_owner_required_and_forged_marker_refused(self):
        client = self.register()
        v = secrets.token_urlsafe(48)
        for headers in ({}, {'X-Auth-Request-Email': OWNER},
                        {'X-Kelion-Proxy-Auth': 'wrong' * 10, 'X-Auth-Request-Email': OWNER},
                        {'X-Kelion-Proxy-Auth': SECRET, 'X-Auth-Request-Email': 'other@example.com'}):
            st, _ = self.authorize(client, v, headers=headers or {'X-None': '1'})
            self.assertEqual(st, 403)

    def test_registration_only_chatgpt_callbacks(self):
        for uri in ('https://evil.example/cb', 'http://chatgpt.com/connector/oauth/x',
                    'https://chatgpt.com/connector/oauth/', 'https://chatgpt.com/connector/oauth/x?y=1'):
            st, _, _ = self.call('POST', '/oauth/register', {'redirect_uris': [uri]})
            self.assertEqual(st, 400, uri)

    def test_identity_comes_from_connector_url_automatically(self):
        for resource, who in (('https://kelionai.app/kelion-channel/mcp', 'chatgpt'), (None, 'chatgpt'),
                              ('https://kelionai.app/kelion-channel/mcp/kelion', 'kelion'),
                              ('https://kelionai.app/kelion-channel/mcp/work', 'work')):
            tok = self.connect(resource)
            st, _, raw = self.call('GET', '/v1/health', headers={'Authorization': 'Bearer ' + tok})
            self.assertEqual(json.loads(raw)['participant'], who, resource)

    def test_cloud_and_unknown_identities_never_grantable(self):
        client = self.register()
        for resource in ('https://kelionai.app/kelion-channel/mcp/cloud', 'https://kelionai.app/kelion-channel/mcp/contabo',
                         'https://evil.example/mcp'):
            st, _ = self.authorize(client, secrets.token_urlsafe(48), resource)
            self.assertEqual(st, 400, resource)

    def test_identity_path_enforced_on_mcp(self):
        tok = self.connect('https://kelionai.app/kelion-channel/mcp/work')
        hdr = {'Authorization': 'Bearer ' + tok, 'Accept': 'application/json, text/event-stream'}
        ping = {'jsonrpc': '2.0', 'id': 1, 'method': 'ping'}
        self.assertEqual(self.call('POST', '/mcp/work', ping, headers=hdr)[0], 200)
        self.assertEqual(self.call('POST', '/mcp/kelion', ping, headers=hdr)[0], 403)
        st, h, _ = self.call('POST', '/mcp/kelion', ping)
        self.assertEqual(st, 401)
        self.assertIn('/.well-known/oauth-protected-resource/mcp/kelion"', h['WWW-Authenticate'])
        st, _, raw = self.call('GET', '/.well-known/oauth-protected-resource/kelion-channel/mcp/kelion')
        self.assertEqual(json.loads(raw)['resource'], 'https://kelionai.app/kelion-channel/mcp/kelion')

    def test_static_tokens_still_work(self):
        st, _, raw = self.call('GET', '/v1/health', headers={'Authorization': 'Bearer ' + self.tokens['cloud']})
        self.assertEqual(json.loads(raw)['participant'], 'cloud')


if __name__ == '__main__':
    unittest.main()
