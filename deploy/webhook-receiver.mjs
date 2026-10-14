// Primește notificarea de deploy trimisă de GitHub Actions la fiecare push pe main
// și pornește imediat deploy-ul web. Fără secret partajat: cererea poartă un token
// OIDC semnat de GitHub, verificat aici cu cheile publice GitHub.
// Ascultă doar pe 127.0.0.1; proxy-ul HTTPS existent trimite aici /hooks/github.
// Nu rulează cod din cerere: doar `systemctl start kelion-web-deploy.service`.
import http from 'node:http';
import { createPublicKey, verify } from 'node:crypto';
import { appendFileSync, mkdirSync } from 'node:fs';
import { execFile } from 'node:child_process';

const PORT = Number(process.env.PORT || 8767);
const REPO = process.env.REPO || 'kelion-team/kelionai_dots';
const BRANCH_REF = 'refs/heads/' + (process.env.BRANCH || 'main');
const AUDIENCE = process.env.AUDIENCE || 'https://kelionai.app/hooks/github';
const SERVICE = process.env.DEPLOY_SERVICE || 'kelion-web-deploy.service';
const EVENTS_LOG = process.env.EVENTS_LOG || '/var/lib/kelion-deploy/events.jsonl';
const ISSUER = 'https://token.actions.githubusercontent.com';
const JWKS_URL = process.env.JWKS_URL || ISSUER + '/.well-known/jwks';

// Fiecare eveniment real este măsurat: sosire, commit, durată deploy, rezultat.
function record(entry) {
  const line = JSON.stringify({ at: new Date().toISOString(), ...entry });
  console.log('[kelion-webhook] ' + line);
  try { mkdirSync(EVENTS_LOG.replace(/\/[^/]*$/, ''), { recursive: true }); appendFileSync(EVENTS_LOG, line + '\n'); } catch (e) { console.log('[kelion-webhook] jurnal indisponibil: ' + e.message); }
}

let keys = [], keysAt = 0;
async function key(kid, fetchImpl = fetch) {
  if (!keys.some(k => k.kid === kid) || Date.now() - keysAt > 3600_000) {
    const r = await fetchImpl(JWKS_URL, { redirect: 'error', signal: AbortSignal.timeout(5000) });
    if (!r.ok) throw new Error('GitHub JWKS unavailable');
    keys = (await r.json()).keys || []; keysAt = Date.now();
  }
  return keys.find(k => k.kid === kid && k.kty === 'RSA');
}

const seen = new Map(); // jti -> exp, ca un token să nu poată fi refolosit
export async function verifyGithubToken(token, { now = Math.floor(Date.now() / 1000), getKey = key } = {}) {
  const parts = typeof token === 'string' ? token.split('.') : [];
  if (parts.length !== 3) throw new Error('malformed token');
  const header = JSON.parse(Buffer.from(parts[0], 'base64url'));
  const claim = JSON.parse(Buffer.from(parts[1], 'base64url'));
  if (header.alg !== 'RS256' || typeof header.kid !== 'string') throw new Error('bad alg');
  const jwk = await getKey(header.kid);
  if (!jwk || !verify('RSA-SHA256', Buffer.from(parts[0] + '.' + parts[1]), createPublicKey({ key: jwk, format: 'jwk' }), Buffer.from(parts[2], 'base64url'))) throw new Error('bad signature');
  if (claim.iss !== ISSUER) throw new Error('bad issuer');
  if (claim.aud !== AUDIENCE) throw new Error('bad audience');
  if (!(claim.exp > now) || !(claim.iat <= now + 60) || !(claim.nbf === undefined || claim.nbf <= now + 60)) throw new Error('expired');
  if (claim.repository !== REPO || claim.ref !== BRANCH_REF || claim.event_name !== 'push') throw new Error('wrong repo/ref/event');
  for (const [j, e] of seen) if (e < now) seen.delete(j);
  if (typeof claim.jti !== 'string' || seen.has(claim.jti)) throw new Error('replayed token');
  seen.set(claim.jti, claim.exp);
  return claim;
}

let running = false, queued = null;
function deploy(meta) {
  if (running) { queued = meta; return; }
  running = true;
  const started = Date.now();
  record({ event: 'deploy_start', ...meta });
  execFile('systemctl', ['start', SERVICE], (error) => {
    record({ event: 'deploy_end', ...meta, ok: !error, duration_ms: Date.now() - started, error: error ? error.message.split('\n')[0] : undefined });
    running = false;
    if (queued) { const next = queued; queued = null; deploy(next); }
  });
}

export const server = http.createServer(async (req, res) => {
  const reply = (code, text) => { res.writeHead(code, { 'content-type': 'text/plain; charset=utf-8' }); res.end(text + '\n'); };
  if (req.url !== '/hooks/github') return reply(404, 'not found');
  if (req.method !== 'POST') return reply(405, 'Acest endpoint primește doar notificări de la GitHub Actions (POST).');
  const auth = req.headers.authorization || '';
  let claim;
  try { claim = await verifyGithubToken(auth.startsWith('Bearer ') ? auth.slice(7) : ''); }
  catch (e) { record({ event: 'rejected', reason: e.message }); return reply(401, 'unauthorized'); }
  const meta = { run_id: claim.run_id, commit: claim.sha?.slice(0, 12), actor: claim.actor, workflow: claim.workflow };
  record({ event: 'push_received', ...meta });
  deploy(meta);
  reply(202, 'deploy started');
});
if (process.argv[1] && import.meta.url.endsWith(process.argv[1].split('/').pop())) {
  server.listen(PORT, '127.0.0.1', () => console.log(`[kelion-webhook] ascult pe 127.0.0.1:${PORT}/hooks/github`));
}
