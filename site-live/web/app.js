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
      if (['no-speech', 'aborted'].includes(event.error)) return;  // apel permanent: tăcerea nu închide apelul
      const messages = { 'not-allowed': 'Microfon refuzat. Permite microfonul în browser, apoi apasă Pornește conversația.',
        'service-not-allowed': 'Serviciul de recunoaștere este blocat de browser.', 'audio-capture': 'Microfon indisponibil. Verifică dispozitivul și permisiunea.',
        network: 'Recunoașterea vocală nu are conexiune. Verifică rețeaua și reîncearcă.', 'no-speech': 'Nu am detectat vorbire. Apasă Pornește conversația pentru a relua.' };
      this.fail(messages[event.error] || 'Recunoașterea s-a oprit: ' + event.error + '. Poți relua din buton.');
    };
    // Apel permanent: când browserul închide ascultarea fără frază, se reia (eveniment, nu temporizator de așteptare).
    mic.onend = () => { if (this.current(generation) && !consumed) this.delay(300).then(() => { if (this.current(generation)) this.listen(generation); }).catch(() => {}); };
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
      try { const ack = new this.Utterance('Mă gândesc.'); ack.lang = 'ro-RO'; this.synthesis.speak(ack); } catch {}
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
    } catch (error) {
      // Cererea a eșuat sau s-a blocat: raportez real (pe monitor și aici), apelul rămâne deschis și ascultă mai departe.
      if (!this.current(generation)) return;
      this.notify('error', (error.message || 'Cererea nu a primit răspuns.') + ' Ascult în continuare.');
      try { await this.delay(1500); } catch { return; }
      if (this.current(generation)) this.listen(generation);
    }
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

// Detector de vorbire (VAD) pe nivelul sunetului: începutul și sfârșitul fiecărei fraze, prag adaptat la zgomot.
export function createVad({ minThreshold = 0.012, factor = 3, silenceMs = 900, minSpeechMs = 350, maxMs = 30000 } = {}) {
  let noise = 0.008, speaking = false, start = 0, lastVoice = 0;
  return function step(rms, t) {
    const threshold = Math.max(minThreshold, noise * factor);
    if (!speaking) {
      if (rms > threshold) { speaking = true; start = lastVoice = t; return 'start'; }
      noise = noise * 0.95 + rms * 0.05; return null;
    }
    if (rms > threshold) lastVoice = t;
    if (t - lastVoice > silenceMs || t - start > maxMs) { speaking = false; return lastVoice - start >= minSpeechMs ? 'end' : 'discard'; }
    return null;
  };
}
// Voce prin serviciul DOTS de pe server: frază → /api/voice/stt → magistrală (Kelion alege canalul) → /api/voice/tts → redare.
// Full duplex prin întrerupere: dacă vorbești peste răspuns, redarea se oprește și fraza nouă e preluată.
export class ServerVoice {
  constructor({ media, AudioCtx, Recorder, stt, tts, request, play, onState = () => {}, onTranscript = () => {}, onResult = () => {}, pollMs = 1500, waitMs = 600000, vad = createVad() }) {
    Object.assign(this, { media, AudioCtx, Recorder, stt, tts, request, play, onState, onTranscript, onResult, pollMs, waitMs, vad });
    this.active = false; this.state = 'idle'; this.queue = Promise.resolve();
  }
  notify(state, message) { this.state = state; this.onState({ state, message, active: this.active }); }
  async start() {
    if (this.active) return;
    if (!this.media?.getUserMedia || !this.AudioCtx || !this.Recorder) { this.notify('error', 'Browserul nu oferă microfon pentru vocea Kelion.'); return; }
    this.active = true; this.notify('starting', 'Pornesc microfonul…');
    try { this.stream = await this.media.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } }); }
    catch { this.active = false; this.notify('error', 'Microfon refuzat sau indisponibil. Permite microfonul și reîncearcă.'); return; }
    if (!this.active) { this.stream.getTracks().forEach(t => t.stop()); return; }
    this.ctx = new this.AudioCtx(); const source = this.ctx.createMediaStreamSource(this.stream);
    this.analyser = this.ctx.createAnalyser(); this.analyser.fftSize = 1024; source.connect(this.analyser);
    const buf = new Float32Array(this.analyser.fftSize);
    this.timer = setInterval(() => {
      this.analyser.getFloatTimeDomainData(buf); let sum = 0; for (const v of buf) sum += v * v;
      this.onLevel(Math.sqrt(sum / buf.length), performance.now());
    }, 40);
    this.notify('listening', 'Te ascult. Vorbește când vrei; poți întrerupe răspunsul vorbind.');
  }
  onLevel(rms, t) {
    const event = this.vad(rms, t);
    if (event === 'start') {
      this.stopPlayback();  // vorbești peste răspuns: îl opresc
      this.chunks = []; this.recorder = new this.Recorder(this.stream);
      this.recorder.ondataavailable = e => { if (e.data?.size) this.chunks.push(e.data); };
      this.recorder.start(); this.notify('listening', 'Te aud…');
    } else if (event === 'end' || event === 'discard') {
      const rec = this.recorder, chunks = this.chunks; this.recorder = null; if (!rec) return;
      rec.onstop = () => { if (event === 'end' && this.active && chunks.length) { const blob = new Blob(chunks, { type: rec.mimeType || chunks[0].type || 'audio/webm' }); this.queue = this.queue.then(() => this.turn(blob)).catch(() => {}); } };
      try { rec.stop(); } catch {}
    }
  }
  stopPlayback() { if (this.playing) { try { this.playing.stop(); } catch {} this.playing = null; } }
  async turn(blob) {
    if (!this.active) return;
    try {
      this.notify('submitting', 'Transcriu pe server…');
      const text = (await this.stt(blob)).trim(); if (!this.active) return;
      if (!text) { this.notify('listening', 'Nu am înțeles; te ascult.'); return; }
      this.onTranscript(text); this.notify('waiting', 'Kelion lucrează pe canalul ales…');
      // Fără tăcere: o confirmare scurtă imediat, până vine răspunsul (vorbitul o întrerupe ca pe orice răspuns).
      if (!this.ack) this.ack = this.tts('Mă gândesc.').catch(() => null);
      this.ack.then(b => { if (b && this.active && this.state === 'waiting' && !this.playing) this.playing = this.play(b, () => { this.playing = null; }); });
      let result = await this.request('/api/tasks', { task: text, input_mode: 'voice_transcript' });
      const id = result.task_id, deadline = Date.now() + this.waitMs;
      while (this.active) {
        this.onResult(result);
        if (result.state === 'result_received' && result.output) break;
        if (['blocked', 'failed', 'blocked_runtime', 'interrupted_requires_reconcile'].includes(result.state)) { this.notify('error', 'Cererea nu a primit răspuns: ' + (result.block_reason || result.failure || result.state) + ' Ascult în continuare.'); return; }
        if (Date.now() > deadline) { this.notify('error', 'Răspunsul întârzie; cererea rămâne în istoric. Ascult în continuare.'); return; }
        await new Promise(r => setTimeout(r, this.pollMs)); if (!this.active) return;
        result = await this.request('/api/tasks/' + id);
      }
      if (!this.active) return;
      this.notify('speaking', 'Kelion îți răspunde (vorbește ca să întrerupi).');
      const audio = await this.tts(result.output.slice(0, 1500)); if (!this.active) return;
      this.playing = this.play(audio, () => { this.playing = null; if (this.active) this.notify('listening', 'Te ascult.'); });
    } catch (error) { if (this.active) this.notify('error', (error.message || 'Vocea a întâmpinat o eroare.') + ' Ascult în continuare.'); }
  }
  interrupt() { this.stopPlayback(); if (this.active) this.notify('listening', 'Te ascult.'); }
  stop(message = 'Conversația s-a încheiat.') {
    this.active = false; clearInterval(this.timer); this.stopPlayback();
    try { this.recorder?.stop(); } catch {} this.recorder = null;
    this.stream?.getTracks().forEach(t => t.stop()); this.stream = null;
    try { this.ctx?.close(); } catch {} this.ctx = null;
    this.notify('idle', message);
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
const SURFACES = { chat: 'Codex (chat) · cota Codex/Work', codex: 'Codex · cota Codex/Work', work: 'Work (agentul Kelion) · cota Codex/Work', magentic: 'Microsoft Magentic' };
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
// Starea lucrului pe server (pentru raportare pe monitor).
let workRoute = 'unknown';
function routeNote(text) { const li = document.createElement('li'); li.className = 'state'; li.textContent = new Date().toLocaleTimeString() + ' · ' + text; $('monitor').prepend(li); }
function showResult(result) {
  if (result.state === 'result_received' && result.output) workRoute = 'ok';
  else if (TERMINAL.includes(result.state)) workRoute = 'blocked';
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
$('history-open').onclick = () => { closeMenu(); $('history').hidden = false; tasks().catch(e => status(e.message)); };
// Avatarul (ca în ChatGPT) deschide meniul contului: email, Voce, Limba ta, Ieșire.
const closeMenu = () => { $('menu').hidden = true; $('avatar').setAttribute('aria-expanded', 'false'); };
$('avatar').onclick = () => { const open = $('menu').hidden; $('menu').hidden = !open; $('avatar').setAttribute('aria-expanded', String(open)); };
$('plus').onclick = () => { closeMenu(); $('attach').hidden = !$('attach').hidden; };
document.addEventListener('click', e => { if (!$('attach').hidden && !e.target.closest('#attach, #plus')) $('attach').hidden = true; });
// GPS: locația se pune în mesaj, tu decizi dacă o trimiți.
$('geo').onclick = () => {
  $('attach').hidden = true;
  if (!navigator.geolocation) { status('Browserul nu oferă locație.'); return; }
  status('Cer locația (permite accesul în browser)…');
  navigator.geolocation.getCurrentPosition(pos => {
    const { latitude: la, longitude: lo, accuracy } = pos.coords;
    const line = '📍 Locația mea: ' + la.toFixed(5) + ', ' + lo.toFixed(5) + ' (±' + Math.round(accuracy) + ' m) https://maps.google.com/?q=' + la.toFixed(5) + ',' + lo.toFixed(5);
    $('task').value = ($('task').value ? $('task').value + '\n' : '') + line; $('task').focus(); status('');
  }, err => status('Locația nu a fost primită: ' + (err.code === 1 ? 'acces refuzat' : err.message)), { enableHighAccuracy: true, timeout: 20000, maximumAge: 0 });
};
// Camera față/spate: previzualizare pe monitor, poza rămâne pe monitor.
const cam = { stream: null, facing: 'user' };
function camStop() { cam.stream?.getTracks().forEach(t => t.stop()); cam.stream = null; $('cam-video').srcObject = null; $('cam-card').hidden = true; }
async function camStart(facing) {
  $('attach').hidden = true; camStop(); cam.facing = facing;
  if (!navigator.mediaDevices?.getUserMedia) { status('Browserul nu oferă acces la cameră.'); return; }
  try {
    cam.stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: facing } }, audio: false });
    $('cam-video').srcObject = cam.stream; $('cam-card').hidden = false; status('');
  } catch (e) { status('Camera nu a pornit: ' + (e.name === 'NotAllowedError' ? 'acces refuzat' : e.message)); }
}
$('cam-front').onclick = () => camStart('user');
$('cam-back').onclick = () => camStart('environment');
$('cam-flip').onclick = () => camStart(cam.facing === 'user' ? 'environment' : 'user');
$('cam-close').onclick = camStop;
$('cam-shot').onclick = () => {
  const v = $('cam-video'); if (!v.videoWidth) return;
  const canvas = document.createElement('canvas'); const scale = Math.min(1, 1280 / v.videoWidth);
  canvas.width = Math.round(v.videoWidth * scale); canvas.height = Math.round(v.videoHeight * scale);
  canvas.getContext('2d').drawImage(v, 0, 0, canvas.width, canvas.height);
  const img = document.createElement('img'); img.src = canvas.toDataURL('image/jpeg', 0.85); img.alt = 'Poză de la cameră';
  const h = document.createElement('h4'); h.textContent = 'Poză · ' + new Date().toLocaleTimeString();
  camStop(); $('results').replaceChildren(h, img);
  status('Poza e pe monitor. Trimiterea pozelor către Kelion se activează după ce serverul primește imagini.');
};
document.addEventListener('click', e => { if (!$('menu').hidden && !e.target.closest('#menu, #avatar, #plus')) closeMenu(); });
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
const browserVoice = new VoiceConversation({ Recognition, synthesis: window.speechSynthesis, Utterance: window.SpeechSynthesisUtterance, request: api, voiceGender: () => $('voice-gender').value,
  onState: ({ state, message, active }) => { kelionState(state); $('call-status').textContent = message; $('call-start').disabled = active; $('call-end').disabled = !active; $('call-card').hidden = !active; $('call-title').textContent = CALL_TITLES[state] || 'Apel cu Kelion';
    $('call-interrupt').disabled = state !== 'speaking'; $('send').disabled = active; $('task').disabled = active; },
  onTranscript: text => { $('voice-transcript').textContent = ''; asked(text); },
  onResult: result => { showResult(result); if (result.state === 'result_received') tasks().catch(() => {}); },
});
// Vocea prin serviciul DOTS de pe server (când e instalat): aceleași afișări, ruta audio rămâne în aplicație.
const pickMime = () => ['audio/webm;codecs=opus', 'audio/ogg;codecs=opus', 'audio/mp4'].find(t => window.MediaRecorder?.isTypeSupported?.(t)) || '';
const serverVoice = new ServerVoice({
  media: navigator.mediaDevices, AudioCtx: window.AudioContext || window.webkitAudioContext,
  Recorder: window.MediaRecorder ? function (stream) { const m = pickMime(); return new MediaRecorder(stream, m ? { mimeType: m } : undefined); } : null,
  request: api,
  stt: async blob => {
    const r = await fetch('/api/voice/stt', { method: 'POST', credentials: 'same-origin', body: blob,
      headers: { 'Content-Type': blob.type || 'audio/webm', 'X-CSRF-Token': csrf, 'X-Kelion-Lang': $('user-lang').value.slice(0, 2) } });
    const j = await r.json().catch(() => ({})); if (!r.ok) throw Error(j.error || 'Transcrierea a eșuat'); return j.text || '';
  },
  tts: async text => {
    const r = await fetch('/api/voice/tts', { method: 'POST', credentials: 'same-origin', body: JSON.stringify({ text, lang: $('user-lang').value.slice(0, 2) }),
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf } });
    if (!r.ok) { const j = await r.json().catch(() => ({})); throw Error(j.error || 'Sinteza vocală a eșuat'); } return r.blob();
  },
  play: (blob, onEnd) => {
    const url = URL.createObjectURL(blob), el = new Audio(url), done = () => { URL.revokeObjectURL(url); onEnd(); };
    el.onended = done; el.onerror = done; el.play().catch(done);
    return { stop() { el.onended = el.onerror = null; el.pause(); URL.revokeObjectURL(url); } };
  },
  onState: browserVoice.onState, onTranscript: browserVoice.onTranscript, onResult: browserVoice.onResult,
});
// Un singur microfon: ruta audio e mereu în aplicație; serverul DOTS dacă e instalat, altfel recunoașterea din browser.
const conversation = {
  impl: browserVoice,
  get active() { return this.impl.active; },
  start() { return this.impl.start(); }, stop(message) { return this.impl.stop(message); }, interrupt() { return this.impl.interrupt(); },
};
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
$('call-start').onclick = () => {
  // Microfonul deschide doar ruta audio, în aplicație. Canalul (chat/codex/work/magentic) îl alege Kelion în spate, pe magistrală.
  following++; if (translator.active) translatorStop();
  if (!csrf) { status('Conectează-te înainte să pornești conversația vocală.'); return; }
  routeNote('Voce: ascult în aplicație; Kelion alege canalul pentru fiecare cerere.');
  conversation.start();
};
$('call-end').onclick = () => conversation.stop();
$('call-interrupt').onclick = () => conversation.interrupt();
window.addEventListener('pagehide', () => { camStop(); translatorStop(); conversation.stop(); dictation?.abort(); });
document.addEventListener('visibilitychange', () => { if (document.hidden && conversation.active) conversation.stop('Conversația s-a oprit deoarece pagina nu mai este vizibilă.'); });

(async () => {
  try {
    const config = await api('/api/config');
    if (!config.ready) { status('Configurare lipsă: ' + config.missing.join(', ') + '. Conectarea și trimiterea sunt dezactivate.'); return; }
    if (config.voice) { conversation.impl = serverVoice; $('call-start').disabled = false; $('call-status').textContent = 'Voce prin serviciul DOTS de pe server.'; }
    try { await signedIn(await api('/api/session')); } catch { $('signin').hidden = false; status('Conectează-te cu un cont Google autorizat.'); }
  } catch (e) { status(e.message); }
})();
}
