// Primește evenimentul GitHub "push" și pornește imediat deploy-ul web.
// Ascultă doar pe 127.0.0.1; proxy-ul HTTPS existent trimite aici /hooks/github.
// Acceptă numai cereri semnate cu secretul webhook-ului (X-Hub-Signature-256),
// numai push pe refs/heads/main din kelion-team/kelionai_dots.
// Nu rulează cod din cerere: doar `systemctl start kelion-web-deploy.service`.
import http from 'node:http';
import { createHmac, timingSafeEqual } from 'node:crypto';
import { readFileSync, appendFileSync, mkdirSync } from 'node:fs';
import { execFile } from 'node:child_process';

const PORT = Number(process.env.PORT || 8767);
const REPO = process.env.REPO || 'kelion-team/kelionai_dots';
const BRANCH_REF = 'refs/heads/' + (process.env.BRANCH || 'main');
const SERVICE = process.env.DEPLOY_SERVICE || 'kelion-web-deploy.service';
const EVENTS_LOG = process.env.EVENTS_LOG || '/var/lib/kelion-deploy/events.jsonl';
const secret = readFileSync(process.env.SECRET_FILE || '/etc/kelion-deploy/webhook-secret', 'utf8').trim();
if (secret.length < 32) throw new Error('Webhook secret must have at least 32 characters');

export function validSignature(body, header, key = secret) {
  if (typeof header !== 'string' || !header.startsWith('sha256=')) return false;
  const expected = Buffer.from('sha256=' + createHmac('sha256', key).update(body).digest('hex'));
  const given = Buffer.from(header);
  return given.length === expected.length && timingSafeEqual(given, expected);
}

// Fiecare eveniment real este măsurat: sosire, commit, durată deploy, rezultat.
function record(entry) {
  const line = JSON.stringify({ at: new Date().toISOString(), ...entry });
  console.log('[kelion-webhook] ' + line);
  try { mkdirSync(EVENTS_LOG.replace(/\/[^/]*$/, ''), { recursive: true }); appendFileSync(EVENTS_LOG, line + '\n'); } catch (e) { console.log('[kelion-webhook] jurnal indisponibil: ' + e.message); }
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

const server = http.createServer((req, res) => {
  const reply = (code, text) => { res.writeHead(code, { 'content-type': 'text/plain; charset=utf-8' }); res.end(text); };
  if (req.method !== 'POST' || req.url !== '/hooks/github') return reply(404, 'not found');
  const chunks = []; let size = 0;
  req.on('data', c => { size += c.length; if (size > 1_000_000) { reply(413, 'too large'); req.destroy(); } else chunks.push(c); });
  req.on('end', () => {
    if (res.writableEnded) return;
    const body = Buffer.concat(chunks);
    if (!validSignature(body, req.headers['x-hub-signature-256'])) return reply(401, 'bad signature');
    const event = req.headers['x-github-event'];
    if (event === 'ping') return reply(200, 'pong');
    if (event !== 'push') return reply(202, 'ignored event');
    let data; try { data = JSON.parse(body); } catch { return reply(400, 'bad json'); }
    if (data?.repository?.full_name !== REPO || data?.ref !== BRANCH_REF) return reply(202, 'ignored ref');
    const touched = (data.commits || []).some(c => [...(c.added || []), ...(c.modified || []), ...(c.removed || [])].some(f => f.startsWith('site-live/web/')));
    if (!touched && (data.commits || []).length) { record({ event: 'push_ignored', delivery: req.headers['x-github-delivery'], commit: data.after?.slice(0, 12), reason: 'fără schimbări în site-live/web' }); return reply(202, 'no web changes'); }
    const meta = { delivery: req.headers['x-github-delivery'], commit: data.after?.slice(0, 12), pusher: data.pusher?.name, pushed_at: data.head_commit?.timestamp };
    record({ event: 'push_received', ...meta, web_changed: touched || !(data.commits || []).length });
    deploy(meta);
    reply(202, 'deploy started');
  });
});
if (process.argv[1] && import.meta.url.endsWith(process.argv[1].split('/').pop())) {
  server.listen(PORT, '127.0.0.1', () => console.log(`[kelion-webhook] ascult pe 127.0.0.1:${PORT}/hooks/github`));
}
