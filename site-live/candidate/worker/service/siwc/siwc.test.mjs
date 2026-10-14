import test from 'node:test';
import assert from 'node:assert/strict';
import { generateKeyPairSync, sign, randomUUID, randomBytes } from 'node:crypto';
import { promises as fs } from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { createAttempt, authorizationURL, consumeCallback, validateIdToken, credentialsFromResponse, loadJWKS, tokenRequest, ISSUER, AUTHORIZE, TOKEN, DISCOVERY, SCOPES, SiwcError } from './oauth.mjs';
import { generateRecipient, encryptTransfer, decryptTransfer, checkPosixStat, assertPrivateDirectory, Vault } from './crypto-store.mjs';
import { providerArgs, childEnvironment, INITIALIZE, validateReady, responseContract, refreshRecord, withProviderSession } from './provider.mjs';
import { registrationMetadata, selectRegistration } from './cli.mjs';

const rsa = generateKeyPairSync('rsa', { modulusLength: 2048 });
const jwk = { ...rsa.publicKey.export({ format: 'jwk' }), kid: 'synthetic', alg: 'RS256', use: 'sig' };
const jwks = { keys: [jwk] }, clientId = 'oaiapp_synthetic';
const attempt = () => createAttempt({ hostId: randomUUID(), port: 1455 });
const claims = (a, extra = {}) => ({ iss: ISSUER, aud: clientId, sub: 'synthetic-subject', iat: Math.floor(Date.now() / 1000) - 10, exp: Math.floor(Date.now() / 1000) + 3600, nonce: a.nonce, ...extra });
function jwt(c, header = {}) { const h = Buffer.from(JSON.stringify({ alg: 'RS256', kid: 'synthetic', ...header })).toString('base64url'); const p = Buffer.from(JSON.stringify(c)).toString('base64url'); const input = `${h}.${p}`; return `${input}.${sign('RSA-SHA256', Buffer.from(input), rsa.privateKey).toString('base64url')}`; }
const response = (a, extra = {}) => ({ access_token: 'synthetic-access', refresh_token: 'synthetic-refresh', id_token: jwt(claims(a)), token_type: 'Bearer', expires_in: 3600, scope: SCOPES.join(' '), ...extra });
const record = () => { const a = attempt(); return credentialsFromResponse(response(a), { identity: claims(a), clientId, hostId: a.hostId, nonce: a.nonce }); };
const callback = (a, extra = {}) => `${a.redirectUri}?${new URLSearchParams({ state: a.state, code: 'synthetic-code', client_id: clientId, ...extra })}`;
const json = value => new Response(JSON.stringify(value), { status: 200, headers: { 'Content-Type': 'application/json' } });

test('PKCE/state/nonce entropy and exact official authorization contract', () => {
  const a = attempt(), b = attempt(), u = new URL(authorizationURL(a));
  assert.notEqual(a.state, b.state); assert.notEqual(a.nonce, a.state); assert.match(a.verifier, /^[\w-]{43}$/);
  assert.equal(u.origin + u.pathname, AUTHORIZE); assert.equal(u.searchParams.get('agent_name_hint'), INITIALIZE.params.clientInfo.name);
  assert.equal(u.searchParams.get('code_challenge_method'), 'S256'); assert.equal(u.searchParams.get('redirect_uri'), 'http://127.0.0.1:1455/auth/callback');
  assert.equal(u.searchParams.get('client_id'), 'dynamic_agent_client'); assert.deepEqual(u.searchParams.get('scope').split(' '), SCOPES);
});
test('callback requires issued client_id, exact state/path and single use', () => {
  for (const overrides of [{ state: 'wrong' }, { client_id: '' }, { client_id: 'dynamic_agent_client' }]) { const a = attempt(); assert.throws(() => consumeCallback(a, callback(a, overrides))); }
  const a = attempt(); assert.throws(() => consumeCallback(a, callback(a).replace('/auth/callback', '/callback')));
  assert.equal(consumeCallback(a, callback(a)).clientId, clientId); assert.throws(() => consumeCallback(a, callback(a)));
});
test('callback duplicate, expired and denied never yield a code', () => {
  const a = attempt(); assert.throws(() => consumeCallback(a, callback(a) + '&state=extra'));
  assert.throws(() => consumeCallback(a, callback(a), a.expiresAt));
  assert.throws(() => consumeCallback(a, callback(a, { error: 'access_denied' })), /authorization_declined/);
});
test('returning registration omits name hint and rejects replacement client', () => {
  const a = createAttempt({ hostId: randomUUID(), port: 32100, selected: { client_id: clientId, subject: 'synthetic-subject', issuer: ISSUER } });
  const u = new URL(authorizationURL(a)); assert.equal(u.searchParams.has('agent_name_hint'), false);
  assert.throws(() => consumeCallback(a, callback(a, { client_id: 'oaiapp_other' })), /client_id_mismatch/);
});
test('valid synthetic signed ID token validates', () => { const a = attempt(); assert.equal(validateIdToken(jwt(claims(a)), { jwks, clientId, nonce: a.nonce }).sub, 'synthetic-subject'); });
test('ID claims reject issuer/audience/nonce/subject/time/azp attacks', () => {
  const a = attempt();
  for (const extra of [{ iss: 'https://attacker.test' }, { aud: 'other' }, { nonce: 'wrong' }, { sub: '' }, { exp: 1 }, { iat: 9999999999 }, { nbf: 9999999999 }, { aud: [clientId, 'other'] }, { azp: 'other' }]) assert.throws(() => validateIdToken(jwt(claims(a, extra)), { jwks, clientId, nonce: a.nonce }));
  assert.throws(() => validateIdToken(jwt(claims(a)), { jwks, clientId, nonce: a.nonce, expectedSubject: 'other' }));
});
test('JWT alg/key URL/critical headers, bad signature and duplicate kid fail closed', () => {
  const a = attempt();
  for (const h of [{ alg: 'none' }, { alg: 'HS256' }, { jku: 'https://attacker.test/jwks' }, { jwk }, { crit: ['evil'] }, { kid: 'unknown' }]) assert.throws(() => validateIdToken(jwt(claims(a), h), { jwks, clientId, nonce: a.nonce }));
  const good = jwt(claims(a)); const pieces = good.split('.'); pieces[2] = randomBytes(256).toString('base64url');
  assert.throws(() => validateIdToken(pieces.join('.'), { jwks, clientId, nonce: a.nonce }));
  assert.throws(() => validateIdToken(good, { jwks: { keys: [jwk, jwk] }, clientId, nonce: a.nonce }));
});
test('JWKS discovery pins origin/path and does not follow attacker location', async () => {
  let calls = 0;
  await assert.rejects(loadJWKS(async url => { calls++; assert.equal(url, DISCOVERY); return json({ issuer: ISSUER, authorization_endpoint: AUTHORIZE, token_endpoint: TOKEN, jwks_uri: 'https://attacker.test/jwks' }); }), /untrusted_jwks_uri/);
  assert.equal(calls, 1);
  const loaded = await loadJWKS(async (url, opts) => { assert.equal(opts.redirect, 'error'); return json(url === DISCOVERY ? { issuer: ISSUER, authorization_endpoint: AUTHORIZE, token_endpoint: TOKEN, jwks_uri: `${ISSUER}/.well-known/jwks.json` } : jwks); });
  assert.equal(loaded.keys[0].kid, 'synthetic');
});
test('token endpoint uses form POST and errors never include response secrets', async () => {
  await assert.rejects(tokenRequest({ grant_type: 'refresh_token' }, async (url, opts) => { assert.equal(url, TOKEN); assert.equal(opts.method, 'POST'); assert.equal(opts.redirect, 'error'); return new Response(JSON.stringify({ error: 'invalid_grant', description: 'secret-not-to-log' }), { status: 400 }); }), e => e.code === 'invalid_grant' && !e.message.includes('secret'));
});
test('scopes are token-response permission, with no plan tier or catalog inference', () => {
  const a = attempt();
  for (const omitted of ['chatgpt.tokens.use.direct', 'resource.invoke', 'offline_access']) assert.throws(() => credentialsFromResponse(response(a, { scope: SCOPES.filter(x => x !== omitted).join(' ') }), { identity: claims(a), clientId, hostId: a.hostId, nonce: a.nonce }), /permission_missing/);
  const r = record(); validateReady(r); assert.equal('entitlement_verified' in r, false);
});
test('transfer round trip preserves VM host id and hides all grant fields', () => {
  const recipient = generateRecipient(), r = record(), envelope = encryptTransfer(r, recipient.public, recipient.public.fingerprint);
  const serialized = JSON.stringify(envelope); assert.equal(serialized.includes(r.access_token), false); assert.equal(serialized.includes(r.subject), false);
  const recovered = decryptTransfer(envelope, recipient.privateKey, recipient.public.host_id);
  assert.equal(recovered.access_token, r.access_token); assert.equal(recovered.ext_agent_host_id, recipient.public.host_id); assert.notEqual(recovered.ext_agent_host_id, r.ext_agent_host_id);
});
test('transfer rejects wrong fingerprint, recipient, host, expired and modified envelope', () => {
  const a = generateRecipient(), b = generateRecipient(), r = record();
  assert.throws(() => encryptTransfer(r, a.public, b.public.fingerprint), /recipient_not_authenticated/);
  const e = encryptTransfer(r, a.public, a.public.fingerprint);
  assert.throws(() => decryptTransfer(e, b.privateKey, a.public.host_id), /wrong_recipient/);
  assert.throws(() => decryptTransfer(e, a.privateKey, b.public.host_id));
  assert.throws(() => decryptTransfer(e, a.privateKey, a.public.host_id, e.metadata.expires_at));
  const modified = structuredClone(e); modified.metadata.id = randomUUID(); assert.throws(() => decryptTransfer(modified, a.privateKey, a.public.host_id));
});
test('POSIX owner-only stat checks reject links, shared mode, foreign uid', () => {
  const st = { uid: 1234, mode: 0o100600, nlink: 1, isFile: () => true, isSymbolicLink: () => false };
  checkPosixStat(st, { uid: 1234 });
  for (const extra of [{ mode: 0o100644 }, { uid: 1 }, { nlink: 2 }, { isSymbolicLink: () => true }]) assert.throws(() => checkPosixStat({ ...st, ...extra }, { uid: 1234 }));
});
test('Windows never treats POSIX mode bits as private ACL/DPAPI', { skip: process.platform !== 'win32' }, async () => { await assert.rejects(assertPrivateDirectory(process.cwd()), /windows_private_storage_requires_verified_dpapi_and_acl/); });
test('real POSIX encrypted vault, atomic restart and competing lock', { skip: process.platform === 'win32' }, async () => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'kelion-siwc-')); await fs.chmod(dir, 0o700);
  const key = randomBytes(32), a = new Vault(dir, key), b = new Vault(dir, key);
  try { await a.lock(async () => { await a.write({ record: record(), phase: 'stopped' }); await assert.rejects(b.lock(async () => {}), /locked/); }); assert.equal((await b.read()).phase, 'stopped'); const disk = await fs.readFile(path.join(dir, 'session.enc'), 'utf8'); assert.equal(disk.includes('synthetic-access'), false); } finally { a.close(); b.close(); await fs.rm(dir, { recursive: true, force: true }); }
});
test('provider arguments contain official provider only; child env excludes API/desktop secrets', () => {
  const r = record(), args = providerArgs(); assert.equal(args.includes(r.access_token), false); assert.match(args.join(' '), /requires_openai_auth=false/); assert.match(args.join(' '), /supports_websockets=false/);
  const env = childEnvironment(r, { codexHome: path.resolve('isolated-synthetic'), parentEnv: { PATH: 'safe', OPENAI_API_KEY: 'forbidden', CODEX_HOME: 'desktop', NODE_OPTIONS: 'injection' } });
  assert.equal(env.ACCESS_TOKEN, r.access_token); assert.equal(env.OPENAI_API_KEY, undefined); assert.equal(env.NODE_OPTIONS, undefined); assert.notEqual(env.CODEX_HOME, 'desktop');
});
test('Responses contract enforces store false/stream true/array and no audio/system input', () => {
  assert.deepEqual(responseContract({ model: 'controller-selected', input: [{ type: 'message', role: 'user', content: 'synthetic' }] }).store, false);
  for (const input of ['text', [{ type: 'input_audio' }], [{ type: 'message', role: 'system', content: 'bad' }]]) assert.throws(() => responseContract({ model: 'selected', input }));
});
test('refresh uses issued client, omitted scope, rotating replacement and retained identity', async () => {
  const r = record(); r.expires_at = Date.now() + 30000; const next = await refreshRecord(r, { fetcher: async (url, opts) => { assert.equal(opts.body.get('client_id'), clientId); assert.equal(opts.body.has('scope'), false); return json({ access_token: 'synthetic-new', refresh_token: 'synthetic-rotated', expires_in: 3600, token_type: 'Bearer' }); } });
  assert.equal(next.access_token, 'synthetic-new'); assert.equal(next.refresh_token, 'synthetic-rotated'); assert.equal(next.id_token, r.id_token);
});
test('early refresh rejects before network regardless of opaque earliest metadata', async () => { let called = false; await assert.rejects(refreshRecord({ ...record(), earliest_refresh_at: { opaque: 'unknown units' } }, { fetcher: async () => { called = true; } }), /refresh_too_early/); assert.equal(called, false); });
test('near-expiry refresh accepts opaque earliest metadata and retains returned value', async () => {
  const r = record(); r.expires_at = Date.now() + 20000; r.earliest_refresh_at = 'opaque-existing'; let calls = 0;
  const next = await refreshRecord(r, { fetcher: async () => { calls++; return json({ access_token: 'synthetic-new', refresh_token: 'synthetic-rotated', expires_in: 3600, token_type: 'Bearer', earliest_refresh_at: { opaque: 'server-metadata' } }); } });
  assert.equal(calls, 1); assert.deepEqual(next.earliest_refresh_at, { opaque: 'server-metadata' });
});
test('initialize negotiates experimental API; private adapter receives negotiation and must acknowledge before initialized', () => {
  assert.equal(INITIALIZE.method, 'initialize'); assert.equal(INITIALIZE.params.capabilities.experimentalApi, true); assert.equal(INITIALIZE.params.clientInfo.name, 'KelionAI');
});
test('CLI registration selector persists no token and reuses exact client/account/local host', async () => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'siwc-selector-'));
  const file = path.join(dir, 'synthetic-registration.json'), r = record();
  try {
    assert.equal(await selectRegistration(file, r.ext_agent_host_id), null);
    const metadata = registrationMetadata(r, r.ext_agent_host_id);
    assert.deepEqual(Object.keys(metadata).sort(), ['schema', 'issuer', 'subject', 'client_id', 'local_host_id'].sort());
    assert.equal(JSON.stringify(metadata).includes(r.access_token), false);
    await fs.writeFile(file, JSON.stringify(metadata), { flag: 'wx' });
    const selected = await selectRegistration(file, r.ext_agent_host_id);
    const a = createAttempt({ hostId: r.ext_agent_host_id, port: 1455, selected }), b = createAttempt({ hostId: r.ext_agent_host_id, port: 1456, selected });
    const url = new URL(authorizationURL(a)); assert.equal(url.searchParams.get('client_id'), r.client_id); assert.equal(url.searchParams.has('agent_name_hint'), false); assert.equal(url.searchParams.has('id_token_hint'), false);
    assert.notEqual(a.state, b.state); assert.notEqual(a.nonce, b.nonce); assert.notEqual(a.verifier, b.verifier);
    await assert.rejects(selectRegistration(file, randomUUID()), /registration_selector_mismatch/);
    await fs.writeFile(file, JSON.stringify({ ...metadata, access_token: 'should-never-be-selector' }));
    await assert.rejects(selectRegistration(file, r.ext_agent_host_id), /registration_selector_mismatch/);
  } finally { await fs.rm(dir, { recursive: true, force: true }); }
});

class MemoryVault {
  constructor(state) { this.state = structuredClone(state); this.writes = []; this.held = false; }
  async lock(fn) { assert.equal(this.held, false); this.held = true; try { return await fn(); } finally { this.held = false; } }
  async read() { return structuredClone(this.state); }
  async write(value) { this.state = structuredClone(value); this.writes.push(value.phase); }
}
test('restart pending/running/uncertain states block child and refresh', async () => {
  for (const phase of ['running', 'refresh_pending', 'child_start_intent', 'needs_reconcile', 'reconciling']) {
    const vault = new MemoryVault({ phase, record: record() }); let used = false;
    await assert.rejects(withProviderSession({ vault, adapter: { reconcileBeforeResume: async () => { used = true; } } }), /restart_requires_reconciliation/); assert.equal(used, false);
  }
});
test('unknown prior turn reconciliation blocks spawning', async () => {
  const vault = new MemoryVault({ phase: 'stopped', record: record() }); let spawn = false;
  await assert.rejects(withProviderSession({ vault, adapter: { reconcileBeforeResume: async () => { throw new Error('synthetic unknown turn'); } }, spawnProviderFn: async () => { spawn = true; } }));
  assert.equal(spawn, false); assert.equal(vault.state.phase, 'reconciling');
});
test('refresh failure is durably stopped, terminal tokens removed, no automatic retry', async () => {
  const r = record(); r.expires_at = 1; const vault = new MemoryVault({ phase: 'stopped', record: r }); let spawn = false;
  await assert.rejects(withProviderSession({ vault, adapter: { reconcileBeforeResume: async () => {} }, refresh: async () => { throw new SiwcError('invalid_grant'); }, spawnProviderFn: async () => { spawn = true; } }), /refresh_failed_closed/);
  assert.equal(spawn, false); assert.equal(vault.state.phase, 'needs_reconcile'); assert.equal(vault.state.record.access_token, undefined); assert.equal(vault.state.record.status, 'reauthorization_required');
});
test('synthetic successful restart renews before child, initializes fixed app name, no turn replay', async () => {
  const r = record(); r.expires_at = 1; const vault = new MemoryVault({ phase: 'stopped', record: r }); const events = [];
  await withProviderSession({ vault, adapter: { reconcileBeforeResume: async () => events.push('reconcile'), usePrivateTransport: async (_child, init) => { events.push('initialize'); assert.equal(init.params.clientInfo.name, 'KelionAI'); return { initializeAcknowledged: true, initializedSent: true, reconciled: true, activeTurn: false }; } }, refresh: async () => { events.push('refresh'); return record(); }, spawnProviderFn: async () => { events.push('spawn'); return { exitCode: 0 }; } });
  assert.deepEqual(events, ['reconcile', 'refresh', 'spawn', 'initialize']); assert.equal(vault.state.phase, 'stopped'); assert.deepEqual(vault.writes, ['reconciling', 'refresh_pending', 'stopped', 'child_start_intent', 'running', 'stopped']);
});
test('transport return without confirmed readback cannot mark session stopped', async () => {
  const vault = new MemoryVault({ phase: 'stopped', record: record() });
  await assert.rejects(withProviderSession({ vault, adapter: { reconcileBeforeResume: async () => {}, usePrivateTransport: async () => undefined }, spawnProviderFn: async () => ({ exitCode: 0 }) }), /provider_failed_closed/);
  assert.equal(vault.state.phase, 'needs_reconcile');
});
test('adapter must confirm initialize acknowledgement and initialized notification', async () => {
  for (const flags of [{}, { initializeAcknowledged: true }, { initializedSent: true }]) {
    const vault = new MemoryVault({ phase: 'stopped', record: record() });
    await assert.rejects(withProviderSession({ vault, adapter: { reconcileBeforeResume: async () => {}, usePrivateTransport: async () => ({ ...flags, reconciled: true, activeTurn: false }) }, spawnProviderFn: async () => ({ exitCode: 0 }) }), /provider_failed_closed/);
    assert.equal(vault.state.phase, 'needs_reconcile');
  }
});
test('uncertain refresh preserves encrypted record but permanently gates automatic restart', async () => {
  const r = record(); r.expires_at = 1; const vault = new MemoryVault({ phase: 'stopped', record: r });
  await assert.rejects(withProviderSession({ vault, adapter: { reconcileBeforeResume: async () => {} }, refresh: async () => { throw new SiwcError('token_request_uncertain'); } }), /refresh_failed_closed/);
  assert.equal(vault.state.record.refresh_token, r.refresh_token); assert.equal(vault.state.phase, 'needs_reconcile');
  await assert.rejects(withProviderSession({ vault, adapter: {} }), /restart_requires_reconciliation/);
});
