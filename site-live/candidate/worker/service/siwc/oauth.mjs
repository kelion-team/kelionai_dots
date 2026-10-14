import { randomBytes, createHash, timingSafeEqual, createPublicKey, verify } from 'node:crypto';

export const ISSUER = 'https://auth.openai.com';
export const AUTHORIZE = `${ISSUER}/api/accounts/authorize`;
export const TOKEN = `${ISSUER}/api/accounts/oauth/token`;
export const DISCOVERY = `${ISSUER}/.well-known/openid-configuration`;
export const RESOURCE = 'https://api.openai.com/v1';
export const APP_NAME = 'KelionAI';
export const SCOPES = ['openid', 'profile', 'email', 'offline_access', 'resource.invoke', 'chatgpt.tokens.use.direct'];
export class SiwcError extends Error { constructor(code) { super(code); this.code = code; } }
export const requireValue = (ok, code) => { if (!ok) throw new SiwcError(code); };
export const uuidOK = value => typeof value === 'string' && /^(?:urn:uuid:)?[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value);
const opaque = () => randomBytes(32).toString('base64url');
const equal = (a, b) => typeof a === 'string' && typeof b === 'string' && Buffer.byteLength(a) === Buffer.byteLength(b) && timingSafeEqual(Buffer.from(a), Buffer.from(b));
export const issuedClientOK = x => typeof x === 'string' && /^oaiapp_[A-Za-z0-9_-]{1,200}$/.test(x);

export function createAttempt({ hostId, port, selected = null, now = Date.now() }) {
  requireValue(uuidOK(hostId) && Number.isInteger(port) && port > 0 && port < 65536, 'invalid_host_or_port');
  requireValue(!selected || (issuedClientOK(selected.client_id) && selected.issuer === ISSUER && typeof selected.subject === 'string' && selected.subject.length > 0), 'invalid_selected_registration');
  const verifier = opaque();
  return { hostId, state: opaque(), nonce: opaque(), verifier, challenge: createHash('sha256').update(verifier).digest('base64url'), redirectUri: `http://127.0.0.1:${port}/auth/callback`, expiresAt: now + 600000, selected, consumed: false };
}

export function authorizationURL(attempt) {
  const p = new URLSearchParams({ client_id: attempt.selected?.client_id ?? 'dynamic_agent_client', ext_agent_host_id: attempt.hostId, response_type: 'code', redirect_uri: attempt.redirectUri, scope: SCOPES.join(' '), resource: RESOURCE, state: attempt.state, nonce: attempt.nonce, code_challenge_method: 'S256', code_challenge: attempt.challenge });
  if (!attempt.selected) p.set('agent_name_hint', APP_NAME);
  // Deliberately omit optional login hints: authorization URLs contain no retained token.
  return `${AUTHORIZE}?${p}`;
}

export function consumeCallback(attempt, callbackURL, now = Date.now()) {
  requireValue(!attempt.consumed && now < attempt.expiresAt, 'expired_or_consumed_attempt');
  const u = new URL(callbackURL);
  requireValue(`${u.origin}${u.pathname}` === attempt.redirectUri && !u.hash, 'callback_uri_mismatch');
  for (const name of ['state', 'code', 'client_id', 'error']) requireValue(u.searchParams.getAll(name).length <= 1, 'duplicate_callback_parameter');
  requireValue(equal(attempt.state, u.searchParams.get('state')), 'state_mismatch');
  attempt.consumed = true;
  requireValue(!u.searchParams.has('error'), 'authorization_declined');
  const clientId = u.searchParams.get('client_id') ?? attempt.selected?.client_id;
  requireValue(issuedClientOK(clientId), 'issued_client_id_required');
  requireValue(!attempt.selected || clientId === attempt.selected.client_id, 'client_id_mismatch');
  const code = u.searchParams.get('code');
  requireValue(typeof code === 'string' && code.length > 0 && code.length <= 8192, 'authorization_code_required');
  return { clientId, code };
}

async function jsonResponse(response) {
  requireValue(response.ok, 'oauth_http_failure');
  requireValue(Number(response.headers.get('content-length') ?? 0) <= 262144, 'response_too_large');
  const reader = response.body.getReader(); let length = 0; const chunks = [];
  try { for (;;) { const { value, done } = await reader.read(); if (done) break; length += value.length; requireValue(length <= 262144, 'response_too_large'); chunks.push(value); } }
  finally { await reader.cancel(); }
  try { return JSON.parse(Buffer.concat(chunks).toString('utf8')); } catch { throw new SiwcError('invalid_json_response'); }
}
async function getJSON(url, fetcher) { return jsonResponse(await fetcher(url, { redirect: 'error', signal: AbortSignal.timeout(15000), headers: { Accept: 'application/json' } })); }

// No JWT-controlled URL is fetched. Only pinned HTTPS discovery and same-origin JWKS.
export async function loadJWKS(fetcher = fetch) {
  const d = await getJSON(DISCOVERY, fetcher);
  requireValue(d.issuer === ISSUER && d.authorization_endpoint === AUTHORIZE && d.token_endpoint === TOKEN, 'discovery_mismatch');
  const u = new URL(d.jwks_uri);
  requireValue(u.origin === ISSUER && !u.username && !u.password && !u.hash && !u.search && u.pathname === '/.well-known/jwks.json', 'untrusted_jwks_uri');
  const jwks = await getJSON(u.href, fetcher);
  requireValue(Array.isArray(jwks.keys) && jwks.keys.length > 0 && jwks.keys.length <= 100, 'invalid_jwks');
  return jwks;
}

export function validateIdToken(token, { jwks, clientId, nonce, expectedSubject, now = Math.floor(Date.now() / 1000) }) {
  requireValue(typeof token === 'string' && token.length <= 32768, 'invalid_id_token');
  const parts = token.split('.');
  requireValue(parts.length === 3 && parts.every(x => /^[A-Za-z0-9_-]+$/.test(x)), 'invalid_id_token');
  let h, c;
  try { h = JSON.parse(Buffer.from(parts[0], 'base64url')); c = JSON.parse(Buffer.from(parts[1], 'base64url')); } catch { throw new SiwcError('invalid_id_token'); }
  requireValue(h.alg === 'RS256' && typeof h.kid === 'string' && !h.crit && !h.jku && !h.jwk && !h.x5u, 'unsupported_jwt_header');
  const matches = jwks.keys.filter(k => k.kid === h.kid);
  requireValue(matches.length === 1, 'unknown_or_ambiguous_kid');
  const k = matches[0];
  requireValue(k.kty === 'RSA' && (!k.alg || k.alg === 'RS256') && (!k.use || k.use === 'sig') && (!k.key_ops || (Array.isArray(k.key_ops) && k.key_ops.includes('verify'))) && !k.d, 'invalid_signing_key');
  let key;
  try { key = createPublicKey({ key: k, format: 'jwk' }); } catch { throw new SiwcError('invalid_signing_key'); }
  requireValue(key.asymmetricKeyDetails.modulusLength >= 2048 && verify('RSA-SHA256', Buffer.from(parts.slice(0, 2).join('.')), key, Buffer.from(parts[2], 'base64url')), 'invalid_id_signature');
  const aud = Array.isArray(c.aud) ? c.aud : [c.aud];
  requireValue(c.iss === ISSUER && issuedClientOK(clientId) && aud.includes(clientId) && (aud.length === 1 || c.azp === clientId) && (!c.azp || c.azp === clientId), 'identity_binding_mismatch');
  requireValue(Number.isInteger(c.exp) && c.exp > now && Number.isInteger(c.iat) && c.iat <= now + 5 && c.iat < c.exp && (c.nbf === undefined || (Number.isInteger(c.nbf) && c.nbf <= now + 5)), 'id_token_time_invalid');
  requireValue(typeof c.sub === 'string' && c.sub.length > 0 && (!expectedSubject || c.sub === expectedSubject), 'subject_mismatch');
  requireValue(typeof nonce === 'string' && equal(c.nonce, nonce), 'nonce_mismatch');
  return c;
}

export function credentialsFromResponse(t, { identity, clientId, hostId, nonce, previous = null, now = Date.now() }) {
  requireValue(t && typeof t.access_token === 'string' && t.access_token.length > 0 && typeof t.refresh_token === 'string' && t.refresh_token.length > 0 && t.token_type?.toLowerCase() === 'bearer', 'invalid_token_response');
  requireValue(Number.isInteger(t.expires_in) && t.expires_in > 0 && t.expires_in <= 86400 && typeof t.scope === 'string', 'invalid_expiry_or_scope');
  const scopes = [...new Set(t.scope.split(/\s+/).filter(Boolean))];
  // This worker requires renewable direct use; missing permission cannot reach a child.
  requireValue(['openid', 'offline_access', 'resource.invoke', 'chatgpt.tokens.use.direct'].every(s => scopes.includes(s)), 'chatgpt_plan_permission_missing');
  requireValue(issuedClientOK(clientId) && uuidOK(hostId), 'invalid_registration');
  if (previous) requireValue(previous.subject === identity.sub && previous.client_id === clientId, 'registration_mismatch');
  // earliest_refresh_at format is not specified in the fetched reference. Retain
  // it as opaque metadata; refresh follows the documented near-expiry rule.
  return { schema: 1, issuer: ISSUER, subject: identity.sub, email: typeof identity.email === 'string' ? identity.email : null, client_id: clientId, ext_agent_host_id: hostId, id_token: t.id_token ?? previous?.id_token, oidc_nonce: nonce, access_token: t.access_token, refresh_token: t.refresh_token, token_type: 'Bearer', scopes, saved_at: new Date(now).toISOString(), expires_at: now + t.expires_in * 1000, earliest_refresh_at: t.earliest_refresh_at ?? null, status: 'ready' };
}

export async function tokenRequest(fields, fetcher = fetch) {
  try {
    const response = await fetcher(TOKEN, { method: 'POST', redirect: 'error', signal: AbortSignal.timeout(15000), headers: { 'Content-Type': 'application/x-www-form-urlencoded', Accept: 'application/json' }, body: new URLSearchParams(fields) });
    if (!response.ok) {
      let code; try { const b = await jsonResponse({ ...response, ok: true, headers: response.headers, body: response.body }); code = b.error; } catch {}
      const terminal = ['invalid_grant', 'invalid_refresh_token', 'token_expired', 'refresh_token_expired', 'refresh_token_invalidated', 'refresh_token_reused', 'invalid_client'];
      throw new SiwcError(terminal.includes(code) ? code : 'token_request_failed');
    }
    return await jsonResponse(response);
  } catch (e) { if (e instanceof SiwcError) throw e; throw new SiwcError('token_request_uncertain'); }
}

export async function exchangeCode(attempt, callbackURL, { fetcher = fetch, jwksLoader = loadJWKS } = {}) {
  const { clientId, code } = consumeCallback(attempt, callbackURL);
  const t = await tokenRequest({ grant_type: 'authorization_code', client_id: clientId, code, code_verifier: attempt.verifier, redirect_uri: attempt.redirectUri, resource: RESOURCE }, fetcher);
  const identity = validateIdToken(t.id_token, { jwks: await jwksLoader(fetcher), clientId, nonce: attempt.nonce, expectedSubject: attempt.selected?.subject });
  return credentialsFromResponse(t, { identity, clientId, hostId: attempt.hostId, nonce: attempt.nonce, previous: attempt.selected });
}
