import { spawn } from 'node:child_process';
import path from 'node:path';
import { APP_NAME, ISSUER, RESOURCE, SCOPES, requireValue, issuedClientOK, tokenRequest, credentialsFromResponse, validateIdToken, loadJWKS, SiwcError } from './oauth.mjs';
import { assertPrivateDirectory } from './crypto-store.mjs';
import { permissionArgs } from './permissions.mjs';

export const PROVIDER = Object.freeze({ name: 'ChatGPT plan', base_url: RESOURCE, env_key: 'ACCESS_TOKEN', wire_api: 'responses', requires_openai_auth: false, supports_websockets: false });
// Pinned app-server 0.162.0-alpha.17.2: thread/start.historyMode requires this
// negotiation. The adapter must await a successful initialize acknowledgement.
export const INITIALIZE = Object.freeze({ method: 'initialize', params: { clientInfo: { name: APP_NAME, title: APP_NAME, version: '0.1.0' }, capabilities: { experimentalApi: true } } });
export function providerArgs(permissions) {
  return ['app-server', '--listen', 'stdio://', '--disable', 'multi_agent', '--disable', 'multi_agent_v2', '--disable', 'multi_agent_v2_dynamic_tools',
    '--disable', 'shell_tool', '--disable', 'unified_exec', '--disable', 'apps', '--disable', 'plugins', '--disable', 'hooks', '--disable', 'computer_use', '--disable', 'browser_use', '--disable', 'browser_use_external', '--disable', 'browser_use_full_cdp_access', '--disable', 'image_generation', '--disable', 'view_image', '--disable', 'code_mode_host', '--disable', 'skill_search', '--disable', 'sleep_tool', '--disable', 'workspace_dependencies',
    '-c', 'shell_environment_policy.inherit="core"', '-c', 'shell_environment_policy.ignore_default_excludes=false', '-c', 'shell_environment_policy.set={}',
    '-c', 'shell_environment_policy.filters={"ACCESS_TOKEN"="exclude","*TOKEN*"="exclude","*KEY*"="exclude","*SECRET*"="exclude","KELION_*"="exclude"}',
    '-c', 'web_search="disabled"', ...(permissions ? permissionArgs(permissions) : []), '-c', 'model_provider="openai_chatgpt_plan"', ...Object.entries(PROVIDER).flatMap(([k, v]) => ['-c', `model_providers.openai_chatgpt_plan.${k}=${JSON.stringify(v)}`])];
}
export function validateReady(record, now = Date.now(), { allowExpiring = false } = {}) {
  requireValue(record?.schema === 1 && record.status === 'ready' && record.issuer === ISSUER && issuedClientOK(record.client_id) && typeof record.subject === 'string' && record.subject.length > 0, 'credentials_not_ready');
  requireValue(Array.isArray(record.scopes) && ['openid', 'offline_access', 'resource.invoke', 'chatgpt.tokens.use.direct'].every(s => record.scopes.includes(s)), 'chatgpt_plan_permission_missing');
  requireValue(typeof record.access_token === 'string' && record.access_token.length > 0 && Number.isFinite(record.expires_at) && (allowExpiring || record.expires_at > now + 60000), 'access_token_expired_or_expiring');
}
export function childEnvironment(record, { codexHome, parentEnv = process.env }) {
  validateReady(record); requireValue(path.isAbsolute(codexHome), 'isolated_codex_home_required');
  const result = {};
  // Never inherit OPENAI_API_KEY, desktop CODEX_HOME, NODE_OPTIONS or arbitrary secrets.
  for (const k of ['PATH', 'Path', 'SystemRoot', 'WINDIR', 'TEMP', 'TMP', 'LANG', 'LC_ALL']) if (typeof parentEnv[k] === 'string') result[k] = parentEnv[k];
  return { ...result, HOME: codexHome, USERPROFILE: codexHome, CODEX_HOME: codexHome, ACCESS_TOKEN: record.access_token };
}

export async function spawnProvider({ executable, codexHome, record, permissions, spawnFn = spawn }) {
  requireValue(path.isAbsolute(executable), 'absolute_codex_executable_required');
  await assertPrivateDirectory(codexHome);
  const env = childEnvironment(record, { codexHome });
  try {
    const child = spawnFn(executable, providerArgs(permissions), { cwd: codexHome, env, shell: false, windowsHide: true, stdio: ['pipe', 'pipe', 'pipe'] });
    // Caller owns JSON-RPC stdout as a private transport, never forwards it to logs.
    child.stderr?.resume();
    return child;
  } finally { delete env.ACCESS_TOKEN; }
}

async function stopChild(child) {
  if (!child || child.exitCode !== null) return;
  await new Promise((resolve, reject) => {
    const done = () => { clearTimeout(soft); clearTimeout(hard); resolve(); };
    child.once('exit', done);
    const soft = setTimeout(() => child.kill('SIGKILL'), 3000);
    const hard = setTimeout(() => { child.removeListener('exit', done); reject(new SiwcError('child_exit_unconfirmed')); }, 6000);
    child.kill();
  });
}

// Adapter owns the existing durable task journal. No planner and no turn replay here.
// start/refresh execute under one cross-process vault lock retained for child lifetime.
export async function withProviderSession({ vault, adapter, executable, codexHome, permissions, refresh = refreshRecord, spawnFn, spawnProviderFn = spawnProvider }) {
  return vault.lock(async () => {
    let state = await vault.read();
    requireValue(state?.phase === 'stopped' && state.record, 'restart_requires_reconciliation');
    state.phase = 'reconciling'; await vault.write(state);
    await adapter.reconcileBeforeResume(); // must throw for unknown turn acceptance
    if (state.record.expires_at <= Date.now() + 60000) {
      state.phase = 'refresh_pending'; await vault.write(state);
      try { state.record = await refresh(state.record); }
      catch (e) {
        const terminal = ['invalid_grant', 'invalid_refresh_token', 'token_expired', 'refresh_token_expired', 'refresh_token_invalidated', 'refresh_token_reused'];
        if (terminal.includes(e.code)) { delete state.record.access_token; delete state.record.refresh_token; delete state.record.id_token; state.record.status = 'reauthorization_required'; }
        state.phase = 'needs_reconcile'; await vault.write(state); throw new SiwcError('refresh_failed_closed');
      }
      state.phase = 'stopped'; await vault.write(state);
    }
    validateReady(state.record);
    state.phase = 'child_start_intent'; await vault.write(state);
    let child, deadline;
    try {
      child = await spawnProviderFn({ executable, codexHome, record: state.record, permissions, spawnFn });
      state.phase = 'running'; await vault.write(state);
      // Adapter initializes, waits for acknowledgement, emits initialized, resumes a
      // saved thread only after reconciliation; no turn/start is authorized by this API.
      const expiry = new Promise((_, reject) => { deadline = setTimeout(() => reject(new SiwcError('token_renewal_requires_restart')), Math.max(1, state.record.expires_at - Date.now() - 30000)); });
      const outcome = await Promise.race([adapter.usePrivateTransport(child, INITIALIZE), expiry]);
      requireValue(outcome?.initializeAcknowledged === true && outcome?.initializedSent === true, 'initialize_acknowledgement_required');
      requireValue(outcome?.reconciled === true && outcome?.activeTurn === false, 'adapter_reconciliation_required');
      state.phase = 'stopped';
    } catch { state.phase = 'needs_reconcile'; throw new SiwcError('provider_failed_closed'); }
    finally {
      clearTimeout(deadline);
      try { await stopChild(child); }
      catch { state.phase = 'needs_reconcile'; throw new SiwcError('child_exit_unconfirmed'); }
      finally { await vault.write(state); }
    }
  });
}

export async function refreshRecord(previous, { fetcher = fetch, jwksLoader = loadJWKS, now = Date.now() } = {}) {
  requireValue(previous.status === 'ready' && issuedClientOK(previous.client_id) && typeof previous.refresh_token === 'string', 'refresh_not_ready');
  // Official Accounts and sessions prescribes renewal near access-token expiry.
  // The token reference does not define earliest_refresh_at's units or format;
  // retain that metadata without guessing a timestamp or overriding this rule.
  requireValue(Number.isFinite(previous.expires_at) && previous.expires_at <= now + 60000, 'refresh_too_early');
  const t = await tokenRequest({ grant_type: 'refresh_token', client_id: previous.client_id, refresh_token: previous.refresh_token, resource: RESOURCE }, fetcher);
  // Refresh may omit scope and ID token. Preserve authenticated identity and prior
  // granted scope per OAuth; a returned ID token must bind the original identity.
  const identity = t.id_token ? validateIdToken(t.id_token, { jwks: await jwksLoader(fetcher), clientId: previous.client_id, nonce: previous.oidc_nonce, expectedSubject: previous.subject }) : { sub: previous.subject, email: previous.email };
  return credentialsFromResponse({ ...t, scope: t.scope ?? previous.scopes.join(' ') }, { identity, clientId: previous.client_id, hostId: previous.ext_agent_host_id, nonce: previous.oidc_nonce, previous });
}

export function responseContract({ model, input, instructions }) {
  requireValue(typeof model === 'string' && model.length > 0 && Array.isArray(input) && input.length > 0, 'invalid_responses_input');
  requireValue(input.every(item => item?.type === 'message' && ['user', 'assistant', 'developer'].includes(item.role) && typeof item.content === 'string'), 'unsupported_input_capability');
  return { model, input, ...(instructions ? { instructions } : {}), store: false, stream: true };
}
