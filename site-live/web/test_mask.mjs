// Teste pentru logica măștii (fără browser): node --test site-live/web/test_mask.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { TurnState, olderTurns, turnItems, sendFailure, markdown } from './app.js';

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
  assert.equal(sendFailure(Object.assign(Error('x'), { rpc: { code: -32000 } })), 'failed');
  assert.equal(sendFailure(Object.assign(Error('x'), { status: 400 })), 'failed');
  assert.equal(sendFailure(Object.assign(Error('x'), { status: 502 })), 'uncertain');
  assert.equal(sendFailure(new TypeError('Failed to fetch')), 'uncertain');
});

test('markdown escapează HTML și permite doar linkuri http(s)', () => {
  assert.ok(!markdown('<img src=x onerror=1>').includes('<img'));
  assert.ok(!markdown('[a](javascript:alert(1))').includes('href'));
});
