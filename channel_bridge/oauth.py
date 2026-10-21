"""OAuth 2.1 (authorization code + PKCE S256) for connecting ChatGPT apps to the shared channel.

The owner signs in through the existing HTTPS proxy (Google via oauth2-proxy). The
proxy adds a private header that only it knows, so a local process cannot forge the
owner's approval. The owner then picks which channel identity the connection gets
(chatgpt, work or kelion). Tokens are random, stored only as SHA-256 hashes, and map
to exactly one identity. Static bearer credentials keep working unchanged.

The identity is chosen automatically by the connector URL, never by a manual step:
  .../kelion-channel/mcp/chatgpt, .../mcp/work, .../mcp/kelion  (plain .../mcp means chatgpt)
When the owner is already signed in, authorization completes in one redirect.
"""
import base64
import hashlib
import hmac
import json
import secrets
import sqlite3
import threading
import time
from urllib.parse import urlencode, urlsplit

OAUTH_PARTICIPANTS = ('chatgpt', 'work', 'kelion')
DEFAULT_REDIRECT_PREFIXES = ('https://chatgpt.com/connector/oauth/', 'https://chat.openai.com/connector/oauth/')
CODE_TTL = 120
ACCESS_TTL = 3600
REFRESH_TTL = 30 * 86400
PENDING_TTL = 600
MAX_CLIENTS = 200


class OAuthError(Exception):
    def __init__(self, error, description, status=400):
        super().__init__(description)
        self.error, self.description, self.status = error, description, status


def _hash(value):
    return hashlib.sha256(value.encode()).hexdigest()


def s256(verifier):
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()


class OAuthServer:
    def __init__(self, path, public_origin, *, proxy_secret='', owner_emails=(), redirect_prefixes=DEFAULT_REDIRECT_PREFIXES,
                 base_path='/kelion-channel', clock=time.time):
        parsed = urlsplit(public_origin or '')
        if parsed.scheme != 'https' or not parsed.netloc:
            raise ValueError('OAuth requires the public HTTPS origin')
        self.origin = public_origin.rstrip('/')
        self.base = self.origin + base_path
        self.issuer = self.base
        self.resource = self.base + '/mcp'
        self.proxy_secret = proxy_secret or ''
        self.owner_emails = {e.strip().lower() for e in owner_emails if e.strip()}
        self.redirect_prefixes = tuple(p for p in redirect_prefixes if p.startswith('https://') and p.endswith('/'))
        self.clock = clock
        self.lock = threading.Lock()
        self.db = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS clients (id TEXT PRIMARY KEY, redirect_uris TEXT NOT NULL, name TEXT, created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS pending (csrf TEXT PRIMARY KEY, request TEXT NOT NULL, expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS codes (hash TEXT PRIMARY KEY, client_id TEXT NOT NULL, redirect_uri TEXT NOT NULL,
                challenge TEXT NOT NULL, participant TEXT NOT NULL, expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS tokens (hash TEXT PRIMARY KEY, kind TEXT NOT NULL, client_id TEXT NOT NULL,
                participant TEXT NOT NULL, expires REAL NOT NULL);
        ''')

    # ---------------------------------------------------------------- metadata
    @property
    def enabled(self):
        return bool(self.proxy_secret) and bool(self.owner_emails)

    def resource_for(self, participant=None):
        return self.resource + ('/' + participant if participant else '')

    def participant_for_resource(self, resource):
        """Identity from the connector URL; None when the resource is not this channel."""
        if resource is None:
            return 'chatgpt'
        resource = resource.rstrip('/')
        if resource == self.resource:
            return 'chatgpt'
        for participant in OAUTH_PARTICIPANTS:
            if resource == self.resource_for(participant):
                return participant
        return None

    def resource_metadata_url(self, participant=None):
        return self.base + '/.well-known/oauth-protected-resource' + ('/mcp/' + participant if participant else '')

    def www_authenticate(self, participant=None):
        return 'Bearer resource_metadata="' + self.resource_metadata_url(participant) + '"'

    def protected_resource(self, participant=None):
        return {'resource': self.resource_for(participant), 'authorization_servers': [self.issuer],
                'bearer_methods_supported': ['header'], 'scopes_supported': ['channel'],
                'resource_name': 'Kelion shared channel'}

    def authorization_server(self):
        return {'issuer': self.issuer,
                'authorization_endpoint': self.base + '/oauth/authorize',
                'token_endpoint': self.base + '/oauth/token',
                'registration_endpoint': self.base + '/oauth/register',
                'response_types_supported': ['code'],
                'grant_types_supported': ['authorization_code', 'refresh_token'],
                'code_challenge_methods_supported': ['S256'],
                'token_endpoint_auth_methods_supported': ['none'],
                'scopes_supported': ['channel'],
                'authorization_response_iss_parameter_supported': True}

    # ---------------------------------------------------------------- registration
    def _redirect_allowed(self, uri):
        if not isinstance(uri, str) or len(uri) > 512:
            return False
        parts = urlsplit(uri)
        return (parts.scheme == 'https' and not parts.query and not parts.fragment and not parts.username
                and any(uri.startswith(p) and len(uri) > len(p) for p in self.redirect_prefixes))

    def register(self, body):
        uris = body.get('redirect_uris')
        if not isinstance(uris, list) or not 1 <= len(uris) <= 5 or not all(self._redirect_allowed(u) for u in uris):
            raise OAuthError('invalid_redirect_uri', 'Redirect URIs must be ChatGPT connector callbacks')
        method = body.get('token_endpoint_auth_method', 'none')
        if method != 'none':
            raise OAuthError('invalid_client_metadata', 'Only public clients (token_endpoint_auth_method none) are supported')
        name = body.get('client_name') if isinstance(body.get('client_name'), str) else ''
        client_id = 'kc_' + secrets.token_urlsafe(24)
        with self.lock:
            if self.db.execute('SELECT COUNT(*) FROM clients').fetchone()[0] >= MAX_CLIENTS:
                raise OAuthError('invalid_client_metadata', 'Client registration limit reached')
            self.db.execute('INSERT INTO clients VALUES (?,?,?,?)', (client_id, json.dumps(uris), name[:100], self.clock()))
        return {'client_id': client_id, 'client_id_issued_at': int(self.clock()), 'redirect_uris': uris,
                'token_endpoint_auth_method': 'none', 'grant_types': ['authorization_code', 'refresh_token'],
                'response_types': ['code']}

    def _client(self, client_id):
        row = self.db.execute('SELECT redirect_uris FROM clients WHERE id=?', (client_id,)).fetchone() if isinstance(client_id, str) else None
        return json.loads(row[0]) if row else None

    # ---------------------------------------------------------------- owner authorization
    def owner_ok(self, headers):
        """True only when the request passed the proxy's sign-in and carries its private marker."""
        if not self.enabled:
            return False
        marks = headers.get_all('X-Kelion-Proxy-Auth', []) if hasattr(headers, 'get_all') else [headers.get('X-Kelion-Proxy-Auth')]
        emails = headers.get_all('X-Auth-Request-Email', []) if hasattr(headers, 'get_all') else [headers.get('X-Auth-Request-Email')]
        if len(marks) != 1 or len(emails) != 1 or not marks[0] or not emails[0]:
            return False
        return hmac.compare_digest(marks[0].encode(), self.proxy_secret.encode()) and emails[0].strip().lower() in self.owner_emails

    def validate_request(self, query):
        def one(key, required=True):
            values = query.get(key, [])
            if len(values) > 1 or (required and not values):
                raise OAuthError('invalid_request', 'Missing or repeated parameter: ' + key)
            return values[0] if values else None
        client_id = one('client_id')
        uris = self._client(client_id)
        if uris is None:
            raise OAuthError('invalid_client', 'Unknown client')
        redirect_uri = one('redirect_uri')
        if redirect_uri not in uris:
            raise OAuthError('invalid_request', 'redirect_uri not registered for this client')
        if one('response_type') != 'code':
            raise OAuthError('unsupported_response_type', 'Only response_type=code')
        challenge = one('code_challenge')
        if one('code_challenge_method') != 'S256' or not isinstance(challenge, str) or not 43 <= len(challenge) <= 128:
            raise OAuthError('invalid_request', 'PKCE S256 code_challenge required')
        participant = self.participant_for_resource(one('resource', required=False))
        if participant is None:
            raise OAuthError('invalid_target', 'Unknown resource')
        state = one('state', required=False) or ''
        if len(state) > 512:
            raise OAuthError('invalid_request', 'state too long')
        return {'client_id': client_id, 'redirect_uri': redirect_uri, 'challenge': challenge, 'state': state,
                'participant': participant}

    def approve(self, request):
        """Owner already signed in: issue the code for the identity named by the connector URL, no extra step."""
        code = secrets.token_urlsafe(32)
        with self.lock:
            self.db.execute('INSERT INTO codes VALUES (?,?,?,?,?,?)', (_hash(code), request['client_id'], request['redirect_uri'],
                                                                     request['challenge'], request['participant'], self.clock() + CODE_TTL))
        params = {'code': code, 'iss': self.issuer}
        if request['state']:
            params['state'] = request['state']
        return request['redirect_uri'] + '?' + urlencode(params)

    # ---------------------------------------------------------------- tokens
    def _issue(self, client_id, participant):
        access, refresh = secrets.token_urlsafe(40), secrets.token_urlsafe(40)
        now = self.clock()
        with self.lock:
            self.db.execute('DELETE FROM tokens WHERE expires < ?', (now,))
            self.db.execute('INSERT INTO tokens VALUES (?,?,?,?,?)', (_hash(access), 'access', client_id, participant, now + ACCESS_TTL))
            self.db.execute('INSERT INTO tokens VALUES (?,?,?,?,?)', (_hash(refresh), 'refresh', client_id, participant, now + REFRESH_TTL))
        return {'access_token': access, 'token_type': 'Bearer', 'expires_in': ACCESS_TTL,
                'refresh_token': refresh, 'scope': 'channel'}

    def token(self, form):
        def one(key):
            values = form.get(key, [])
            if len(values) != 1:
                raise OAuthError('invalid_request', 'Missing or repeated field: ' + key)
            return values[0]
        grant, client_id = one('grant_type'), one('client_id')
        if self._client(client_id) is None:
            raise OAuthError('invalid_client', 'Unknown client', 401)
        if grant == 'authorization_code':
            code, redirect_uri, verifier = one('code'), one('redirect_uri'), one('code_verifier')
            if not 43 <= len(verifier) <= 128:
                raise OAuthError('invalid_grant', 'Invalid code_verifier')
            with self.lock:
                row = self.db.execute('SELECT client_id, redirect_uri, challenge, participant, expires FROM codes WHERE hash=?',
                                      (_hash(code),)).fetchone()
                self.db.execute('DELETE FROM codes WHERE hash=?', (_hash(code),))   # single use, even when it fails
            if (not row or row[4] < self.clock() or row[0] != client_id or row[1] != redirect_uri
                    or not hmac.compare_digest(s256(verifier), row[2])):
                raise OAuthError('invalid_grant', 'Invalid, expired or already used authorization code')
            return self._issue(client_id, row[3])
        if grant == 'refresh_token':
            refresh = one('refresh_token')
            with self.lock:
                row = self.db.execute("SELECT client_id, participant, expires FROM tokens WHERE hash=? AND kind='refresh'",
                                      (_hash(refresh),)).fetchone()
                self.db.execute("DELETE FROM tokens WHERE hash=? AND kind='refresh'", (_hash(refresh),))   # rotation
            if not row or row[2] < self.clock() or row[0] != client_id:
                raise OAuthError('invalid_grant', 'Invalid or expired refresh token')
            return self._issue(client_id, row[1])
        raise OAuthError('unsupported_grant_type', 'Unsupported grant_type')

    def principal(self, bearer):
        if not isinstance(bearer, str) or not 20 <= len(bearer) <= 256:
            return None
        row = self.db.execute("SELECT participant, expires FROM tokens WHERE hash=? AND kind='access'", (_hash(bearer),)).fetchone()
        return row[0] if row and row[1] >= self.clock() and row[0] in OAUTH_PARTICIPANTS else None
