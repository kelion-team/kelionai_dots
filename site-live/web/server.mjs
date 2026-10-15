import http from 'node:http';
import { DatabaseSync } from 'node:sqlite';
import { readFileSync, mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { hash, random, HttpError, googleKeys, verifyGoogle } from './auth.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const fail = (status, message) => { throw new HttpError(status, message); };
const COOKIE = '__Host-kelion_session', LOGIN = '__Host-kelion_login';
function cookie(req, name) {
  const values = (req.headers.cookie ?? '').split(';').map(x => x.trim()).filter(x => x.startsWith(name + '='));
  return values.length === 1 && /^[A-Za-z0-9_-]{43}$/.test(values[0].slice(name.length + 1)) ? values[0].slice(name.length + 1) : '';
}
const setCookie = (name, value, age) => `${name}=${value}; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=${age}`;
async function body(req, max = 110000) {
  if (req.headers['content-type']?.split(';')[0] !== 'application/json') fail(415, 'JSON required');
  let size = 0; const chunks = [];
  for await (const chunk of req) { size += chunk.length; if (size > max) fail(413, 'Request too large'); chunks.push(chunk); }
  try { const data = JSON.parse(Buffer.concat(chunks)); if (!data || Array.isArray(data) || typeof data !== 'object') throw 0; return data; } catch { fail(400, 'Invalid JSON'); }
}
const AUDIO_TYPES = new Set(['audio/webm', 'audio/ogg', 'audio/wav', 'audio/mp4']);
async function audioBody(req) {
  const type = (req.headers['content-type'] ?? '').split(';')[0].trim();
  if (!AUDIO_TYPES.has(type)) fail(415, 'Audio required');
  let size = 0; const chunks = [];
  for await (const chunk of req) { size += chunk.length; if (size > 4 * 1024 * 1024) fail(413, 'Audio too large'); chunks.push(chunk); }
  if (!size) fail(400, 'Empty audio');
  return { type, data: Buffer.concat(chunks) };
}
export function createApp(config, { keys = googleKeys(), upstreamFetch = fetch } = {}) {
  if (config.publicOrigin !== 'https://kelionai.app') throw Error('Exact public HTTPS origin required');
  if (config.clientId && !/^[A-Za-z0-9_-]+\.apps\.googleusercontent\.com$/.test(config.clientId)) throw Error('Invalid Google client ID');
  const allowed = new Set((config.allowedEmails ?? []).map(e => e.toLowerCase()));
  if ([...allowed].some(e => !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(e))) throw Error('Invalid owner allowlist');
  const missing = [!config.clientId && 'GOOGLE_CLIENT_ID', !allowed.size && 'KELION_ALLOWED_EMAILS', !config.apiToken && 'KELION_CLIENT_TOKEN'].filter(Boolean);
  if (config.apiToken && !/^[A-Za-z0-9_-]{32,256}$/.test(config.apiToken)) throw Error('Invalid API credential');
  if (config.voiceToken && !/^[A-Za-z0-9_-]{32,256}$/.test(config.voiceToken)) throw Error('Invalid voice credential');
  if (config.maskToken && !/^[A-Za-z0-9_-]{32,256}$/.test(config.maskToken)) throw Error('Invalid mask credential');
  // Puntea măștii (loopback 8775): operațiile Codex app-server de pe kelion-nou, 1:1 după schemă.
  async function mask(path, data, timeout = 130000) {
    if (!config.maskToken) fail(503, 'Mask bridge not configured');
    let response;
    try { response = await upstreamFetch('http://127.0.0.1:8775' + path, { method: data ? 'POST' : 'GET', redirect: 'error', signal: AbortSignal.timeout(timeout),
      headers: { authorization: 'Bearer ' + config.maskToken, 'content-type': 'application/json' }, ...(data ? { body: JSON.stringify(data) } : {}) }); }
    catch { fail(502, 'Mask bridge unavailable'); }
    if (response.status === 404) { const e = await response.json().catch(() => ({})); fail(404, String(e.error || 'Not found').slice(0, 300)); }
    if (response.status === 400) { const e = await response.json().catch(() => ({})); fail(400, String(e.error || 'Invalid request').slice(0, 300)); }
    if (!response.ok) fail(502, 'Mask bridge unavailable');
    const text = await response.text(); if (text.length > 64 * 1024 * 1024) fail(502, 'Mask response too large');
    return JSON.parse(text);
  }
  // Serviciul DOTS de voce (loopback 8770): sunet → text (whisper.cpp) și text → sunet (piper), pe server.
  async function voice(path, init) {
    if (!config.voiceToken) fail(503, 'Voice service not configured');
    let response;
    try { response = await upstreamFetch('http://127.0.0.1:8770' + path, { ...init, redirect: 'error', signal: AbortSignal.timeout(120000),
      headers: { ...init.headers, authorization: 'Bearer ' + config.voiceToken } }); }
    catch { fail(502, 'Voice service unavailable'); }
    if (response.status === 422) { const e = await response.json().catch(() => ({})); fail(422, String(e.error || 'Voice processing failed').slice(0, 300)); }
    if (!response.ok) fail(502, 'Voice service unavailable');
    return response;
  }
  mkdirSync(dirname(config.database), { recursive: true, mode: 0o700 });
  const db = new DatabaseSync(config.database);
  db.exec(`PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL; PRAGMA busy_timeout=5000;
    CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, sub TEXT NOT NULL, email TEXT NOT NULL, csrf TEXT NOT NULL, expires INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS nonces (id TEXT PRIMARY KEY, nonce TEXT NOT NULL, expires INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, sub TEXT NOT NULL, created INTEGER NOT NULL, delivery TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS tasks_owner ON tasks(sub,created);
    CREATE TABLE IF NOT EXISTS auth_config (id INTEGER PRIMARY KEY CHECK(id=1), fingerprint TEXT NOT NULL);`);
  const prepared = sql => db.prepare(sql);
  // Configuration changes revoke login challenges and sessions, never owned task history.
  // Missing metadata also revokes pre-R3 sessions on the first upgraded start.
  const authFingerprint = hash(JSON.stringify([config.publicOrigin, config.clientId || '', [...allowed].sort()]));
  db.exec('BEGIN IMMEDIATE');
  try {
    if (prepared('SELECT fingerprint FROM auth_config WHERE id=1').get()?.fingerprint !== authFingerprint) {
      db.exec('DELETE FROM sessions; DELETE FROM nonces;');
      prepared('INSERT INTO auth_config VALUES(1,?) ON CONFLICT(id) DO UPDATE SET fingerprint=excluded.fingerprint').run(authFingerprint);
    }
    db.exec('COMMIT');
  } catch (error) { db.exec('ROLLBACK'); db.close(); throw error; }
  const cleanup = () => { const now = Date.now(); prepared('DELETE FROM sessions WHERE expires <= ?').run(now); prepared('DELETE FROM nonces WHERE expires <= ?').run(now); };
  const timer = setInterval(cleanup, 60000); timer.unref(); cleanup();
  // Global limits are intentional: only the configured owner uses this deployment.
  const buckets = new Map();
  function limit(key, maximum, window = 60000) {
    const now = Date.now(); let b = buckets.get(key);
    if (!b || now >= b.until) { b = { count: 0, until: now + window }; buckets.set(key, b); }
    if (++b.count > maximum) fail(429, 'Rate limit; try later');
  }
  function session(req) {
    if (missing.length) fail(503, 'Authentication configuration missing');
    const value = cookie(req, COOKIE);
    const row = value && prepared('SELECT * FROM sessions WHERE id=? AND expires>?').get(hash(value), Date.now());
    if (!row || !allowed.has(row.email)) fail(401, 'Sign in required');
    return row;
  }
  async function upstream(path, data) {
    try {
      const response = await upstreamFetch('http://127.0.0.1:8765' + path, {
        method: data ? 'POST' : 'GET', redirect: 'error', signal: AbortSignal.timeout(10000),
        headers: { authorization: 'Bearer ' + config.apiToken, 'content-type': 'application/json' },
        ...(data ? { body: JSON.stringify(data) } : {}),
      });
      if (!response.ok) fail(response.status === 404 ? 404 : 502, 'Kelion API unavailable');
      const text = await response.text(); if (text.length > 2200000) fail(502, 'Kelion response too large');
      const result = JSON.parse(text);
      return { task_id: result.task_id, state: result.state, output: result.output ?? null,
        output_hash: result.output_hash ?? null, receipt: result.receipt ?? null,
        failure: result.failure ?? null, block_reason: result.block_reason ?? null,
        result_retrieved: result.result_retrieved === true, verified: result.verified === true,
        output_provenance: result.output_provenance ?? null,
        progress: Array.isArray(result.progress) ? result.progress.slice(-40) : [],
        task: typeof result.payload?.request?.task === 'string' ? result.payload.request.task.slice(0, 4000) : null };
    } catch (error) { if (error instanceof HttpError) throw error; fail(502, 'Kelion API unavailable'); }
  }
  const assets = new Map([['/', ['text/html; charset=utf-8', readFileSync(join(here, 'index.html'))]], ['/app.js', ['text/javascript; charset=utf-8', readFileSync(join(here, 'app.js'))]], ['/style.css', ['text/css; charset=utf-8', readFileSync(join(here, 'style.css'))]]]);
  const server = http.createServer(async (req, res) => {
    const send = (status, data, extra = {}) => { res.writeHead(status, { 'content-type': 'application/json; charset=utf-8', ...extra }); res.end(JSON.stringify(data)); };
    res.setHeader('Cache-Control', 'no-store'); res.setHeader('X-Content-Type-Options', 'nosniff');
    res.setHeader('Referrer-Policy', 'no-referrer'); res.setHeader('Permissions-Policy', 'camera=(self), microphone=(self), geolocation=(self)'); res.setHeader('Cross-Origin-Opener-Policy', 'same-origin-allow-popups');
    res.setHeader('Content-Security-Policy', "default-src 'self'; script-src 'self' https://accounts.google.com/gsi/client; style-src 'self' 'unsafe-inline' https://accounts.google.com/gsi/style; frame-src https://accounts.google.com/gsi/ https://www.youtube-nocookie.com https://www.openstreetmap.org; connect-src 'self' https://accounts.google.com/gsi/; img-src 'self' data: blob:; media-src 'self' blob:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'");
    try {
      if (![new URL(config.publicOrigin).host, '127.0.0.1:' + server.address().port].includes(req.headers.host)) fail(403, 'Invalid host');
      if (req.headers.origin && req.headers.origin !== config.publicOrigin) fail(403, 'Invalid origin');
      // Deschiderea paginii dintr-un link (ChatGPT, e-mail) e o navigare de top-level: permisă doar pentru pagina „/”.
      const topNavigation = req.method === 'GET' && req.url === '/' && req.headers['sec-fetch-mode'] === 'navigate' && req.headers['sec-fetch-dest'] === 'document';
      if (req.headers['sec-fetch-site'] === 'cross-site' && !topNavigation) fail(403, 'Cross-site request rejected');
      if (!['GET', 'POST'].includes(req.method)) fail(405, 'Method not allowed');
      if (req.url.includes('?') || req.url.includes('#')) fail(404, 'Unknown endpoint');
      const path = req.url;
      if (req.method === 'POST' && req.headers.origin !== config.publicOrigin) fail(403, 'Exact origin required');
      if (req.method === 'GET' && assets.has(path)) { const [type, content] = assets.get(path); res.writeHead(200, { 'content-type': type }); res.end(content); return; }
      if (req.method === 'GET' && path === '/api/config') return send(200, { clientId: config.clientId || null, missing, ready: !missing.length, worker: 'not_verified', voice: Boolean(config.voiceToken), mask: Boolean(config.maskToken) });
      if (req.method === 'POST' && path === '/auth/nonce') {
        if (missing.length) fail(503, 'Missing: ' + missing.join(', '));
        limit('nonce', 30); cleanup();
        const old = cookie(req, LOGIN); if (old) prepared('DELETE FROM nonces WHERE id=?').run(hash(old));
        const binding = random(), nonce = random();
        prepared('INSERT INTO nonces VALUES (?,?,?)').run(hash(binding), nonce, Date.now() + 300000);
        return send(200, { nonce }, { 'set-cookie': setCookie(LOGIN, binding, 300) });
      }
      if (req.method === 'POST' && path === '/auth/google') {
        if (missing.length) fail(503, 'Authentication configuration missing');
        limit('login', 30); const data = await body(req), binding = cookie(req, LOGIN);
        const row = binding && prepared('DELETE FROM nonces WHERE id=? RETURNING *').get(hash(binding));
        if (!row || row.expires <= Date.now()) fail(401, 'Login challenge expired or already used');
        const user = await verifyGoogle(data.credential, { clientId: config.clientId, nonce: row.nonce, keys });
        if (!allowed.has(user.email)) fail(403, 'This Google account is not authorized');
        const old = cookie(req, COOKIE); if (old) prepared('DELETE FROM sessions WHERE id=?').run(hash(old));
        const id = random(), csrf = random();
        prepared('INSERT INTO sessions VALUES (?,?,?,?,?)').run(hash(id), user.sub, user.email, csrf, Date.now() + 43200000);
        return send(200, { email: user.email, csrf }, { 'set-cookie': [setCookie(COOKIE, id, 43200), setCookie(LOGIN, '', 0)] });
      }
      const MASK = ['/api/app/health', '/api/app/methods', '/api/app/pending', '/api/app/rpc', '/api/app/events', '/api/app/respond'];
      if (![...MASK, '/api/session', '/auth/logout', '/api/tasks', '/api/voice/stt', '/api/voice/tts'].includes(path) && !/^\/api\/tasks\/web-[a-f0-9]{32}$/.test(path)) fail(404, 'Unknown endpoint');
      const user = session(req);
      if (req.method === 'POST' && req.headers['x-csrf-token'] !== user.csrf) fail(403, 'Invalid CSRF token');
      if (req.method === 'GET' && path === '/api/session') return send(200, { email: user.email, csrf: user.csrf });
      if (req.method === 'POST' && path === '/auth/logout') { prepared('DELETE FROM sessions WHERE id=?').run(user.id); return send(200, { ok: true }, { 'set-cookie': setCookie(COOKIE, '', 0) }); }
      if (req.method === 'GET' && path === '/api/tasks') return send(200, { tasks: prepared('SELECT id AS task_id,created,delivery FROM tasks WHERE sub=? ORDER BY created DESC LIMIT 50').all(user.sub) });
      if (req.method === 'POST' && path === '/api/tasks') {
        limit('submit', 10); const data = await body(req);
        if (Object.keys(data).some(k => !['task', 'input_mode'].includes(k)) || typeof data.task !== 'string' || !data.task.trim() || data.task.length > 100000 || !['text', 'voice_transcript'].includes(data.input_mode ?? 'text')) fail(400, 'Invalid task');
        const id = 'web-' + hash(random()).slice(0, 32);
        prepared('INSERT INTO tasks VALUES (?,?,?,?)').run(id, user.sub, Date.now(), 'submission_pending');
        // Persist owner before dispatch. Never replay a POST on timeout/restart.
        try {
          const result = await upstream('/v1/tasks', { task_id: id, task: data.task, origin: 'chat', input_mode: data.input_mode ?? 'text' });
          prepared('UPDATE tasks SET delivery=? WHERE id=?').run('received', id);
          return send(202, result);
        } catch { prepared('UPDATE tasks SET delivery=? WHERE id=?').run('submission_uncertain_readback_required', id); return send(502, { task_id: id, error: 'Submission uncertain; read this task before sending again' }); }
      }
      if (req.method === 'POST' && path === '/api/voice/stt') {
        limit('voice', 60); const audio = await audioBody(req);
        const lang = /^[a-z]{2}$/.test(req.headers['x-kelion-lang'] ?? '') ? req.headers['x-kelion-lang'] : 'ro';
        const response = await voice('/v1/stt', { method: 'POST', body: audio.data, headers: { 'content-type': audio.type, 'x-kelion-lang': lang } });
        const result = await response.json(); return send(200, { text: typeof result.text === 'string' ? result.text.slice(0, 4000) : '' });
      }
      if (req.method === 'POST' && path === '/api/voice/tts') {
        limit('voice', 60); const data = await body(req);
        if (Object.keys(data).some(k => !['text', 'lang'].includes(k)) || typeof data.text !== 'string' || !data.text.trim() || data.text.length > 4000) fail(400, 'Invalid text');
        const lang = /^[a-z]{2}$/.test(data.lang ?? '') ? data.lang : 'ro';
        const response = await voice('/v1/tts', { method: 'POST', body: JSON.stringify({ text: data.text, lang }), headers: { 'content-type': 'application/json' } });
        const wav = Buffer.from(await response.arrayBuffer()); if (wav.length > 20 * 1024 * 1024) fail(502, 'Voice response too large');
        res.writeHead(200, { 'content-type': 'audio/wav', 'content-length': wav.length }); res.end(wav); return;
      }
      if (MASK.includes(path)) {
        if (req.method === 'GET' && ['/api/app/health', '/api/app/methods', '/api/app/pending'].includes(path)) { limit('mask-read', 600); return send(200, await mask('/v1/' + path.slice(9))); }
        if (req.method === 'POST' && path === '/api/app/rpc') {
          limit('mask-rpc', 600); const data = await body(req, 12 * 1024 * 1024);
          if (Object.keys(data).some(k => !['method', 'params'].includes(k)) || typeof data.method !== 'string' || !/^[A-Za-z_/]{1,80}$/.test(data.method)
            || (data.params !== undefined && (data.params === null || typeof data.params !== 'object' || Array.isArray(data.params)))) fail(400, 'Invalid request');
          return send(200, await mask('/v1/rpc', data, 620000));
        }
        if (req.method === 'POST' && path === '/api/app/events') {
          limit('mask-events', 600); const data = await body(req);
          if (Object.keys(data).some(k => k !== 'since') || !Number.isSafeInteger(data.since) || data.since < 0) fail(400, 'Invalid request');
          return send(200, await mask('/v1/events', { since: data.since, timeout: 25 }, 35000));
        }
        if (req.method === 'POST' && path === '/api/app/respond') {
          limit('mask-rpc', 600); const data = await body(req, 1024 * 1024);
          if (Object.keys(data).some(k => !['id', 'result', 'error'].includes(k)) || !['string', 'number'].includes(typeof data.id)) fail(400, 'Invalid request');
          return send(200, await mask('/v1/respond', data));
        }
        fail(405, 'Method not allowed');
      }
      if (req.method === 'GET' && path.startsWith('/api/tasks/')) {
        limit('read', 300); const id = path.slice('/api/tasks/'.length);
        if (!prepared('SELECT 1 FROM tasks WHERE id=? AND sub=?').get(id, user.sub)) fail(404, 'Unknown task');
        const result = await upstream('/v1/tasks/' + id); return send(200, result);
      }
      fail(404, 'Unknown endpoint');
    } catch (error) { if (!res.headersSent) send(error instanceof HttpError ? error.status : 500, { error: error instanceof HttpError ? error.message : 'Internal error' }); else res.end(); }
  });
  server.requestTimeout = 120000; server.headersTimeout = 10000; server.maxRequestsPerSocket = 100;
  server.on('close', () => { clearInterval(timer); db.close(); });
  return server;
}
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  process.umask(0o077);
  const app = createApp({ publicOrigin: 'https://kelionai.app', clientId: process.env.GOOGLE_CLIENT_ID ?? '',
    allowedEmails: (process.env.KELION_ALLOWED_EMAILS ?? '').split(',').map(s => s.trim()).filter(Boolean),
    apiToken: process.env.KELION_CLIENT_TOKEN ?? '', voiceToken: process.env.KELION_VOICE_TOKEN ?? '', maskToken: process.env.KELION_MASK_TOKEN ?? '', database: join(process.env.STATE_DIRECTORY || '/var/lib/kelion-web', 'web.sqlite') });
  app.listen(8766, '127.0.0.1', () => console.log('Kelion web listening on loopback:8766'));
  for (const event of ['SIGINT', 'SIGTERM']) process.on(event, () => { app.close(); app.closeAllConnections(); });
}
