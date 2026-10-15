// Teste pentru logica măștii (fără browser): node --test site-live/web/test_mask.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { TurnState, olderTurns, turnItems, sendFailure, markdown, monitorDirective, monitorView } from './app.js';

test('turn/completed înaintea răspunsului HTTP turn/start nu repune turnul activ', () => {
  const s = new TurnState();
  s.completed('u1');                       // notificarea ajunge prima
  assert.equal(s.started('u1'), null);     // apoi răspunsul HTTP cu turn.id = u1
  assert.equal(s.active, null);
});

test('ordinea normală: started apoi completed', () => {
  const s = new TurnState();
  assert.equal(s.started('u2'), 'u2');
  assert.equal(s.completed('u2'), null);
  assert.equal(s.started('u3'), 'u3');     // un turn nou poate porni
});

test('istoric paginat pe două pagini, fără dubluri, în ordine cronologică', async () => {
  // turnuri u1..u5; resume a afișat u4, u5; ancora (u4) e inclusă în prima pagină.
  const pages = {
    c4: { data: [{ id: 'u4' }, { id: 'u3' }], nextCursor: 'c2' },
    c2: { data: [{ id: 'u2' }, { id: 'u1' }], nextCursor: null },
  };
  const calls = [];
  const rpc = async (method, params) => { calls.push([method, params]); return pages[params.cursor]; };
  const seen = new Set(['u4', 'u5']);
  const p1 = await olderTurns(rpc, 't1', 'c4', seen);
  assert.deepEqual(p1.turns.map(t => t.id), ['u3']);
  assert.equal(p1.cursor, 'c2');
  p1.turns.forEach(t => seen.add(t.id));
  const p2 = await olderTurns(rpc, 't1', p1.cursor, seen);
  assert.deepEqual(p2.turns.map(t => t.id), ['u1', 'u2']);
  assert.equal(p2.cursor, null);
  assert.deepEqual(calls.map(([m, p]) => [m, p.sortDirection, p.itemsView]), [['thread/turns/list', 'desc', 'full'], ['thread/turns/list', 'desc', 'full']]);
});

test('turn sumar: elementele complete vin din thread/items/list, toate paginile', async () => {
  const pages = { undefined: { data: [{ id: 'a' }], nextCursor: 'k' }, k: { data: [{ id: 'b' }], nextCursor: null } };
  const rpc = async (method, params) => { assert.equal(method, 'thread/items/list'); assert.equal(params.turnId, 'u1'); return pages[params.cursor]; };
  assert.deepEqual((await turnItems(rpc, 't1', { id: 'u1', itemsView: 'summary', items: [{ id: 'x' }] })).map(i => i.id), ['a', 'b']);
  assert.deepEqual(await turnItems(async () => assert.fail('nu trebuie apelat'), 't1', { id: 'u2', itemsView: 'full', items: [{ id: 'y' }] }), [{ id: 'y' }]);
});

test('eșec sigur față de trimitere incertă', () => {
  const bridge = reason => Object.assign(Error('x'), { rpc: { code: -32000, data: { source: 'kelion-mask-bridge', reason } } });
  assert.equal(sendFailure(bridge('disconnected')), 'uncertain');   // conexiune întreruptă în punte
  assert.equal(sendFailure(Object.assign(Error('x'), { rpc: { code: -32001, data: { source: 'kelion-mask-bridge', reason: 'timeout' } } })), 'uncertain');
  assert.equal(sendFailure(bridge('unavailable')), 'failed');       // app-server indisponibil înainte de trimitere
  assert.equal(sendFailure(Object.assign(Error('x'), { rpc: { code: -32003, data: { source: 'kelion-mask-bridge', reason: 'blocked' } } })), 'failed');
  assert.equal(sendFailure(Object.assign(Error('x'), { rpc: { code: -32000, message: 'Your workspace is out of credits' } })), 'failed');  // app-server a refuzat
  assert.equal(sendFailure(Object.assign(Error('x'), { rpc: { code: -32600 } })), 'failed');
  assert.equal(sendFailure(Object.assign(Error('x'), { status: 400 })), 'failed');
  assert.equal(sendFailure(Object.assign(Error('x'), { status: 502 })), 'uncertain');
  assert.equal(sendFailure(new TypeError('Failed to fetch')), 'uncertain');
});

test('markdown escapează HTML și permite doar linkuri http(s)', () => {
  assert.ok(!markdown('<img src=x onerror=1>').includes('<img'));
  assert.ok(!markdown('[a](javascript:alert(1))').includes('href'));
});

test('monitor: directiva din răspuns, ultima câștigă; JSON invalid ignorat', () => {
  const t = 'Iată harta.\n```kelion-monitor\n{"action":"open","type":"map","lat":44.43,"lon":26.1,"zoom":12,"title":"București"}\n```';
  assert.equal(monitorDirective(t).type, 'map');
  assert.equal(monitorDirective('```kelion-monitor\n{x}\n```'), null);
  assert.equal(monitorDirective('fără bloc'), null);
});

test('monitor: vizualizări sigure pentru video, hartă, web, imagine, text, închidere', () => {
  const yt = monitorView({ action: 'open', type: 'video', url: 'https://www.youtube.com/watch?v=dQw4w9WgXcQ' });
  assert.equal(yt.src, 'https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ?autoplay=1');
  assert.equal(monitorView({ action: 'open', type: 'video', url: 'https://youtu.be/dQw4w9WgXcQ' }).kind, 'frame');
  assert.equal(monitorView({ action: 'open', type: 'video', url: 'https://cdn.example.com/a.mp4' }).kind, 'link');   // fără încărcare automată
  assert.equal(monitorView({ action: 'open', type: 'video', url: 'http://insecure.example.com/a.mp4' }), null);
  assert.equal(monitorView({ action: 'open', type: 'web', url: 'javascript:alert(1)' }), null);
  const map = monitorView({ action: 'open', type: 'map', lat: 44.43, lon: 26.1, zoom: 12 });
  assert.match(map.src, /^https:\/\/www\.openstreetmap\.org\/export\/embed\.html\?bbox=/);
  assert.equal(monitorView({ action: 'open', type: 'map', lat: 'x', lon: 1 }), null);
  assert.equal(monitorView({ action: 'open', type: 'image', url: 'https://example.com/a.png' }).kind, 'link');
  assert.equal(monitorView({ action: 'open', type: 'web', url: 'https://example.com/' }).kind, 'link');
  assert.equal(monitorView({ action: 'open', type: 'text', text: '# Meteo' }).kind, 'text');
  assert.deepEqual(monitorView({ action: 'close' }), { kind: 'close' });
  assert.equal(monitorView({ action: 'open', type: 'html', text: '<script>' }), null);
});
