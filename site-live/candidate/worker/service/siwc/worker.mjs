import { spawn } from 'node:child_process';
import { promises as fs } from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createPublicKey, verify } from 'node:crypto';
import { requireValue, SiwcError } from './oauth.mjs';
import { readPrivate, writePrivate, Vault, assertPrivateDirectory } from './crypto-store.mjs';
import { withProviderSession, validateReady } from './provider.mjs';
import { canonical, sha, PrivateRPC, GeneratedProtocol, actualPhase } from './private-rpc.mjs';
import { permissionConfiguration, assertEmptyWorkspace } from './permissions.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ID = /^[A-Za-z0-9][A-Za-z0-9_.-]{3,127}$/;
const RISK = ['security','production','privacy','payments','financial','medical','legal','destructive','safety'];
export const runtimeScope = runtime => { const { siwc_worker, siwc_magentic, ...scope } = runtime; return sha(canonical(scope)); };
export const grantFingerprint = record => sha(canonical({ issuer: record.issuer, subject: record.subject, client_id: record.client_id, ext_agent_host_id: record.ext_agent_host_id }));

export function signedPayload(signed, publicKey) {
  const key = createPublicKey(publicKey);
  requireValue(key.asymmetricKeyType === 'ed25519' && signed && typeof signed.signature === 'string' && verify(null, Buffer.from(canonical(signed.payload)), key, Buffer.from(signed.signature, 'base64url')), 'signed_authority_required');
  return signed.payload;
}
// These local records are read through readPrivate in production. A separate
// signing authority is optional, not an additional human approval requirement.
export function operatorPayload(document, publicKey) {
  if (document && Object.hasOwn(document, 'signature')) return signedPayload(document, publicKey);
  const payload = document?.payload ?? document;
  requireValue(payload && typeof payload === 'object' && !Array.isArray(payload), 'operator_record_required');
  return payload;
}
export function validateActivation({ runtime, authorization, entitlement, authorityKey, record, now = Date.now() / 1000, synthetic = false, allowExpiring = false }) {
  const a = operatorPayload(authorization, authorityKey), e = operatorPayload(entitlement, authorityKey);
  const magentic = a.mode === 'magentic', configured = magentic ? runtime.siwc_magentic : runtime.siwc_worker;
  requireValue(configured?.enabled === true && runtime.adapter === 'codex-app-server' && runtime.execution_surface === 'codex' && runtime.verification_evidence, 'siwc_worker_disabled');
  validateReady(record, now * 1000, { allowExpiring });
  requireValue(a.kind === (synthetic ? 'synthetic_fixture' : 'operator_bounded_siwc_job') && e.kind === (synthetic ? 'synthetic_fixture' : 'siwc_account_readiness'), 'synthetic_evidence_forbidden_in_production');
  // Three is the implementation bound, not a quoted numeric user instruction.
  requireValue(ID.test(a.task_id) && typeof a.input_sha256 === 'string' && /^[a-f0-9]{64}$/.test(a.input_sha256) && a.runtime_scope_sha256 === runtimeScope(runtime) && a.grant_fingerprint === grantFingerprint(record) && (magentic ? Number.isInteger(a.max_turns) && a.max_turns > 0 && a.max_turns <= 128 && /^[a-f0-9]{64}$/.test(a.framework_config_sha256) : a.max_turns === 3) && a.allowance_authorized === true && a.billing_mode === 'included' && a.read_only === true && a.network_access === false && a.no_new_spend === true && a.new_task_only === true && a.expires_at > now && a.expires_at <= now + 3600, 'bounded_operator_job_required');
  requireValue(e.grant_fingerprint === a.grant_fingerprint && e.runtime_scope_sha256 === a.runtime_scope_sha256 && e.expires_at > now && e.credential_isolation_verified === true && typeof e.credential_isolation_evidence_ref === 'string' && e.credential_isolation_evidence_ref.length > 0, 'account_binding_and_isolation_required');
  const allowance = e.account_allowance;
  requireValue(allowance?.available === true && allowance.billing_mode === 'included' && Number.isFinite(allowance.observed_at) && allowance.observed_at > 0 && allowance.observed_at <= now && allowance.expires_at > now && allowance.expires_at <= e.expires_at && typeof allowance.source_ref === 'string' && allowance.source_ref.length > 0, 'fresh_account_allowance_required');
  if(magentic&&configured.mode==='owner_gateway') {
    requireValue(a.policy_sha256===sha(canonical(configured))&&configured.dedicated_owner_gateway_client===true&&configured.grant_fingerprint===a.grant_fingerprint&&configured.max_turns===a.max_turns&&configured.expires_at===a.expires_at&&configured.gateway_client_token_sha256===configured.frontend_receipt_client_token_sha256,'server_owner_gateway_policy_mismatch');
  } else requireValue(configured.authorization_sha256 === sha(canonical(a)) && configured.task_id === a.task_id && configured.input_sha256 === a.input_sha256 && configured.max_turns === a.max_turns && configured.expires_at === a.expires_at && (!magentic || configured.framework_config_sha256 === a.framework_config_sha256), 'server_authorization_binding_mismatch');
  return { authorization: a, gate(chosen) {
    requireValue(Date.now() / 1000 < a.expires_at && Date.now() / 1000 < e.expires_at && Date.now() / 1000 < allowance.expires_at, 'authorization_expired'); validateReady(record);
    const listed = runtime.manifest.models.find(m => m.id === chosen.model);
    // Catalog compatibility permits the first bounded attempt. Only that
    // request's terminal completed event/readback can establish access.
    requireValue(listed?.enabled === true && listed.verified === true && listed.native_spawn_supported === true && listed.billing_mode === 'included' && listed.surface === 'codex' && listed.reasoning_levels.includes(chosen.reasoning_effort), 'chosen_model_configuration_missing');
  } };
}

export class HttpWorker {
  constructor(origin, token, fetcher = fetch) {
    const u = new URL(origin);
    requireValue(u.protocol === 'http:' && u.hostname === '127.0.0.1' && u.port && u.pathname === '/' && !u.search && !u.hash && !u.username && typeof token === 'string' && token.length >= 32, 'direct_loopback_worker_required');
    this.origin = u.origin; this.token = token; this.fetcher = fetcher;
  }
  async call(endpoint, body) {
    requireValue(/^\/v1\/worker\/[a-z/-]+$/.test(endpoint), 'non_worker_endpoint_forbidden');
    let response;
    try { response = await this.fetcher(this.origin + endpoint, { method: body === undefined ? 'GET' : 'POST', redirect: 'error', signal: AbortSignal.timeout(20000), headers: { Authorization: `Bearer ${this.token}`, 'Content-Type': 'application/json' }, ...(body === undefined ? {} : { body: JSON.stringify(body) }) }); } catch { throw new SiwcError('worker_http_uncertain_no_replay'); }
    requireValue(response.ok, 'worker_http_rejected_' + response.status);
    const reader = response.body.getReader(); let size = 0; const chunks = [];
    try { for (;;) { const { done, value } = await reader.read(); if (done) break; size += value.length; requireValue(size <= 2200000, 'worker_response_too_large'); chunks.push(value); } } finally { await reader.cancel(); }
    return JSON.parse(Buffer.concat(chunks));
  }
}

export class OriginalController {
  constructor(python) { requireValue(path.isAbsolute(python), 'absolute_python_required'); this.python = python; }
  async call(message) {
    return new Promise((resolve, reject) => {
      const env = {}; for (const k of ['PATH','Path','SystemRoot','WINDIR','TEMP','TMP']) if (process.env[k]) env[k] = process.env[k];
      env.PYTHONDONTWRITEBYTECODE = '1'; env.PYTHONIOENCODING = 'utf-8';
      const child = spawn(this.python, [path.join(HERE, 'controller_bridge.py')], { env, cwd: HERE, shell: false, windowsHide: true, stdio: ['pipe','pipe','pipe'] });
      const chunks = []; let size = 0, failure = false;
      const timer = setTimeout(() => { failure = true; child.kill(); reject(new SiwcError('controller_timeout')); }, 20000);
      child.stderr.resume(); child.stdout.on('data', b => { size += b.length; if (size > 2000000) { failure = true; child.kill(); reject(new SiwcError('controller_response_limit')); } else chunks.push(b); });
      child.on('error', () => { clearTimeout(timer); reject(new SiwcError('controller_spawn_failed')); });
      child.on('exit', code => { clearTimeout(timer); if (failure) return; if (code !== 0) return reject(new SiwcError('original_controller_rejected')); try { resolve(JSON.parse(Buffer.concat(chunks))); } catch { reject(new SiwcError('controller_invalid_json')); } });
      child.stdin.end(JSON.stringify(message));
    });
  }
}

export class HTTPJournal {
  constructor(api, taskId, runnerKey, reservation = null) { this.api = api; this.taskId = taskId; this.key = runnerKey; this.phases = {}; this.reservation = reservation; }
  async status() { return this.api.call('/v1/worker/runner/status', { task_id: this.taskId, runner_key: this.key }); }
  async phase(phase, update, options = {}) {
    const data = { ...(this.phases[phase] ?? {}), ...update }; this.phases[phase] = data;
    await this.api.call('/v1/worker/runner/checkpoint', { task_id: this.taskId, runner_key: this.key, phase, data, needs_reconcile: options.needsReconcile === true, finished: options.finished === true });
  }
  async turnIntent(phase, params) {
    const data = { ...this.phases[phase], state: 'turn_start_intent', turn_request_sha256: sha(canonical(params)) };
    const result = await this.api.call('/v1/worker/runner/turn-intent', { task_id: this.taskId, runner_key: this.key, phase, data });
    requireValue(Number.isInteger(result.index) && result.index >= 1 && result.index <= 3, 'durable_budget_intent_missing'); this.phases[phase] = { ...data, client_turn_request_index: result.index };
  }
}

export function bindAssessment(raw, role, text) {
  const a = JSON.parse(text);
  requireValue(a && canonical(Object.keys(a).sort()) === canonical(['task_id','source_agent_id','difficulty','reason','risk_flags'].sort()) && a.task_id === raw.task_id && a.source_agent_id === role.source_agent_id && Number.isInteger(a.difficulty) && a.difficulty >= 1 && a.difficulty <= 4 && typeof a.reason === 'string' && a.reason.trim() && Array.isArray(a.risk_flags) && a.risk_flags.every(x => RISK.includes(x)), 'canonical_five_field_assessment_required');
  return { ...a, task_input: raw.task };
}
const schema = properties => ({ type: 'object', properties, required: Object.keys(properties), additionalProperties: false });

export async function runCycle({ api, controller, rpc, journal, reservation, runtime, gate, workerId }) {
  const raw = reservation.payload.request; requireValue(reservation.state === 'running_kelion' && reservation.input_hash === sha(canonical(raw)) && !('role' in raw) && reservation.decision === null && reservation.output === null, 'new_owned_raw_task_required');
  let phase = 'bootstrap';
  try {
    const { registry } = await controller.call({ action: 'registry' }); const roles = registry.roles;
    const bootstrap = async task => { const d = await controller.call({ action: 'bootstrap', task, manifest: runtime.manifest }); return { model: d.host_model.id, reasoning_effort: d.host_model.reasoning }; };
    const selectionSchema = schema({ role: { type: 'string', enum: roles.map(r => r.role) }, reason: { type: 'string', minLength: 1 }, logic_validation_required: { type: 'boolean' } });
    phase = 'kelion_selection';
    const selected = await actualPhase({ rpc, journal, gate, phase, chosen: await bootstrap('Clasifica cererea într-un profil Kelion potrivit'), workspace: runtime.workspace, developer: 'Ești Kelion, selector central. Alege un profil canonic. Nu executa cererea. Returnează numai JSON conform schemei.', prompt: canonical({ task_id: raw.task_id, task: raw.task, profiles: roles.map(({ role, description, scope, guard, requires_logic_validation }) => ({ role, description: description ?? null, scope: scope ?? null, guard: guard ?? null, requires_logic_validation: requires_logic_validation ?? false })) }), outputSchema: selectionSchema });
    const selection = JSON.parse(selected.output);
    requireValue(canonical(Object.keys(selection).sort()) === canonical(['role','reason','logic_validation_required'].sort()) && typeof selection.reason === 'string' && selection.reason.trim() && typeof selection.logic_validation_required === 'boolean', 'invalid_kelion_selection');
    const role = roles.find(r => r.role === selection.role); requireValue(role && (!role.requires_logic_validation || selection.logic_validation_required === true), 'canonical_role_required');
    phase = 'dots_assessment';
    const assessed = await actualPhase({ rpc, journal, gate, phase, chosen: await bootstrap('Clasifica dificultatea cererii pentru profilul DOTS ales'), workspace: runtime.workspace, developer: role.developer_instructions, prompt: canonical({ phase: 'assessment', task_id: raw.task_id, source_agent_id: role.source_agent_id, task_input: raw.task }), outputSchema: schema({ task_id: { type: 'string', const: raw.task_id }, source_agent_id: { type: 'string', const: role.source_agent_id }, difficulty: { type: 'integer', minimum: 1, maximum: 4 }, reason: { type: 'string', minLength: 1 }, risk_flags: { type: 'array', items: { type: 'string', enum: RISK } } }) });
    const assessment = bindAssessment(raw, role, assessed.output);
    await journal.phase(phase, { assessment_parent_binding: { task_input_sha256: sha(raw.task), binding: 'immutable_parent_input_not_model_echo', historical_output_repaired: false } });
    const request = { task_id: raw.task_id, task: raw.task, role: role.role, surface: 'codex', logic_validation_required: selection.logic_validation_required };
    const plan = await controller.call({ action: 'plan', request, assessment, manifest: runtime.manifest });
    requireValue(plan.status === 'native_spawn_prepared' && plan.requires_action_approval !== true, 'original_controller_action_approval_or_plan_blocked');
    const prepared = await api.call('/v1/worker/runner/prepare', { task_id: raw.task_id, runner_key: journal.key, role: role.role, assessment, logic_validation_required: selection.logic_validation_required });
    requireValue(prepared.state === 'queued' && canonical(prepared.decision.spawn_request) === canonical(plan.spawn_request), 'server_original_controller_plan_mismatch');
    const claim = (await api.call('/v1/worker/runner/claim', { task_id: raw.task_id, runner_key: journal.key, worker_id: workerId })).claim;
    requireValue(claim?.task_id === raw.task_id && claim.input_hash === reservation.input_hash && claim.runtime_id === runtime.runtime_id && claim.decision.runtime_binding.runtime_sha256 === sha(canonical(runtime)), 'exact_task_lease_required');
    const spawnRequest = claim.decision.spawn_request; phase = 'dots_work';
    // Lease secret is persisted only in the authenticated private journal.
    await journal.phase(phase, { lease_token: claim.lease_token });
    const work = await actualPhase({ rpc, journal, gate, phase, chosen: { model: spawnRequest.model, reasoning_effort: spawnRequest.reasoning_effort }, workspace: runtime.workspace, developer: role.developer_instructions, prompt: spawnRequest.message });
    const receipt = { adapter: 'codex-app-server', runtime_id: runtime.runtime_id, native_agent_id: work.thread_id, turn_id: work.turn_id, model: spawnRequest.model, reasoning_effort: spawnRequest.reasoning_effort, status: 'completed', readback_output_sha256: work.output_sha256 };
    const result = await api.call('/v1/worker/complete', { task_id: raw.task_id, lease_token: claim.lease_token, output: work.output, receipt });
    requireValue(result.state === 'result_received' && result.output === work.output && result.output_hash === work.output_sha256, 'api_result_readback_mismatch');
    await journal.phase('finished', { state: 'completed', output_sha256: work.output_sha256, actual_monetary_cost: null, model_evidence: 'configured_binding_readback_not_per_turn_telemetry' }, { finished: true });
    const stored = await journal.status(); requireValue(stored.state === 'completed' && stored.journal.client_turn_requests === 3, 'final_journal_readback_mismatch');
    return { task_id: raw.task_id, status: 'result_received', output_sha256: work.output_sha256, client_turn_requests: 3, monetary_cost: null, per_turn_model_attestation: false };
  } catch (e) {
    try { await journal.phase(phase, { state: 'needs_reconcile', failure: e instanceof SiwcError ? e.code : 'worker_cycle_failed' }, { needsReconcile: true }); } catch {}
    throw new SiwcError(e instanceof SiwcError ? e.code : 'worker_cycle_failed_requires_reconciliation');
  }
}

export async function workerOnce(settings, internal = {}) {
  // Public disabled config is usable for an offline preflight and cannot launch a child.
  requireValue(settings.enabled === true, 'siwc_worker_disabled');
  const config = internal.config ?? JSON.parse(await readPrivate(settings.private_config));
  const runtime = config.runtime; requireValue(path.isAbsolute(runtime.workspace) && ID.test(config.worker_id), 'worker_configuration_invalid');
  await assertEmptyWorkspace(runtime.workspace);
  let protectedPaths = [settings.private_config, config.vault_root, config.vault_key_file, config.worker_token_file, config.operator_state_root, config.codex_home, config.authorization_file, config.readiness_file ?? config.entitlement_file, config.authority_public_key_file, config.framework_run_directory, config.framework_artifact_directory, config.framework_config_file, config.session_state_root, config.session_jobs_root].filter(Boolean);
  if(config.private_root) {
    await assertPrivateDirectory(config.private_root);
    const within=(root,p)=>{const rel=path.relative(root,p);return !rel.startsWith('..')&&!path.isAbsolute(rel);};
    requireValue(protectedPaths.every(p=>within(config.private_root,p)||(process.env.CREDENTIALS_DIRECTORY&&within(process.env.CREDENTIALS_DIRECTORY,p))), 'all_worker_private_paths_inside_private_root_or_systemd_credentials_required');
    protectedPaths=[config.private_root];
  }
  if(process.env.CREDENTIALS_DIRECTORY)protectedPaths.push(process.env.CREDENTIALS_DIRECTORY);
  const permissions = permissionConfiguration({ workspace: runtime.workspace, protectedPaths, codexExecutable: config.codex_executable });
  requireValue(runtime.permission_profile_sha256 === sha(canonical(permissions)), 'permission_configuration_binding_mismatch');
  const shippedPins = JSON.parse(await fs.readFile(path.join(HERE, 'protocol-pins.json'), 'utf8'));
  requireValue(canonical(config.protocol_sha256) === canonical(shippedPins) && canonical(runtime.protocol_sha256) === canonical(shippedPins), 'pinned_protocol_configuration_required');
  requireValue(path.isAbsolute(config.codex_executable) && /^[a-f0-9]{64}$/.test(runtime.executable_sha256) && sha(await fs.readFile(config.codex_executable)) === runtime.executable_sha256, 'verified_executable_sha256_required');
  const workerToken = (await readPrivate(config.worker_token_file)).toString('utf8').trim();
  const vaultKey = await readPrivate(config.vault_key_file), vault = new Vault(config.vault_root, vaultKey); vaultKey.fill(0);
  const api = new HttpWorker(config.api_origin, workerToken), controller = new OriginalController(config.python_executable);
  await assertPrivateDirectory(config.operator_state_root);
  const marker = path.join(config.operator_state_root, 'once-reservation.json');
  try { await fs.lstat(marker); throw new SiwcError('previous_once_intent_requires_reconciliation'); } catch (e) { if (e.code !== 'ENOENT') throw e; }
  const authorizationDocument = JSON.parse(await readPrivate(config.authorization_file)), readinessDocument = JSON.parse(await readPrivate(config.readiness_file ?? config.entitlement_file));
  const authorityKey = config.authority_public_key_file ? (await readPrivate(config.authority_public_key_file)).toString('utf8') : undefined;
  const authorizationPayload = operatorPayload(authorizationDocument, authorityKey);
  const isMagentic = authorizationPayload.mode === 'magentic';
  let magenticDriver, framework, frameworkConfig;
  if (isMagentic) {
    requireValue(process.platform === 'linux', 'original_framework_requires_linux_fcntl');
    magenticDriver = await import('./magentic-driver.mjs');
    const { FrameworkCLI } = await import('./framework-cli.mjs');
    await assertPrivateDirectory(config.framework_run_directory); await assertPrivateDirectory(config.framework_artifact_directory);
    requireValue((await fs.readdir(config.framework_run_directory)).length === 0, 'existing_framework_run_requires_reconciliation');
    frameworkConfig = JSON.parse(await readPrivate(config.framework_config_file));
    framework = new FrameworkCLI({ python: config.framework_python, sourceRoot: config.framework_source_root, runDirectory: config.framework_run_directory, artifactDirectory: config.framework_artifact_directory });
  }
  const protocol = await GeneratedProtocol.load(config.protocol_directory, config.protocol_sha256);
  let result, journal;
  try {
    await withProviderSession({ vault, executable: config.codex_executable, codexHome: config.codex_home, permissions, adapter: {
      async reconcileBeforeResume() {
        const state = await vault.read(); validateActivation({ runtime, authorization: authorizationDocument, entitlement: readinessDocument, authorityKey, record: state.record, allowExpiring: true });
        // Existing durable marker is never removed automatically or ignored.
        const mark = await fs.open(marker, 'wx', 0o600);
        try { await mark.writeFile(JSON.stringify({ task_id: authorizationPayload.task_id, state: 'reserve_intent' })); await mark.sync(); } finally { await mark.close(); }
        const a = authorizationPayload;
        const reserved = internal.admission ? {reservation:internal.admission.reservation} : await api.call(isMagentic ? '/v1/worker/magentic/reserve' : '/v1/worker/runner/reserve', { worker_id: config.worker_id, task_id: a.task_id, authorization: { task_id: a.task_id, input_sha256: a.input_sha256, runtime_sha256: sha(canonical(runtime)), authorization_sha256: sha(canonical(a)), max_turns: a.max_turns, expires_at: a.expires_at, ...(isMagentic ? { framework_config_sha256: a.framework_config_sha256 } : {}) } });
        requireValue(reserved.reservation?.task_id === a.task_id && reserved.reservation.input_hash === a.input_sha256, 'raw_task_reservation_missing');
        await writePrivate(marker, JSON.stringify({ task_id: a.task_id, runner_key: reserved.reservation.runner_key, state: 'reserved' }));
        journal = isMagentic ? new magenticDriver.MagenticHTTPJournal(api, a.task_id, reserved.reservation.runner_key, config.worker_id) : new HTTPJournal(api, a.task_id, reserved.reservation.runner_key, reserved.reservation);
        journal.reservation = reserved.reservation;
      },
      async usePrivateTransport(child, initialize) {
        const state = await vault.read(); const activation = validateActivation({ runtime, authorization: authorizationDocument, entitlement: readinessDocument, authorityKey, record: state.record });
        const rpc = new PrivateRPC(child, protocol); await rpc.rpc(initialize.method, initialize.params); rpc.notifyInitialized();
        result = isMagentic ? await magenticDriver.runMagenticCycle({ api, controller, rpc, journal, reservation: journal.reservation, runtime, gate: activation.gate, authorization: activation.authorization, framework, frameworkConfig, artifactDirectory: config.framework_artifact_directory, bindAssessment }) : await runCycle({ api, controller, rpc, journal, reservation: journal.reservation, runtime, gate: activation.gate, workerId: config.worker_id });
        await writePrivate(marker, JSON.stringify({ task_id: result.task_id, state: 'completed', output_sha256: result.output_sha256 }));
        return { initializeAcknowledged: true, initializedSent: true, reconciled: true, activeTurn: false };
      }
    } });
    return result;
  } catch (e) {
    if (journal) { try { if (isMagentic) await journal.call('fail',{reason:'worker_session_failed'}); else await journal.phase('bootstrap', { state: 'needs_reconcile', failure: 'worker_session_failed' }, { needsReconcile: true }); } catch {} }
    throw e;
  } finally { vault.close(); }
}
if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  (async () => { requireValue(process.argv.length === 4 && ['--once','--poll'].includes(process.argv[2]), 'usage_worker_--once_or_--poll_SETTINGS_JSON'); const settings = JSON.parse(await fs.readFile(process.argv[3], 'utf8')); if(process.argv[2]==='--poll'){const {workerPoll}=await import('./owner-poll.mjs');return workerPoll(settings);}return workerOnce(settings); })()
    .then(result => console.log(JSON.stringify(result))).catch(e => { console.error(JSON.stringify({ status: 'stopped', code: e instanceof SiwcError ? e.code : 'worker_failed', live_success_claimed: false })); process.exitCode = 1; });
}
