import { promises as fs } from 'node:fs';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { requireValue, SiwcError } from './oauth.mjs';
import { PERMISSION_PROFILE } from './permissions.mjs';

export const METHODS = Object.freeze({ initialize: 'v1/InitializeParams.json', 'thread/start': 'v2/ThreadStartParams.json', 'thread/resume': 'v2/ThreadResumeParams.json', 'turn/start': 'v2/TurnStartParams.json', 'thread/read': 'v2/ThreadReadParams.json', 'turn/interrupt': 'v2/TurnInterruptParams.json', 'command/exec': 'v2/CommandExecParams.json' });
export const sha = value => createHash('sha256').update(value).digest('hex');
export const canonical = value => {
  if (Array.isArray(value)) return '[' + value.map(canonical).join(',') + ']';
  if (value !== null && typeof value === 'object') return '{' + Object.keys(value).sort().map(k => JSON.stringify(k) + ':' + canonical(value[k])).join(',') + '}';
  requireValue(value !== undefined && !(typeof value === 'number' && !Number.isFinite(value)), 'noncanonical_value');
  return JSON.stringify(value);
};

export class GeneratedProtocol {
  static async load(directory, pins) {
    const schemas = {};
    for (const [method, relative] of Object.entries(METHODS)) {
      const raw = await fs.readFile(path.join(directory, relative));
      requireValue(pins[relative] === sha(raw), 'protocol_source_hash_mismatch'); schemas[method] = JSON.parse(raw);
    }
    for (const [method, required] of Object.entries({ 'thread/start': ['permissions', 'historyMode', 'environments', 'modelProvider', 'allowProviderModelFallback', 'runtimeWorkspaceRoots'], 'turn/start': ['permissions', 'input', 'model', 'effort', 'environments'], 'thread/read': ['includeTurns'] })) requireValue(required.every(k => schemas[method].properties[k]), 'required_protocol_field_missing');
    for (const relative of ['v2/ThreadStartResponse.json','v2/ThreadResumeResponse.json']) {
      const raw = await fs.readFile(path.join(directory, relative));
      requireValue(pins[relative] === sha(raw) && JSON.parse(raw).definitions.ActivePermissionProfile.properties.id, 'permission_response_schema_mismatch');
    }
    const readOnly = schemas['turn/start'].definitions.SandboxPolicy.oneOf.find(x => x.title === 'ReadOnlySandboxPolicy');
    requireValue(readOnly?.properties.networkAccess && !readOnly.properties.readPolicy, 'sandbox_schema_changed_requires_review');
    return new GeneratedProtocol(schemas);
  }
  constructor(schemas) { this.schemas = schemas; }
  check(method, params) {
    const schema = this.schemas[method];
    requireValue(schema && params && typeof params === 'object' && !Array.isArray(params), 'unsupported_rpc_method');
    requireValue((schema.required ?? []).every(k => k in params) && Object.keys(params).every(k => k in schema.properties), 'rpc_schema_parameter_mismatch');
  }
}

// One outstanding client RPC at a time. Raw messages stay in this private transport.
export class PrivateRPC {
  constructor(child, protocol, timeoutMs = 20000) {
    this.child = child; this.protocol = protocol; this.timeoutMs = timeoutMs;
    this.sequence = 0; this.pending = null; this.events = []; this.waiter = null; this.failure = null; this.buffer = '';
    child.stdout.setEncoding('utf8');
    child.stdout.on('data', chunk => this.consume(chunk));
    child.stdout.on('end', () => this.fail('rpc_eof'));
    child.on('error', () => this.fail('rpc_child_error'));
  }
  fail(code) {
    if (this.failure) return; this.failure = new SiwcError(code);
    this.pending?.reject(this.failure); this.waiter?.reject(this.failure);
  }
  consume(chunk) {
    if (this.failure) return;
    this.buffer += chunk;
    if (Buffer.byteLength(this.buffer) > 2200000) return this.fail('rpc_message_too_large');
    for (;;) {
      const index = this.buffer.indexOf('\n'); if (index < 0) break;
      const line = this.buffer.slice(0, index); this.buffer = this.buffer.slice(index + 1);
      if (!line.trim()) continue;
      let msg; try { msg = JSON.parse(line); } catch { return this.fail('rpc_non_json'); }
      if (!msg || typeof msg !== 'object' || Array.isArray(msg)) return this.fail('rpc_malformed');
      if ('id' in msg && 'method' in msg) return this.fail('rpc_approval_or_external_decision_required');
      if ('id' in msg) {
        if (!this.pending || msg.id !== this.pending.id || ('error' in msg) || !msg.result || typeof msg.result !== 'object') return this.fail('rpc_rejected_or_response_mismatch');
        const pending = this.pending; this.pending = null; pending.resolve(msg.result);
      } else if (typeof msg.method === 'string') {
        if (this.waiter) { const waiter = this.waiter; this.waiter = null; waiter.resolve(msg); }
        else { this.events.push(msg); if (this.events.length > 10000) return this.fail('rpc_event_limit'); }
      } else return this.fail('rpc_malformed');
    }
  }
  send(message) { requireValue(!this.failure && !this.child.stdin.destroyed, 'rpc_not_ready'); this.child.stdin.write(JSON.stringify(message) + '\n'); }
  async rpc(method, params) {
    this.protocol.check(method, params); requireValue(!this.pending, 'concurrent_rpc_forbidden'); if (this.failure) throw this.failure;
    let timer;
    try { return await new Promise((resolve, reject) => {
      const id = ++this.sequence; this.pending = { id, resolve, reject };
      timer = setTimeout(() => this.fail('rpc_timeout_unknown_acceptance'), this.timeoutMs);
      try { this.send({ jsonrpc: '2.0', id, method, params }); } catch { this.fail('rpc_write_failed'); }
    }); } finally { clearTimeout(timer); }
  }
  notifyInitialized() { this.send({ jsonrpc: '2.0', method: 'initialized', params: {} }); }
  async event(timeoutMs) {
    if (this.failure) throw this.failure; if (this.events.length) return this.events.shift();
    requireValue(!this.waiter, 'concurrent_event_wait_forbidden'); let timer;
    try { return await new Promise((resolve, reject) => { this.waiter = { resolve, reject }; timer = setTimeout(() => this.fail('turn_timeout_unknown_acceptance'), timeoutMs); }); }
    finally { clearTimeout(timer); this.waiter = null; }
  }
}

function binding(record, chosen) {
  requireValue(record.model === chosen.model && record.reasoningEffort === chosen.reasoning_effort && record.modelProvider === 'openai_chatgpt_plan', 'configured_model_effort_provider_mismatch');
}
function policy(record) {
  requireValue(record.approvalPolicy === 'never' && record.approvalsReviewer === 'user' && record.activePermissionProfile?.id === PERMISSION_PROFILE && record.sandbox?.networkAccess === false, 'bounded_sandbox_readback_mismatch');
}
function output(items) {
  requireValue(Array.isArray(items), 'missing_output_items'); const agents = items.filter(x => x.type === 'agentMessage');
  const finals = agents.filter(x => x.phase === 'final_answer'); const selected = finals.length ? finals : agents.filter(x => x.phase == null);
  requireValue(selected.length > 0 && selected.every(x => typeof x.text === 'string'), 'actual_final_output_missing');
  const text = selected.map(x => x.text).join('\n'); requireValue(text.trim() && Buffer.byteLength(text) <= 1048576, 'invalid_output_size'); return text;
}

export async function actualPhase({ rpc, journal, phase, chosen, developer, prompt, workspace, outputSchema, gate, timeoutMs = 120000 }) {
  await gate(chosen); requireValue(timeoutMs > 0 && timeoutMs <= 300000, 'invalid_turn_timeout');
  const bounded = developer + '\nExecuție finită: nu folosi instrumente, shell, fișiere private, rețea, conectori sau delegare. Returnează numai rezultatul cerut, fără raționament privat. Nu modifica nimic.';
  await journal.phase(phase, { state: 'thread_start_intent', chosen, prompt_sha256: sha(prompt), developer_sha256: sha(bounded) });
  const start = await rpc.rpc('thread/start', { model: chosen.model, modelProvider: 'openai_chatgpt_plan', allowProviderModelFallback: false, cwd: workspace, runtimeWorkspaceRoots: [workspace], environments: [], dynamicTools: [], selectedCapabilityRoots: [], developerInstructions: bounded, config: { model_reasoning_effort: chosen.reasoning_effort }, approvalPolicy: 'never', approvalsReviewer: 'user', permissions: PERMISSION_PROFILE, historyMode: 'legacy', ephemeral: false, serviceTier: 'default' });
  const threadId = start.thread?.id; requireValue(typeof threadId === 'string' && threadId, 'thread_id_missing');
  await journal.phase(phase, { state: 'thread_started', thread_id: threadId }); binding(start, chosen); policy(start);
  const params = { threadId, model: chosen.model, effort: chosen.reasoning_effort, approvalPolicy: 'never', approvalsReviewer: 'user', serviceTierForTurn: 'default', environments: [], runtimeWorkspaceRoots: [workspace], permissions: PERMISSION_PROFILE, input: [{ type: 'text', text: prompt, text_elements: [] }], ...(outputSchema ? { outputSchema } : {}) };
  await gate(chosen); await journal.turnIntent(phase, params); // fsync before any possible acceptance
  const started = await rpc.rpc('turn/start', params), turnId = started.turn?.id;
  requireValue(typeof turnId === 'string' && turnId, 'turn_id_missing'); await journal.phase(phase, { state: 'turn_started', turn_id: turnId });
  const deadline = Date.now() + timeoutMs; const items = []; let completed;
  while (Date.now() < deadline) {
    const e = await rpc.event(deadline - Date.now()); const p = e.params ?? {};
    if (p.threadId !== threadId) continue;
    if (e.method === 'item/completed' && p.turnId === turnId) {
      requireValue(p.item?.type === 'agentMessage' || p.item?.type === 'reasoning', 'unexpected_tool_execution_requires_reconciliation');
      if (p.item?.type === 'agentMessage') items.push(p.item);
    }
    if (e.method === 'turn/completed' && p.turn?.id === turnId) { completed = p.turn; break; }
  }
  requireValue(completed?.status === 'completed', 'turn_not_completed'); const eventOutput = output(completed.items?.length ? completed.items : items);
  const resumed = await rpc.rpc('thread/resume', { threadId, excludeTurns: true }); binding(resumed, chosen); policy(resumed);
  const read = (await rpc.rpc('thread/read', { threadId, includeTurns: true })).thread;
  requireValue(read?.id === threadId, 'thread_readback_identity_mismatch'); binding(read, chosen);
  const turns = read.turns.filter(t => t.id === turnId); requireValue(turns.length === 1 && turns[0].status === 'completed', 'completed_turn_readback_missing');
  const actual = output(turns[0].items); requireValue(actual === eventOutput, 'event_readback_output_mismatch');
  const proof = { state: 'readback_complete', prompt_sha256: sha(prompt), output: actual, output_sha256: sha(actual), thread_id: threadId, turn_id: turnId, configured_model: chosen.model, configured_effort: chosen.reasoning_effort, configured_binding_source: 'thread/start + thread/resume + thread/read', access_evidence: 'completed_for_this_request_only', per_turn_model_attestation: false, monetary_cost: null };
  await journal.phase(phase, proof); return proof;
}
