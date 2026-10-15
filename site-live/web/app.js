'use strict';
// Masca KelionAI peste Codex app-server de pe kelion-nou. Fiecare acțiune de aici e o operație din schema
// app-server (orchestration/app-server-schema), trimisă prin puntea locală; nimic nu se simulează în pagină.

// Markdown minimal și sigur (text escapat; linkuri doar http/https).
export function markdown(text) {
  const esc = s => s.replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  const inline = s => esc(s).replace(/`([^`]+)`/g, '<code>$1</code>').replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, (m, t, u) => '<a href="' + u + '" target="_blank" rel="noopener noreferrer">' + t + '</a>');
  const out = [], lines = String(text ?? '').split('\n');
  let list = null, para = [];
  const flush = () => { if (para.length) { out.push('<p>' + para.map(inline).join('<br>') + '</p>'); para = []; } if (list) { out.push('</' + list + '>'); list = null; } };
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (/^```/.test(line)) {
      flush(); const code = [];
      while (++i < lines.length && !/^```/.test(lines[i])) code.push(lines[i]);
      out.push('<pre><code>' + esc(code.join('\n')) + '</code></pre>'); continue;
    }
    const h = /^(#{1,4})\s+(.*)$/.exec(line), li = /^\s*(?:[-*]|(\d+)\.)\s+(.*)$/.exec(line);
    if (h) { flush(); out.push('<h' + (h[1].length + 2) + '>' + inline(h[2]) + '</h' + (h[1].length + 2) + '>'); }
    else if (li) { if (para.length) { const l = list; list = null; flush(); list = l; } const kind = li[1] ? 'ol' : 'ul'; if (list !== kind) { if (list) out.push('</' + list + '>'); out.push('<' + kind + '>'); list = kind; } out.push('<li>' + inline(li[2]) + '</li>'); }
    else if (!line.trim()) flush();
    else { if (list) { out.push('</' + list + '>'); list = null; } para.push(line); }
  }
  flush(); return out.join('');
}

// Text afișabil dintr-un UserInput (schema: text, image, localImage, audio, localAudio, ...).
export function inputText(content) {
  return (content || []).map(part => part.type === 'text' ? part.text : part.type === 'localImage' ? '🖼 ' + part.path.split('/').pop()
    : part.type === 'image' ? '🖼 imagine' : '[' + part.type + ']').join('\n');
}

// Starea turnului activ: un turn deja încheiat nu mai poate redeveni activ, indiferent dacă
// notificarea turn/completed ajunge înaintea răspunsului HTTP la turn/start.
export class TurnState {
  constructor() { this.active = null; this.done = new Set(); }
  started(id) { if (id && !this.done.has(id)) this.active = id; return this.active; }
  completed(id) { this.done.add(id); if (this.active === id) this.active = null; return this.active; }
  reset() { this.active = null; this.done.clear(); }
}

// Pagini de turnuri mai vechi: thread/turns/list cu cursorul înapoi și sortDirection "desc" (schema app-server).
// Prima pagină include turnul-ancoră deja afișat; turnurile văzute se sar. Rezultatul e în ordine cronologică.
export async function olderTurns(rpc, threadId, cursor, seen, limit = 20) {
  const r = await rpc('thread/turns/list', { threadId, cursor, sortDirection: 'desc', itemsView: 'full', limit });
  const turns = (r.data || []).filter(t => !seen.has(t.id)).reverse();
  return { turns, cursor: r.nextCursor || null };
}

// Elementele complete ale unui turn încărcat doar sumar: thread/items/list, toate paginile.
export async function turnItems(rpc, threadId, turn) {
  if (!turn.itemsView || turn.itemsView === 'full') return turn.items || [];
  const out = []; let cursor = null;
  do {
    const r = await rpc('thread/items/list', { threadId, turnId: turn.id, sortDirection: 'asc', ...(cursor ? { cursor } : {}) });
    out.push(...(r.data || [])); cursor = r.nextCursor || null;
  } while (cursor);
  return out;
}

// Eșec sigur (cererea sigur nu a ajuns) față de trimitere incertă (poate a ajuns): fără retrimitere automată.
export function sendFailure(error) {
  if (error?.rpc) return 'failed';                                   // app-server a răspuns cu eroare
  if (error?.status && error.status >= 400 && error.status < 500) return 'failed';
  return 'uncertain';                                                // rețea, 502/504, timp depășit
}

if (typeof document !== 'undefined') {
const $ = id => document.getElementById(id);
const el = (tag, cls, text) => { const n = document.createElement(tag); if (cls) n.className = cls; if (text !== undefined) n.textContent = text; return n; };
let csrf = '', methods = { allowed: [], blocked: {}, uploads_dir: '' }, models = [], since = 0, polling = false;
let current = null, nextCursor = null, chips = [], olderCursor = null, sending = false;
const turnState = new TurnState(), seenTurns = new Set();
const active = () => turnState.active;
const items = new Map();   // itemId -> elementul randat

async function api(path, data) {
  const response = await fetch(path, { method: data === undefined ? 'GET' : 'POST', credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', ...(csrf ? { 'X-CSRF-Token': csrf } : {}) }, ...(data === undefined ? {} : { body: JSON.stringify(data) }) });
  const result = await response.json().catch(() => ({}));
  if (!response.ok) throw Object.assign(Error(result.error || 'Cererea a eșuat (' + response.status + ')'), { status: response.status });
  return result;
}
// params === null: metoda nu are parametri în schemă (ex. account/rateLimits/read).
async function rpc(method, params = {}) {
  const r = await api('/api/app/rpc', params === null ? { method } : { method, params });
  if (r.error) { const e = Error(r.error.message || 'Eroare app-server'); e.rpc = r.error; throw e; }
  return r.result;
}
function note(text, cls = 'note') { const n = el('div', 'msg ' + cls, text); $('log').append(n); scroll(); return n; }
function scroll() { const log = $('log'); if (log.scrollHeight - log.scrollTop - log.clientHeight < 200) log.scrollTop = log.scrollHeight; }
function link(ok, text) { $('link').className = 'link ' + (ok ? 'ok' : 'bad'); $('link').title = text; }

// ---------- istoric ----------
async function loadThreads(more = false) {
  const params = { limit: 40, sortKey: 'updated_at', sortDirection: 'desc', archived: $('archived').checked };
  if ($('search').value.trim()) params.searchTerm = $('search').value.trim();
  if (more && nextCursor) params.cursor = nextCursor;
  const r = await rpc('thread/list', params);
  nextCursor = r.nextCursor || null; $('more-threads').hidden = !nextCursor;
  if (!more) $('threads').replaceChildren();
  for (const t of r.data || []) {
    const b = el('button', 'thread' + (t.id === current ? ' on' : ''), t.name || t.preview || 'Conversație fără titlu');
    b.dataset.id = t.id; b.title = new Date((t.updatedAt || t.createdAt) * 1000).toLocaleString();
    b.onclick = () => { openThread(t.id).catch(e => note(e.message, 'err')); closeSide(); };
    $('threads').append(b);
  }
  showApprovals();
}
function markCurrent() { for (const b of $('threads').children) b.classList.toggle('on', b.dataset.id === current); }

// ---------- randarea elementelor (ThreadItem) ----------
function render(item, turnId, before = null) {
  let node = items.get(item.id);
  const fresh = !node;
  if (fresh) { node = el('div', 'msg item-' + item.type); node.dataset.turn = turnId || ''; items.set(item.id, node);
    if (before) $('log').insertBefore(node, before); else $('log').append(node); $('empty').hidden = true; }
  node.replaceChildren();
  switch (item.type) {
    case 'userMessage': node.className = 'msg me'; node.textContent = inputText(item.content);
      for (const part of item.content || []) if (part.type === 'localImage') showImage(node, part.path); break;
    case 'agentMessage': node.className = 'msg bot'; node.innerHTML = markdown(item.text); node.dataset.raw = item.text || ''; break;
    case 'reasoning': { node.className = 'msg tool'; const d = el('details'); d.append(el('summary', '', 'Raționament'));
      const body = el('div', 'reason'); body.textContent = (item.summary || []).join('\n\n'); d.append(body); node.append(d); break; }
    case 'plan': node.className = 'msg tool'; node.append(el('strong', '', 'Plan')); node.append(el('pre', '', item.text)); break;
    case 'commandExecution': { node.className = 'msg tool'; const d = el('details'); d.open = item.status === 'inProgress';
      d.append(el('summary', '', '⌘ ' + item.command + ' · ' + item.status + (item.exitCode != null ? ' · cod ' + item.exitCode : '')));
      const out = el('pre', 'out', item.aggregatedOutput || ''); d.append(out); node.append(d); break; }
    case 'fileChange': { node.className = 'msg tool'; const d = el('details'); d.append(el('summary', '', '✎ Fișiere modificate (' + (item.changes || []).length + ') · ' + item.status));
      for (const c of item.changes || []) { d.append(el('div', 'path', (c.kind?.type ? c.kind.type + ' ' : '') + c.path)); d.append(el('pre', 'diff', c.diff)); }
      node.append(d); break; }
    case 'mcpToolCall': { node.className = 'msg tool'; const d = el('details'); d.append(el('summary', '', '⚙ ' + item.server + ' · ' + item.tool + ' · ' + item.status));
      d.append(value({ arguments: item.arguments, result: item.result, error: item.error })); node.append(d); break; }
    case 'dynamicToolCall': case 'functionCallOutput': case 'collabAgentToolCall': case 'subAgentActivity': {
      node.className = 'msg tool'; const d = el('details'); d.append(el('summary', '', '⚙ ' + item.type + (item.tool ? ' · ' + item.tool : '') + (item.status ? ' · ' + item.status : '')));
      d.append(value(item)); node.append(d); break; }
    case 'webSearch': { node.className = 'msg tool'; const d = el('details'); d.append(el('summary', '', '🔎 Căutare web: ' + (item.query || '')));
      for (const r of item.results || []) { const a = el('a', 'res', r.title || r.url); if (/^https?:\/\//.test(r.url || '')) { a.href = r.url; a.target = '_blank'; a.rel = 'noopener noreferrer'; } d.append(a); }
      node.append(d); break; }
    case 'imageView': node.className = 'msg tool'; node.append(el('div', 'path', '🖼 ' + item.path)); showImage(node, item.path); break;
    case 'imageGeneration': node.className = 'msg bot'; node.append(el('div', 'path', '🎨 ' + (item.revisedPrompt || 'Imagine generată') + ' · ' + item.status));
      if (item.savedPath) showImage(node, item.savedPath); if (item.failure) node.append(el('div', 'err', JSON.stringify(item.failure))); break;
    case 'contextCompaction': node.className = 'msg note'; node.textContent = 'Context compactat.'; break;
    case 'enteredReviewMode': case 'exitedReviewMode': node.className = 'msg note'; node.textContent = item.type === 'enteredReviewMode' ? 'Revizie pornită.' : 'Revizie încheiată.'; break;
    case 'sleep': node.className = 'msg note'; node.textContent = 'Așteptare ' + Math.round((item.durationMs || 0) / 1000) + ' s'; break;
    default: node.className = 'msg tool'; { const d = el('details'); d.append(el('summary', '', item.type)); d.append(value(item)); node.append(d); }
  }
  scroll(); return node;
}
async function showImage(node, path) {
  try { const r = await rpc('fs/readFile', { path }); const img = el('img', 'pic'); img.alt = path.split('/').pop();
    img.src = URL.createObjectURL(new Blob([Uint8Array.from(atob(r.dataBase64), c => c.charCodeAt(0))])); node.append(img); }
  catch (e) { node.append(el('div', 'err', 'Imaginea nu poate fi citită: ' + e.message)); }
}
// Valori din răspunsuri afișate fidel, fără câmpuri inventate.
function value(v, depth = 0) {
  if (v === null || v === undefined) return el('span', 'nil', '—');
  if (typeof v !== 'object') return el('span', 'val', String(v));
  if (depth > 5) return el('pre', 'val', JSON.stringify(v, null, 1));
  const box = el(Array.isArray(v) ? 'ol' : 'dl', 'tree');
  for (const [k, x] of Object.entries(v)) {
    if (Array.isArray(v)) { const li = el('li'); li.append(value(x, depth + 1)); box.append(li); }
    else { box.append(el('dt', '', k)); const dd = el('dd'); dd.append(value(x, depth + 1)); box.append(dd); }
  }
  return box;
}

// ---------- conversație ----------
function resetLog() { items.clear(); seenTurns.clear(); turnState.reset(); olderCursor = null; $('log').replaceChildren($('older'), $('empty')); $('older').hidden = true; $('empty').hidden = false; }
async function showTurn(turn, before = null) {
  seenTurns.add(turn.id);
  for (const item of await turnItems(rpc, current, turn)) render(item, turn.id, before);
  if (turn.status === 'inProgress') turnState.started(turn.id); else turnState.completed(turn.id);
  if (turn.error) { const n = el('div', 'msg err', 'Eroare: ' + turn.error.message); if (before) $('log').insertBefore(n, before); else $('log').append(n); }
}
async function openThread(id) {
  const r = await rpc('thread/resume', { threadId: id });
  current = id; resetLog(); markCurrent();
  $('title').textContent = r.thread.name || r.thread.preview || 'Conversație'; $('thread-menu-wrap').hidden = false;
  if (r.model) selectModel(r.model, r.reasoningEffort);
  for (const turn of r.thread.turns || []) await showTurn(turn);
  olderCursor = r.turnsBackwardsCursor || null; $('older').hidden = !olderCursor;
  busy(Boolean(active())); $('log').scrollTop = $('log').scrollHeight; showApprovals();
}
async function loadOlder() {
  if (!current || !olderCursor) return;
  $('older').disabled = true;
  try {
    const thread = current, anchor = $('older').nextElementSibling, height = $('log').scrollHeight;
    const page = await olderTurns(rpc, thread, olderCursor, seenTurns);
    if (thread !== current) return;
    for (const turn of page.turns) await showTurn(turn, anchor);
    olderCursor = page.cursor; $('older').hidden = !olderCursor;
    $('log').scrollTop += $('log').scrollHeight - height;
  } catch (e) { note(e.message, 'err'); } finally { $('older').disabled = false; }
}
function newThread() { current = null; resetLog(); markCurrent(); $('title').textContent = 'Conversație nouă'; $('thread-menu-wrap').hidden = true; busy(false); showApprovals(); }
function busy(on) { $('send').disabled = sending; $('stop').hidden = !on; $('send').title = on ? 'Trimite în timpul rulării (steer)' : 'Trimite'; }

// Textul și imaginile rămân în compozitor până când app-server confirmă cererea.
async function send(text) {
  const input = [];
  if (text) input.push({ type: 'text', text, text_elements: [] });
  for (const c of chips) input.push({ type: 'localImage', path: c.path });
  if (!input.length || sending) return;
  sending = true; busy(Boolean(active()));
  const done = () => { if ($('input').value.trim() === text) { $('input').value = ''; fit(); } chips = chips.filter(c => !input.some(i => i.path === c.path)); drawChips(); };
  try {
    if (!current) {
      const params = {}; if ($('model').value) params.model = $('model').value;
      if ($('approval').value) params.approvalPolicy = $('approval').value; if ($('sandbox').value) params.sandbox = $('sandbox').value;
      const r = await rpc('thread/start', params); current = r.thread.id; $('thread-menu-wrap').hidden = false; showApprovals(); loadThreads().catch(() => {});
    }
    if (active()) { await rpc('turn/steer', { threadId: current, expectedTurnId: active(), input }); done(); return; }
    const params = { threadId: current, input };
    if ($('model').value) params.model = $('model').value; if ($('effort').value) params.effort = $('effort').value;
    if ($('approval').value) params.approvalPolicy = $('approval').value;
    const r = await rpc('turn/start', params); done();
    if (r.turn.status === 'inProgress') turnState.started(r.turn.id); else turnState.completed(r.turn.id);
    seenTurns.add(r.turn.id);
    for (const item of r.turn.items || []) render(item, r.turn.id);
  } catch (e) {
    if (sendFailure(e) === 'failed') note('Netrimis: ' + e.message + '. Mesajul a rămas în compozitor.', 'err');
    else note('Trimitere incertă (' + e.message + '): poate a ajuns la Codex. Verifică conversația înainte să retrimiți; nu retrimit automat.', 'warn');
  } finally { sending = false; busy(Boolean(active())); }
}

// ---------- aprobări și întrebări cerute de server (ServerRequest) ----------
const DECISIONS = {
  'item/commandExecution/requestApproval': [['accept', 'Aprobă'], ['acceptForSession', 'Aprobă pentru sesiune'], ['decline', 'Refuză'], ['cancel', 'Refuză și oprește']],
  'item/fileChange/requestApproval': [['accept', 'Aprobă'], ['acceptForSession', 'Aprobă pentru sesiune'], ['decline', 'Refuză'], ['cancel', 'Refuză și oprește']],
  execCommandApproval: [['approved', 'Aprobă'], ['approved_for_session', 'Aprobă pentru sesiune'], ['denied', 'Refuză'], ['abort', 'Refuză și oprește']],
  applyPatchApproval: [['approved', 'Aprobă'], ['approved_for_session', 'Aprobă pentru sesiune'], ['denied', 'Refuză'], ['abort', 'Refuză și oprește']],
};
const waiting = new Map();   // cererile serverului care așteaptă răspuns, pe conversații
function approval(req) { waiting.set('req-' + JSON.stringify(req.id), req); showApprovals(); }
function resolved(key) { waiting.delete(key); document.getElementById(key)?.remove(); showApprovals(); }
function showApprovals() {
  const busyThreads = new Set([...waiting.values()].map(r => r.params?.threadId).filter(Boolean));
  for (const b of $('threads').children) b.classList.toggle('wait', busyThreads.has(b.dataset.id));
  for (const n of [...$('approvals').children]) if (!waiting.has(n.id) || (waiting.get(n.id).params?.threadId && waiting.get(n.id).params.threadId !== current)) n.remove();
  for (const req of waiting.values()) if (!req.params?.threadId || req.params.threadId === current) card(req);
}
function card(req) {
  const key = 'req-' + JSON.stringify(req.id);
  if (document.getElementById(key)) return;
  const box = el('div', 'card'); box.id = key;
  box.append(el('strong', '', 'Cerere de la Codex: ' + req.method)); box.append(value(req.params));
  const row = el('div', 'row');
  const answer = async payload => { row.querySelectorAll('button').forEach(b => b.disabled = true);
    try { await api('/api/app/respond', { id: req.id, ...payload }); resolved(key); } catch (e) { if (e.status === 404) { resolved(key); return; } box.append(el('div', 'err', e.message)); row.querySelectorAll('button').forEach(b => b.disabled = false); } };
  if (DECISIONS[req.method]) for (const [decision, label] of DECISIONS[req.method]) { const b = el('button', decision.startsWith('accept') || decision.startsWith('approved') ? '' : 'ghost', label); b.type = 'button'; b.onclick = () => answer({ result: { decision } }); row.append(b); }
  else if (req.method === 'item/tool/requestUserInput') {
    const fields = {};
    for (const q of req.params.questions || []) { const l = el('label', 'q', q.question || q.header || q.id); const i = el('input'); if (q.isSecret) i.type = 'password'; fields[q.id] = i; l.append(i); box.append(l); }
    const b = el('button', '', 'Trimite răspunsul'); b.type = 'button'; b.onclick = () => answer({ result: { answers: Object.fromEntries(Object.entries(fields).map(([k, i]) => [k, { answers: [i.value] }])) } }); row.append(b);
  } else if (req.method === 'mcpServer/elicitation/request') {
    for (const action of ['accept', 'decline', 'cancel']) { const b = el('button', action === 'accept' ? '' : 'ghost', { accept: 'Acceptă', decline: 'Refuză', cancel: 'Anulează' }[action]); b.type = 'button'; b.onclick = () => answer({ result: { action, content: null } }); row.append(b); }
  } else {
    const b = el('button', 'ghost', 'Refuză (nesuportat în mască)'); b.type = 'button'; b.onclick = () => answer({ error: { code: -32601, message: 'Nesuportat în masca KelionAI' } }); row.append(b);
  }
  box.append(row); $('approvals').append(box);
}

// ---------- evenimente (ServerNotification) ----------
function onEvent(ev) {
  const p = ev.params || {};
  if (ev.kind === 'bridge') { link(ev.method === 'bridge/connected', ev.method === 'bridge/connected' ? 'Conectat la Codex de pe kelion-nou' : 'Legătura cu Codex s-a întrerupt: ' + (p.reason || '')); return; }
  if (ev.kind === 'request') { approval(ev); return; }
  if (ev.method === 'serverRequest/resolved') { resolved('req-' + JSON.stringify(p.requestId)); return; }
  if (['thread/started', 'thread/archived', 'thread/unarchived', 'thread/deleted', 'thread/name/updated'].includes(ev.method)) {
    loadThreads().catch(() => {}); if (ev.method === 'thread/name/updated' && p.threadId === current) $('title').textContent = p.threadName || $('title').textContent; return; }
  if (['warning', 'configWarning', 'deprecationNotice', 'guardianWarning'].includes(ev.method)) { note('⚠ ' + (p.message || p.summary || JSON.stringify(p)), 'warn'); return; }
  if (ev.method === 'account/rateLimits/updated' && $('panel-title').dataset.kind === 'account') { openPanel('account'); return; }
  if (p.threadId && p.threadId !== current) return;
  switch (ev.method) {
    case 'turn/started': seenTurns.add(p.turn.id); turnState.started(p.turn.id); busy(Boolean(active())); break;
    case 'turn/completed': turnState.completed(p.turn.id); busy(Boolean(active()));
      if (p.turn.error) note('Eroare: ' + p.turn.error.message, 'err'); if (p.turn.status === 'interrupted') note('Oprit.', 'note'); loadThreads().catch(() => {}); break;
    case 'item/started': case 'item/completed': render(p.item, p.turnId); break;
    case 'item/agentMessage/delta': { let n = items.get(p.itemId); if (!n) n = render({ type: 'agentMessage', id: p.itemId, text: '' }, p.turnId);
      n.dataset.raw = (n.dataset.raw || '') + p.delta; n.innerHTML = markdown(n.dataset.raw); scroll(); break; }
    case 'item/reasoning/summaryTextDelta': { const n = items.get(p.itemId)?.querySelector('.reason'); if (n) n.textContent += p.delta; break; }
    case 'item/commandExecution/outputDelta': { const n = items.get(p.itemId)?.querySelector('.out'); if (n) { n.textContent += p.delta; scroll(); } break; }
    case 'turn/plan/updated': { const n = note('', 'tool'); n.append(el('strong', '', 'Plan')); const ol = el('ol'); for (const s of p.plan || []) ol.append(el('li', s.status, s.step + ' · ' + s.status)); n.append(ol); break; }
    case 'error': note('Eroare: ' + (p.error?.message || '') + (p.willRetry ? ' · se reîncearcă' : ''), 'err'); break;
    case 'model/rerouted': note('Model redirecționat: ' + JSON.stringify(p), 'warn'); break;
    case 'thread/compacted': note('Context compactat.', 'note'); break;
    case 'thread/status/changed': if (p.status?.type === 'systemError') note('Eroare de sistem în conversație.', 'err'); break;
  }
}
async function poll() {
  if (polling) return; polling = true;
  while (csrf) {
    try {
      const r = await api('/api/app/events', { since });
      if (r.reset && current) openThread(current).catch(() => {});
      for (const ev of r.events) onEvent(ev);
      since = r.last;
    } catch (e) { link(false, e.message); await new Promise(res => setTimeout(res, 3000)); }
  }
  polling = false;
}

// ---------- modele și efort (model/list) ----------
async function loadModels() {
  models = []; let cursor;
  do { const r = await rpc('model/list', cursor ? { cursor } : {}); models.push(...(r.data || [])); cursor = r.nextCursor; } while (cursor);
  $('model').replaceChildren(...models.map(m => { const o = el('option', '', m.displayName || m.id); o.value = m.model || m.id; o.title = m.description || ''; if (m.isDefault) o.selected = true; return o; }));
  efforts();
}
function efforts(selected) {
  const m = models.find(x => (x.model || x.id) === $('model').value);
  $('effort').replaceChildren(...(m?.supportedReasoningEfforts || []).map(e => { const o = el('option', '', 'Efort: ' + e.reasoningEffort); o.value = e.reasoningEffort; o.title = e.description || '';
    if ((selected || m.defaultReasoningEffort) === e.reasoningEffort) o.selected = true; return o; }));
}
function selectModel(model, effort) { if ([...$('model').options].some(o => o.value === model)) { $('model').value = model; efforts(effort); } }

// ---------- panouri ----------
const PANELS = {
  skills: ['Skills', () => rpc('skills/list', {})],
  plugins: ['Pluginuri', () => rpc('plugin/list', {})],
  apps: ['Aplicații', () => rpc('app/list', {})],
  mcp: ['Servere MCP', () => rpc('mcpServerStatus/list', { detail: 'toolsAndAuthOnly' })],
  account: ['Cont și limite', async () => {
    const out = {};
    for (const [k, m] of [['cont', 'account/read'], ['limite', 'account/rateLimits/read'], ['utilizare', 'account/usage/read']]) { try { out[k] = await rpc(m, m === 'account/read' ? {} : null); } catch (e) { out[k] = 'Eroare: ' + e.message; } }
    return out; }],
  functions: ['Funcții', async () => ({ 'permise (din schema app-server)': methods.allowed, 'blocate, cu motivul': methods.blocked, sursa: methods.source })],
};
async function openPanel(kind) {
  const [title, load] = PANELS[kind]; $('panel-title').textContent = title; $('panel-title').dataset.kind = kind;
  $('panel-body').replaceChildren(el('p', 'note', 'Se încarcă…')); $('panel').hidden = false; closeSide();
  try { $('panel-body').replaceChildren(value(await load())); } catch (e) { $('panel-body').replaceChildren(el('p', 'err', e.message)); }
}

// ---------- acțiuni pe conversație ----------
async function threadAction(act) {
  $('thread-menu').hidden = true; if (!current) return;
  try {
    if (act === 'rename') { const name = prompt('Nume nou', $('title').textContent); if (name && name.trim()) { await rpc('thread/name/set', { threadId: current, name: name.trim() }); $('title').textContent = name.trim(); } }
    if (act === 'fork') { const r = await rpc('thread/fork', { threadId: current }); await openThread(r.thread.id); }
    if (act === 'archive') { await rpc('thread/archive', { threadId: current }); newThread(); }
    if (act === 'unarchive') await rpc('thread/unarchive', { threadId: current });
    if (act === 'compact') await rpc('thread/compact/start', { threadId: current });
    if (act === 'delete' && confirm('Ștergi definitiv conversația?')) { await rpc('thread/delete', { threadId: current }); newThread(); }
    loadThreads().catch(() => {});
  } catch (e) { note(e.message, 'err'); }
}

// ---------- imagini (fs/writeFile în directorul de încărcări al punții) ----------
function drawChips() { $('chips').replaceChildren(...chips.map((c, i) => { const s = el('span', 'chip', '🖼 ' + c.name + ' ✕'); s.onclick = () => { chips.splice(i, 1); drawChips(); }; return s; })); }
async function attach(files) {
  for (const file of files) {
    if (file.size > 8 * 1024 * 1024) { note(file.name + ': imaginea depășește 8 MB.', 'err'); continue; }
    try {
      const dir = methods.uploads_dir; await rpc('fs/createDirectory', { path: dir, recursive: true });
      const data = await new Promise((res, rej) => { const r = new FileReader(); r.onload = () => res(String(r.result).split(',')[1]); r.onerror = rej; r.readAsDataURL(file); });
      const path = dir + '/' + Date.now() + '-' + Math.random().toString(16).slice(2, 8) + (/\.[a-z0-9]{1,5}$/i.exec(file.name)?.[0] || '.png').toLowerCase();
      await rpc('fs/writeFile', { path, dataBase64: data }); chips.push({ path, name: file.name }); drawChips();
    } catch (e) { note(file.name + ': ' + e.message, 'err'); }
  }
}

// ---------- autentificare (Google, doar contul permis) ----------
function status(text) { $('status').textContent = text; }
async function signedIn(user) {
  csrf = user.csrf; $('who').textContent = user.email; $('gate').hidden = true; $('app').hidden = false;
  // Pornim de la ultimul eveniment: istoricul vine din thread/resume, cererile în așteptare din /pending.
  try { const h = await api('/api/app/health'); since = h.last_event || 0; link(h.connected, h.connected ? 'Conectat la Codex de pe kelion-nou' : 'Codex indisponibil: ' + (h.last_error || '')); } catch (e) { link(false, e.message); }
  poll();
  try { methods = await api('/api/app/methods'); } catch (e) { note(e.message, 'err'); }
  await Promise.all([loadModels().catch(e => note('Modele: ' + e.message, 'err')), loadThreads().catch(e => note('Istoric: ' + e.message, 'err'))]);
  for (const p of (await api('/api/app/pending').catch(() => ({}))).requests || []) approval(p);
}
async function login() {
  $('signin').disabled = true;
  try {
    const config = await api('/api/config'); const { nonce } = await api('/auth/nonce', {});
    if (!window.google?.accounts?.id) await new Promise((resolve, reject) => { const s = document.createElement('script'); s.src = 'https://accounts.google.com/gsi/client'; s.onload = resolve; s.onerror = () => reject(Error('Biblioteca Google nu a putut fi încărcată.')); document.head.append(s); });
    google.accounts.id.initialize({ client_id: config.clientId, nonce, ux_mode: 'popup', auto_select: false,
      callback: async response => { try { await signedIn(await api('/auth/google', { credential: response.credential })); } catch (e) { status(e.message + ' Repornește conectarea.'); $('signin').hidden = false; $('google').replaceChildren(); } } });
    $('google').replaceChildren(); google.accounts.id.renderButton($('google'), { type: 'standard', theme: 'filled_black', size: 'large' }); status('Alege contul Google autorizat.');
  } catch (e) { status(e.message); } finally { $('signin').disabled = false; }
}

// ---------- legături UI ----------
const fit = () => { const t = $('input'); t.style.height = 'auto'; t.style.height = Math.min(t.scrollHeight, 220) + 'px'; };
const closeSide = () => document.body.classList.remove('side-on');
$('input').addEventListener('input', fit);
$('input').addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); $('composer').requestSubmit(); } });
$('composer').onsubmit = e => { e.preventDefault(); send($('input').value.trim()); };
$('stop').onclick = () => { if (current && active()) rpc('turn/interrupt', { threadId: current, turnId: active() }).catch(e => note(e.message, 'err')); };
$('older').onclick = loadOlder;
$('model').onchange = () => efforts();
$('file').onchange = e => { attach([...e.target.files]); e.target.value = ''; };
$('new-thread').onclick = () => { newThread(); closeSide(); };
$('new-top').onclick = () => newThread();
let searchTimer; $('search').oninput = () => { clearTimeout(searchTimer); searchTimer = setTimeout(() => loadThreads().catch(e => note(e.message, 'err')), 300); };
$('archived').onchange = () => loadThreads().catch(e => note(e.message, 'err'));
$('more-threads').onclick = () => loadThreads(true).catch(e => note(e.message, 'err'));
$('thread-menu-open').onclick = () => { $('thread-menu').hidden = !$('thread-menu').hidden; };
for (const b of $('thread-menu').querySelectorAll('button')) b.onclick = () => threadAction(b.dataset.act);
for (const b of document.querySelectorAll('.nav')) b.onclick = () => openPanel(b.dataset.panel);
$('panel-close').onclick = () => { $('panel').hidden = true; $('panel-title').dataset.kind = ''; };
$('side-open').onclick = () => document.body.classList.add('side-on');
$('side-close').onclick = closeSide;
$('signin').onclick = login;
$('logout').onclick = async () => { try { await api('/auth/logout', {}); } finally { location.reload(); } };

(async () => {
  try {
    const config = await api('/api/config');
    if (!config.ready) { status('Configurare lipsă: ' + config.missing.join(', ') + '.'); return; }
    if (!config.mask) status('Puntea către Codex nu e configurată pe server (KELION_MASK_TOKEN).');
    try { await signedIn(await api('/api/session')); } catch { $('signin').hidden = false; status('Conectează-te cu contul Google autorizat.'); }
  } catch (e) { status(e.message); }
})();
}
