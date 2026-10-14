'use strict';
// Alege vocea română după genul selectat. Numele vocilor diferă între browsere;
// dacă nu există o voce de genul cerut, se folosește vocea română disponibilă cu ton ajustat.
const VOICE_NAMES = { masculin: /emil|andrei|bogdan|male|masculin|bărbat/i, feminin: /ioana|alina|carmen|female|feminin|femeie/i };
export function pickVoice(voices, gender) {
  const ro = voices.filter(v => v.lang.toLowerCase().startsWith('ro'));
  const wanted = gender === 'masculin' ? 'masculin' : 'feminin', other = wanted === 'masculin' ? 'feminin' : 'masculin';
  const exact = ro.find(v => VOICE_NAMES[wanted].test(v.name));
  if (exact) return { voice: exact, pitch: 1 };
  const neutral = ro.find(v => !VOICE_NAMES[other].test(v.name)) || ro[0];
  return { voice: neutral, pitch: wanted === 'masculin' ? 0.75 : 1.1 };
}
// Browser conversation controller. Recognition/synthesis events, not timers, delimit audio.
export class VoiceConversation {
  constructor({ Recognition, synthesis, Utterance, request, onState = () => {}, onTranscript = () => {}, onResult = () => {}, pollMs = 2000, waitMs = 1800000, echoDelayMs = 400, voiceGender = () => 'feminin' }) {
    Object.assign(this, { Recognition, synthesis, Utterance, request, onState, onTranscript, onResult, pollMs, waitMs, echoDelayMs, voiceGender });
    this.active = false; this.generation = 0; this.state = 'idle';
  }
  notify(state, message) { this.state = state; this.onState({ state, message, active: this.active, taskId: this.taskId }); }
  current(generation) { return this.active && this.generation === generation; }
  start() {
    if (this.active) return;
    if (!this.Recognition || !this.synthesis || !this.Utterance) { this.notify('error', 'Conversația vocală nu este disponibilă în acest browser.'); return; }
    this.active = true; this.taskId = null; const generation = ++this.generation;
    this.abort = new AbortController(); this.listen(generation);
  }
  stop(message = 'Conversația s-a încheiat. Cererile deja trimise rămân în istoric.') {
    this.active = false; this.generation++; this.abort?.abort();
    if (this.recognition) { const mic = this.recognition; this.recognition = null; mic.onresult = mic.onerror = mic.onend = mic.onstart = null; try { mic.abort(); } catch {} }
    this.cancelSpeech?.(); this.cancelSpeech = null; this.synthesis?.cancel();
    this.notify('idle', message);
  }
  interrupt() {
    if (!this.active || this.state !== 'speaking') return;
    this.stop('Redare întreruptă.');
    this.active = true; const generation = ++this.generation; this.abort = new AbortController();
    this.notify('starting', 'Redare întreruptă; se reia ascultarea.');
    this.delay(this.echoDelayMs).then(() => { if (this.current(generation)) this.listen(generation); }).catch(() => {});
  }
  fail(message) { this.stop(message); this.notify('error', message); }
  delay(ms) {
    const signal = this.abort.signal;
    return new Promise((resolve, reject) => {
      const cancel = () => { clearTimeout(timer); signal.removeEventListener('abort', cancel); reject(new Error('Conversație oprită')); };
      const timer = setTimeout(() => { signal.removeEventListener('abort', cancel); resolve(); }, ms);
      signal.addEventListener('abort', cancel, { once: true }); if (signal.aborted) cancel();
    });
  }
  listen(generation) {
    if (!this.current(generation)) return;
    const mic = new this.Recognition(); this.recognition = mic;
    mic.lang = 'ro-RO'; mic.continuous = false; mic.interimResults = false; mic.maxAlternatives = 1;
    let consumed = false;
    this.notify('starting', 'Permite microfonul pentru a începe.');
    mic.onstart = () => { if (this.current(generation) && !consumed) this.notify('listening', 'Ascult. Fraza finală va fi trimisă automat.'); };
    mic.onerror = event => {
      if (!this.current(generation) || consumed) return;
      const messages = { 'not-allowed': 'Microfon refuzat. Permite microfonul în browser, apoi apasă Pornește conversația.',
        'service-not-allowed': 'Serviciul de recunoaștere este blocat de browser.', 'audio-capture': 'Microfon indisponibil. Verifică dispozitivul și permisiunea.',
        network: 'Recunoașterea vocală nu are conexiune. Verifică rețeaua și reîncearcă.', 'no-speech': 'Nu am detectat vorbire. Apasă Pornește conversația pentru a relua.' };
      this.fail(messages[event.error] || 'Recunoașterea s-a oprit: ' + event.error + '. Poți relua din buton.');
    };
    mic.onend = () => { if (this.current(generation) && !consumed) this.fail('Ascultarea s-a oprit fără o frază. Apasă Pornește conversația pentru a relua.'); };
    mic.onresult = event => {
      if (!this.current(generation) || consumed) return;
      const final = Array.from(event.results).filter(item => item.isFinal).map(item => item[0].transcript).join(' ').trim();
      if (!final) return;
      consumed = true; this.onTranscript(final); this.notify('submitting', 'Opresc microfonul înainte de a trimite transcrierea.');
      // Require recognition's real end event before dispatch/speech to prevent speaker echo capture.
      const ended = new Promise((resolve, reject) => {
        const timeout = setTimeout(() => reject(new Error('Microfonul nu a confirmat oprirea. Repornește conversația.')), 3000);
        mic.onend = () => { clearTimeout(timeout); if (this.recognition === mic) this.recognition = null; resolve(); };
        mic.onerror = () => {}; mic.onresult = null;
        try { mic.abort(); } catch { clearTimeout(timeout); reject(new Error('Microfonul nu poate fi oprit.')); }
      });
      this.turn(final, generation, ended);
    };
    try { mic.start(); } catch { this.fail('Browserul nu a putut porni microfonul. Verifică permisiunea și reîncearcă.'); }
  }
  async turn(transcript, generation, ended) {
    try {
      await ended; if (!this.current(generation)) return;
      let result;
      try { result = await this.request('/api/tasks', { task: transcript, input_mode: 'voice_transcript' }); }
      catch (error) {
        if (!error.taskId) throw error;
        result = { task_id: error.taskId, state: 'submission_uncertain_readback_required' };
      }
      if (!this.current(generation)) return;
      if (!/^web-[a-f0-9]{32}$/.test(result.task_id)) throw new Error('API-ul nu a returnat un identificator valid de cerere.');
      this.taskId = result.task_id; const taskId = this.taskId, deadline = Date.now() + this.waitMs;
      while (this.current(generation)) {
        if (result.task_id !== taskId) throw new Error('Răspunsul API nu corespunde cererii vocale.');
        this.onResult(result);
        if (result.state === 'result_received' && result.result_retrieved === true && typeof result.output === 'string' && result.output.trim()) break;
        if (['failed', 'blocked_runtime', 'interrupted_requires_reconcile'].includes(result.state)) throw new Error('Cererea ' + taskId + ': ' + (result.failure || result.block_reason || result.state) + '. Consultă istoricul.');
        if (Date.now() >= deadline) throw new Error('Răspunsul întârzie. Cererea ' + taskId + ' rămâne în istoric; nu a fost retrimisă.');
        this.notify('waiting', 'Cerere ' + taskId + ' · stare API: ' + result.state + '. Aștept răspunsul; microfon oprit.');
        await this.delay(this.pollMs); if (!this.current(generation)) return;
        result = await this.request('/api/tasks/' + taskId, undefined, { signal: this.abort.signal });
      }
      if (!this.current(generation)) return;
      await this.speak(result.output, generation);
      if (!this.current(generation)) return;
      this.notify('starting', 'Răspuns redat. Se reia ascultarea.');
      await this.delay(this.echoDelayMs); this.listen(generation);
    } catch (error) { if (this.current(generation)) this.fail(error.message || 'Conversația vocală s-a oprit. Reîncearcă din buton.'); }
  }
  async speak(output, generation) {
    // Bound spoken duration while retaining the full actual response in the text panel.
    let remaining = output.slice(0, 12000);
    this.notify('speaking', output.length > 12000 ? 'Redau primele 12.000 de caractere; răspunsul complet rămâne în text.' : 'Se pregătește redarea răspunsului.');
    while (remaining && this.current(generation)) {
      let cut = Math.min(700, remaining.length); if (cut < remaining.length) { const space = remaining.lastIndexOf(' ', cut); if (space > 350) cut = space; }
      const text = remaining.slice(0, cut); remaining = remaining.slice(cut).trimStart();
      const utterance = new this.Utterance(text); utterance.lang = 'ro-RO';
      const pick = pickVoice(this.synthesis.getVoices(), this.voiceGender());
      if (pick.voice) utterance.voice = pick.voice;
      utterance.pitch = pick.pitch;
      await new Promise((resolve, reject) => {
        let settled = false;
        const finish = error => { if (settled) return; settled = true; clearTimeout(timeout); this.cancelSpeech = null; utterance.onend = utterance.onerror = utterance.onstart = null; error ? reject(error) : resolve(); };
        const timeout = setTimeout(() => finish(new Error('Redarea vocală nu s-a încheiat. Verifică sunetul browserului și reîncearcă.')), 90000);
        this.cancelSpeech = () => finish(new Error('Redare întreruptă'));
        utterance.onstart = () => { if (this.current(generation)) this.notify('speaking', 'Browserul redă răspunsul. Microfonul este oprit.'); };
        utterance.onend = () => finish();
        utterance.onerror = event => finish(new Error('Redarea audio a eșuat: ' + event.error + '. Verifică sunetul browserului; răspunsul rămâne în text.'));
        try { this.synthesis.speak(utterance); } catch { finish(new Error('Browserul nu poate reda vocea.')); }
      });
    }
  }
}

if (typeof document !== 'undefined') {
const $ = id => document.getElementById(id);
let csrf, voiceInput = false, dictation;
async function api(path, data, options = {}) {
  const response = await fetch(path, { method: data === undefined ? 'GET' : 'POST', credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', ...(csrf ? { 'X-CSRF-Token': csrf } : {}) },
    ...(data === undefined ? {} : { body: JSON.stringify(data) }), ...options });
  const result = await response.json();
  if (!response.ok) { const error = Error(result.error || 'Cererea a eșuat'); error.taskId = result.task_id; throw error; }
  return result;
}
function status(message) { $('status').textContent = message; }
const TERMINAL = ['result_received', 'blocked', 'failed', 'blocked_runtime', 'interrupted_requires_reconcile'];
const SURFACES = { chat: 'ChatGPT', codex: 'Codex', work: 'Work (agentul Kelion)', magentic: 'Microsoft Magentic' };
const STEP_STATUS = { running: 'lucrează', completed: 'gata', insufficient: 'insuficient → escaladez', needs_code: 'trece la Codex', needs_tools: 'trece la Work', failed: 'eșuat → escaladez', unavailable: 'indisponibil → următoarea' };
const STATE_TEXT = { awaiting_kelion: 'Cererea a ajuns la Kelion, în coadă', running_magistrala: 'Kelion rutează cererea pe magistrală', result_received: 'Răspuns primit', blocked: 'Blocat' };
// Monitorul de sub roboțel: pașii reali raportați de magistrală (suprafață, raționament, stare, durată).
function renderMonitor(result) {
  const items = [];
  const add = (text, cls = '') => { const li = document.createElement('li'); li.textContent = text; if (cls) li.className = cls; items.push(li); };
  add(new Date().toLocaleTimeString() + ' · ' + (STATE_TEXT[result.state] || 'Stare: ' + result.state), 'state');
  for (const step of result.progress || []) {
    const at = step.at ? new Date(step.at * 1000).toLocaleTimeString() + ' · ' : '';
    add(at + (SURFACES[step.surface] || step.surface || '?') + (step.effort ? ' · raționament ' + step.effort : '') + ' · '
      + (STEP_STATUS[step.status] || step.status) + (Number.isFinite(step.duration_ms) ? ' · ' + (step.duration_ms / 1000).toFixed(1) + ' s' : '') + (step.detail ? ' · ' + step.detail : ''),
      step.status === 'running' ? 'running' : step.status === 'completed' ? 'done' : 'step');
  }
  if (result.block_reason || result.failure) add('Motiv: ' + (result.block_reason || result.failure), 'bad');
  $('monitor').replaceChildren(...items); $('monitor').scrollTop = $('monitor').scrollHeight;
}
// Conversația scrisă (jos): mesajele tale și răspunsurile lui Kelion, separat de monitor.
const answered = new Set();
function bubble(cls, text) {
  // Rândul de scris arată doar ultimul schimb: un mesaj nou de la tine (sau o frază auzită) curăță schimbul anterior.
  if (cls === 'me' || cls === 'heard') $('conv').replaceChildren();
  const p = document.createElement('p'); p.className = 'msg ' + cls; p.textContent = text;
  $('conv').querySelector('.hint')?.remove(); $('conv').append(p); $('conv').scrollTop = $('conv').scrollHeight; return p;
}
// Monitorul arată rezultatele lucrului (blocuri de cod, linkuri); chatul primește textul.
function splitOutput(output) {
  const code = [], links = [];
  const text = output.replace(/```([\w+-]*)\n?([\s\S]*?)```/g, (_, lang, body) => { code.push({ lang, body }); return '[' + (lang || 'cod') + ' pe monitor]'; });
  for (const m of output.matchAll(/https?:\/\/[^\s)<>"']+/g)) if (!links.includes(m[0])) links.push(m[0]);
  return { text: text.trim(), code, links };
}
function renderResults(result, parts) {
  const box = $('results'); box.replaceChildren();
  if (!parts || (!parts.code.length && !parts.links.length)) return;
  const h = document.createElement('h4'); h.textContent = 'Rezultat · ' + result.task_id.slice(0, 12); box.append(h);
  for (const c of parts.code) { const pre = document.createElement('pre'); pre.textContent = c.body; if (c.lang) pre.dataset.lang = c.lang; box.append(pre); }
  for (const url of parts.links.slice(0, 10)) { const a = document.createElement('a'); a.href = url; a.textContent = url; a.target = '_blank'; a.rel = 'noopener noreferrer'; box.append(a); }
}
function showResult(result) {
  renderMonitor(result);
  if (result.output) renderResults(result, splitOutput(result.output));
  if (answered.has(result.task_id)) return;
  if (result.output) { answered.add(result.task_id); document.getElementById('wait-' + result.task_id)?.remove(); bubble('ai', splitOutput(result.output).text || 'Rezultatul e pe monitor.'); }
  else if (TERMINAL.includes(result.state)) { answered.add(result.task_id); document.getElementById('wait-' + result.task_id)?.remove(); bubble('ai bad', 'Nu am putut răspunde. Motivul e pe monitor.'); }
  else if (!document.getElementById('wait-' + result.task_id)) { bubble('ai wait', 'Gândire…').id = 'wait-' + result.task_id; }
}
function asked(text) { if (text) bubble('me', text); }
async function tasks() {
  const result = await api('/api/tasks'); $('tasks').replaceChildren();
  if (!result.tasks.length) $('tasks').textContent = 'Nu ai încă cereri.';
  for (const task of result.tasks) {
    const button = document.createElement('button');
    button.textContent = task.task_id + ' · ' + new Date(task.created).toLocaleString() + ' · ' + task.delivery;
    button.onclick = async () => { $('history').hidden = true; answered.delete(task.task_id); try { following++; const r = await api('/api/tasks/' + task.task_id); showResult(r); if (!TERMINAL.includes(r.state)) follow(r.task_id); } catch (e) { status(e.message); } };
    $('tasks').append(button);
  }
}
// La deschidere: ultimele cereri apar în conversație (mesajul tău + răspunsul), monitorul arată ultima cerere.
async function loadConversation() {
  const list = (await api('/api/tasks')).tasks.slice(0, 1);
  let last;
  for (const t of list) {
    try { last = await api('/api/tasks/' + t.task_id); } catch { continue; }
    const tr = last.task && /^Traduce în [^.]+\. Răspunde doar cu traducerea, fără alt text:\n/.exec(last.task);
    if (tr) bubble('heard', '🎧 ' + last.task.slice(tr[0].length)); else if (last.task) bubble('me', last.task);
    showResult(last);
  }
  if (last && !TERMINAL.includes(last.state)) follow(last.task_id);
}
async function signedIn(user) {
  csrf = user.csrf; $('account').textContent = user.email; $('avatar').textContent = (user.email || '?').slice(0, 2).toUpperCase(); $('workspace').hidden = false;
  $('signin').hidden = true; $('google').replaceChildren(); status(''); await tasks(); await loadConversation().catch(e => status(e.message));
}
async function login() {
  $('signin').disabled = true;
  try {
    const config = await api('/api/config');
    const { nonce } = await api('/auth/nonce', {});
    if (!window.google?.accounts?.id) {
      await new Promise((resolve, reject) => {
        const script = document.createElement('script'); script.src = 'https://accounts.google.com/gsi/client';
        script.onload = resolve; script.onerror = () => reject(Error('Biblioteca Google nu a putut fi încărcată.')); document.head.append(script);
      });
    }
    google.accounts.id.initialize({ client_id: config.clientId, nonce, ux_mode: 'popup', auto_select: false,
      callback: async response => { try { await signedIn(await api('/auth/google', { credential: response.credential })); }
        catch (e) { status(e.message + ' Repornește conectarea.'); $('signin').hidden = false; $('google').replaceChildren(); } } });
    $('google').replaceChildren(); google.accounts.id.renderButton($('google'), { type: 'standard', theme: 'outline', size: 'large' });
    status('Alege contul Google autorizat.');
  } catch (e) { status(e.message); } finally { $('signin').disabled = false; }
}
$('signin').onclick = login;
$('logout').onclick = async () => { conversation.stop(); dictation?.abort(); try { await api('/auth/logout', {}); location.reload(); } catch (e) { status(e.message); } };
$('history-open').onclick = () => { closeMenu(); $('settings').hidden = true; $('history').hidden = false; tasks().catch(e => status(e.message)); };
const closeMenu = () => { $('menu').hidden = true; $('menu-open').setAttribute('aria-expanded', 'false'); };
$('menu-open').onclick = () => { const open = $('menu').hidden; $('menu').hidden = !open; $('menu-open').setAttribute('aria-expanded', String(open)); };
$('plus').onclick = () => $('menu-open').click();
document.addEventListener('click', e => { if (!$('menu').hidden && !e.target.closest('#menu, #menu-open, #plus')) closeMenu(); });
$('settings-open').onclick = async () => { closeMenu(); $('history').hidden = true; $('settings').hidden = false;
  try { const c = await api('/api/config'); $('server-state').textContent = (c.ready ? 'Pagina web: configurată.' : 'Pagina web: lipsesc ' + c.missing.join(', ') + '.')
    + ' Starea ultimei cereri apare pe monitor.'; } catch (e) { $('server-state').textContent = 'Serverul nu răspunde: ' + e.message; } };
$('settings-close').onclick = () => { $('settings').hidden = true; };
$('history-close').onclick = () => { $('history').hidden = true; };
$('refresh').onclick = () => tasks().catch(e => status(e.message));
$('task').addEventListener('input', () => { voiceInput = false; });
$('task').addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); $('chat').requestSubmit(); } });
let following = 0;
async function follow(taskId) {
  const mine = ++following; kelionState('waiting');
  for (let i = 0; i < 900 && mine === following; i++) {
    await new Promise(resolve => setTimeout(resolve, 2000)); if (mine !== following) return;
    let result; try { result = await api('/api/tasks/' + taskId); } catch (e) { status(e.message); continue; }
    if (mine !== following) return;
    showResult(result);
    if (TERMINAL.includes(result.state)) { kelionState(result.state === 'result_received' ? 'idle' : 'error'); tasks().catch(() => {}); return; }
  }
}
$('chat').onsubmit = async event => {
  event.preventDefault(); $('send').disabled = true;
  const text = $('task').value; asked(text);
  try { const result = await api('/api/tasks', { task: text, input_mode: voiceInput ? 'voice_transcript' : 'text' }); showResult(result); $('task').value = ''; voiceInput = false; status('Cerere trimisă. Monitorul arată progresul în timp real.'); follow(result.task_id); }
  catch (e) { status(e.message + (e.taskId ? ' ID: ' + e.taskId : '')); }
  finally { $('send').disabled = false; await tasks().catch(e => status(e.message)); }
};
const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
const KELION_LABELS = { idle: 'Pregătit', starting: 'Pornesc microfonul…', listening: 'Te ascult…', submitting: 'Am înțeles, trimit…', waiting: 'Gândire', speaking: 'Vorbesc…', error: 'Ceva nu a mers' };
const CALL_TITLES = { starting: 'Se apelează…', listening: 'Te ascult…', submitting: 'Trimit…', waiting: 'Gândire…', speaking: 'Kelion vorbește', error: 'Apel oprit' };
function kelionState(state) { const k = document.getElementById('kelion'); if (k) k.dataset.state = state in KELION_LABELS ? state : 'idle'; const l = document.getElementById('kelion-state'); if (l) l.textContent = KELION_LABELS[state] || KELION_LABELS.idle; }
const GENDER_KEY = 'kelion-voice-gender';
try { const saved = localStorage.getItem(GENDER_KEY); if (saved === 'masculin' || saved === 'feminin') $('voice-gender').value = saved; } catch {}
$('voice-gender').onchange = () => { try { localStorage.setItem(GENDER_KEY, $('voice-gender').value); } catch {} };
const conversation = new VoiceConversation({ Recognition, synthesis: window.speechSynthesis, Utterance: window.SpeechSynthesisUtterance, request: api, voiceGender: () => $('voice-gender').value,
  onState: ({ state, message, active }) => { kelionState(state); $('call-status').textContent = message; $('call-start').disabled = active; $('call-end').disabled = !active; $('call-card').hidden = !active; $('call-title').textContent = CALL_TITLES[state] || 'Apel cu Kelion';
    $('call-interrupt').disabled = state !== 'speaking'; $('send').disabled = active; $('task').disabled = active; },
  onTranscript: text => { $('voice-transcript').textContent = ''; asked(text); },
  onResult: result => { showResult(result); if (result.state === 'result_received') tasks().catch(() => {}); },
});
if (Recognition && window.speechSynthesis && window.SpeechSynthesisUtterance) {
  $('call-start').disabled = false; $('call-status').textContent = 'Pregătit. Pornește conversația când dorești să folosești microfonul.';
} else $('call-status').textContent = 'Conversația vocală nu este disponibilă: browserul trebuie să ofere recunoaștere și redare vocală. Poți folosi chatul text.';
// Ascultă și traduce: ce aude microfonul (în limba aleasă) apare tradus în limba ta, doar scris, fără voce.
const LANG_KEY = 'kelion-lang', SRC_KEY = 'kelion-src-lang';
const langName = code => $('user-lang').querySelector('option[value="' + code + '"]')?.textContent || code;
try {
  const saved = localStorage.getItem(LANG_KEY), nav = navigator.language || 'ro-RO';
  const guess = [...$('user-lang').options].find(o => o.value === saved) || [...$('user-lang').options].find(o => o.value.slice(0, 2) === nav.slice(0, 2));
  if (guess) $('user-lang').value = guess.value;
  const src = localStorage.getItem(SRC_KEY); if (src) $('src-lang').value = src; else $('src-lang').value = $('user-lang').value === 'en-US' ? 'ro-RO' : 'en-US';
} catch {}
$('user-lang').onchange = () => { try { localStorage.setItem(LANG_KEY, $('user-lang').value); } catch {} };
async function translateResult(taskId) {
  for (let i = 0; i < 150; i++) {
    await new Promise(r => setTimeout(r, 2000));
    let r; try { r = await api('/api/tasks/' + taskId); } catch { continue; }
    showResult(r); if (TERMINAL.includes(r.state)) return;
  }
}
const translator = { active: false, mic: null };
function translatorStop(message) {
  translator.active = false; const mic = translator.mic; translator.mic = null;
  if (mic) { mic.onresult = mic.onend = mic.onerror = null; try { mic.abort(); } catch {} }
  $('tr-card').hidden = true; $('translate').setAttribute('aria-pressed', 'false'); if (message) status(message);
}
function translatorListen() {
  if (!translator.active) return;
  const mic = new Recognition(); translator.mic = mic;
  mic.lang = $('src-lang').value; mic.continuous = true; mic.interimResults = false;
  mic.onresult = async event => {
    for (let i = event.resultIndex; i < event.results.length; i++) {
      if (!event.results[i].isFinal) continue;
      const heard = event.results[i][0].transcript.trim(); if (!heard) continue;
      bubble('heard', '🎧 ' + heard);
      try {
        const r = await api('/api/tasks', { task: 'Traduce în ' + langName($('user-lang').value) + '. Răspunde doar cu traducerea, fără alt text:\n' + heard, input_mode: 'voice_transcript' });
        showResult(r); translateResult(r.task_id);
      } catch (e) { status(e.message); }
    }
  };
  mic.onerror = event => { if (['not-allowed', 'service-not-allowed', 'audio-capture'].includes(event.error)) translatorStop('Microfon indisponibil sau refuzat pentru traducere.'); };
  mic.onend = () => { if (translator.active && translator.mic === mic) translatorListen(); };  // repornește la evenimentul de oprire al browserului
  try { mic.start(); $('tr-status').textContent = 'Ascult ' + langName($('src-lang').value) + ' → scriu în ' + langName($('user-lang').value) + '. Fără voce.'; }
  catch { translatorStop('Browserul nu a putut porni microfonul.'); }
}
$('src-lang').onchange = () => { try { localStorage.setItem(SRC_KEY, $('src-lang').value); } catch {} if (translator.active) { const mic = translator.mic; translator.mic = null; if (mic) { mic.onend = null; try { mic.abort(); } catch {} } translatorListen(); } };
$('tr-stop').onclick = () => translatorStop();
if (Recognition) {
  $('translate-wrap').hidden = false;
  // T: oprește chatul full duplex și pornește traducerea (becul se aprinde); a doua apăsare stinge becul și repornește full duplex.
  $('translate').onclick = () => {
    if (!csrf) { status('Conectează-te întâi.'); return; }
    if (translator.active) { translatorStop(); conversation.start(); return; }
    if (conversation.active) conversation.stop('Chatul vocal e oprit cât traduc.');
    translator.active = true; $('tr-card').hidden = false; $('translate').setAttribute('aria-pressed', 'true'); translatorListen();
  };
}
$('call-start').onclick = () => { following++; if (translator.active) translatorStop(); if (!csrf) { status('Conectează-te înainte să pornești conversația vocală.'); return; } dictation?.abort(); conversation.start(); };
$('call-end').onclick = () => conversation.stop();
$('call-interrupt').onclick = () => conversation.interrupt();
window.addEventListener('pagehide', () => { translatorStop(); conversation.stop(); dictation?.abort(); });
document.addEventListener('visibilitychange', () => { if (document.hidden && conversation.active) conversation.stop('Conversația s-a oprit deoarece pagina nu mai este vizibilă.'); });

(async () => {
  try {
    const config = await api('/api/config');
    if (!config.ready) { status('Configurare lipsă: ' + config.missing.join(', ') + '. Conectarea și trimiterea sunt dezactivate.'); return; }
    try { await signedIn(await api('/api/session')); } catch { $('signin').hidden = false; status('Conectează-te cu un cont Google autorizat.'); }
  } catch (e) { status(e.message); }
})();
}
