import { PERMISSION_PROFILE, permissionConfiguration, permissionArgs } from './permissions.mjs';
import test from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { EventEmitter } from 'node:events';
import { PassThrough, Writable } from 'node:stream';
import { createInterface } from 'node:readline';
import { promises as fs } from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { fileURLToPath } from 'node:url';
import { generateKeyPairSync, sign, randomUUID } from 'node:crypto';
import { HttpWorker, OriginalController, HTTPJournal, runCycle, validateActivation, runtimeScope, grantFingerprint, workerOnce, bindAssessment } from './worker.mjs';
import { GeneratedProtocol, PrivateRPC, sha, canonical } from './private-rpc.mjs';
import { INITIALIZE, providerArgs } from './provider.mjs';
import { magenticReceipt, FRAMEWORK_COMMIT, verifyMagenticSources } from './magentic-receipt.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const PYTHON = process.env.SIWC_TEST_PYTHON ?? 'C:/Users/adria/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe';
const PROTOCOL = process.env.SIWC_TEST_PROTOCOL ?? path.resolve(HERE, '../private/appserver-protocol');
const pins = JSON.parse(await fs.readFile(path.join(HERE, 'protocol-pins.json'), 'utf8'));
const protocol = await GeneratedProtocol.load(PROTOCOL, pins);
const controller = new OriginalController(PYTHON);
const registry = (await controller.call({ action: 'registry' })).registry;
const role = registry.roles.find(x => x.role === 'programare');
const keypair = generateKeyPairSync('ed25519');
const authorityKey = keypair.publicKey.export({ type: 'spki', format: 'pem' });
const signed = payload => ({ payload, signature: sign(null, Buffer.from(canonical(payload)), keypair.privateKey).toString('base64url') });

function setup() {
  const raw = { task_id: 'SYNTHETIC-' + randomUUID(), task: 'List three words', origin: 'codex', input_mode: 'text' };
  const record = { schema: 1, status: 'ready', issuer: 'https://auth.openai.com', subject: 'SYNTHETIC-sub', client_id: 'oaiapp_SYNTHETIC', ext_agent_host_id: randomUUID(), access_token: 'SYNTHETIC-access-only', expires_at: Date.now() + 3600000, scopes: ['openid','offline_access','resource.invoke','chatgpt.tokens.use.direct'] };
  const runtime = { adapter: 'codex-app-server', runtime_id: 'SYNTHETIC-worker-runtime', execution_surface: 'codex', workspace: HERE, verification_evidence: 'SYNTHETIC ONLY: not real entitlement', manifest: { schema_version: 1, connectors: [], models: [{ id: 'fixture-economy', surface: 'codex', enabled: true, verified: true, billing_mode: 'included', cost_rank: 1, capability_tier: 1, reasoning_levels: ['low'], native_spawn_supported: true }, { id: 'fixture-critical', surface: 'codex', enabled: true, verified: true, billing_mode: 'included', cost_rank: 4, capability_tier: 4, reasoning_levels: ['low','medium','high'], native_spawn_supported: true }] } };
  const a = { kind: 'synthetic_fixture', task_id: raw.task_id, input_sha256: sha(canonical(raw)), runtime_scope_sha256: runtimeScope(runtime), grant_fingerprint: grantFingerprint(record), max_turns: 3, allowance_authorized: true, billing_mode: 'included', read_only: true, network_access: false, no_new_spend: true, new_task_only: true, expires_at: Math.floor(Date.now() / 1000) + 300 };
  runtime.siwc_worker = { enabled: true, task_id: a.task_id, input_sha256: a.input_sha256, authorization_sha256: sha(canonical(a)), max_turns: 3, expires_at: a.expires_at };
  const e = { kind: 'synthetic_fixture', grant_fingerprint: a.grant_fingerprint, runtime_scope_sha256: a.runtime_scope_sha256, expires_at: a.expires_at, credential_isolation_verified: true, credential_isolation_evidence_ref: 'SYNTHETIC fixture, not isolation proof', account_allowance: { available: true, billing_mode: 'included', observed_at: Math.floor(Date.now() / 1000), expires_at: a.expires_at, source_ref: 'SYNTHETIC current allowance observation' } };
  return { raw, record, runtime, authorization: signed(a), entitlement: signed(e), authorityKey };
}

async function server(fixture) {
  const fixtureEnv = { PYTHONDONTWRITEBYTECODE: '1', PYTHONIOENCODING: 'utf-8' }; for (const k of ['PATH','Path','SystemRoot','WINDIR','TEMP','TMP']) if (process.env[k]) fixtureEnv[k] = process.env[k];
  const child = spawn(PYTHON, [path.join(HERE, 'http-fixture.py')], { windowsHide: true, stdio: ['pipe','pipe','pipe'], env: fixtureEnv });
  const token = 'SYNTHETIC-worker-' + 'w'.repeat(32), clientToken = 'SYNTHETIC-client-' + 'c'.repeat(32);
  child.stderr.resume(); const lines = createInterface({ input: child.stdout });
  const info = new Promise((resolve, reject) => { const timer = setTimeout(() => { child.kill(); reject(new Error('fixture startup timeout')); }, 10000); lines.once('line', line => { clearTimeout(timer); resolve(JSON.parse(line)); }); child.once('error', reject); });
  child.stdin.write(JSON.stringify({ runtime: fixture.runtime, raw_tasks: [fixture.raw], worker_token: token, client_token: clientToken }) + '\n');
  const { port } = await info;
  return { api: new HttpWorker(`http://127.0.0.1:${port}`, token), stop: async () => { const closed = new Promise(resolve => child.once('exit', resolve)); child.stdin.end('\n'); await closed; lines.close(); } };
}

function syntheticAppServer(raw, journal, failure) {
  const child = new EventEmitter(); child.stdout = new PassThrough(); child.stderr = new PassThrough(); child.exitCode = 0;
  let count = 0; const threads = new Map(); const methods = [];
  const send = message => child.stdout.write(JSON.stringify(message) + '\n');
  const withPolicy = thread => ({ thread, model: thread.model, modelProvider: thread.modelProvider, reasoningEffort: thread.reasoningEffort, approvalPolicy: 'never', approvalsReviewer: 'user', activePermissionProfile: { id: PERMISSION_PROFILE }, sandbox: { type: 'readOnly', networkAccess: false } });
  let initializeAcknowledged = false, initialized = false;
  child.stdin = new Writable({ write(chunk, _encoding, callback) {
    (async () => {
      const message = JSON.parse(chunk.toString('utf8')); methods.push(message.method); const p = message.params;
      if (message.method === 'initialize') { assert.equal(p.capabilities.experimentalApi, true); initializeAcknowledged = true; send({ id: message.id, result: { userAgent: 'SYNTHETIC' } }); return; }
      if (message.method === 'initialized') { assert.equal(initializeAcknowledged, true); initialized = true; return; }
      assert.equal(initialized, true);
      if (message.method === 'thread/start') {
        assert.equal(p.permissions, PERMISSION_PROFILE); assert.equal('sandbox' in p, false);
        assert.deepEqual(p.environments, []); assert.deepEqual(p.dynamicTools, []); assert.equal(p.modelProvider, 'openai_chatgpt_plan');
        const thread = { id: 'SYNTHETIC-thread-' + (threads.size + 1), model: p.model, reasoningEffort: p.config.model_reasoning_effort, modelProvider: p.modelProvider, turns: [] }; threads.set(thread.id, thread); send({ id: message.id, result: withPolicy(thread) }); return;
      }
      if (message.method === 'turn/start') {
        assert.equal(p.permissions, PERMISSION_PROFILE); assert.equal('sandboxPolicy' in p, false);
        count++;
        const durable = await journal.status(); assert.equal(durable.journal.client_turn_requests, count); assert.equal(durable.journal.turn_request_intents[count - 1].turn_request_sha256, sha(canonical(p)));
        if (failure === 'approval') { send({ id: 'SYNTHETIC-approval', method: 'item/commandExecution/requestApproval', params: { threadId: p.threadId } }); return; }
        if (failure === 'timeout') return;
        const turnId = 'SYNTHETIC-turn-' + count;
        const text = count === 1 ? JSON.stringify({ role: role.role, reason: 'SYNTHETIC selector output', logic_validation_required: false }) : count === 2 ? JSON.stringify({ task_id: raw.task_id, source_agent_id: role.source_agent_id, difficulty: 1, reason: 'SYNTHETIC assessment output', risk_flags: failure === 'risk' ? ['security'] : [] }) : 'SYNTHETIC operational final output';
        const turn = { id: turnId, status: 'completed', items: [{ type: 'agentMessage', id: 'SYNTHETIC-item-' + count, phase: 'final_answer', text }] }; threads.get(p.threadId).turns.push(turn);
        send({ id: message.id, result: { turn: { id: turnId, status: 'inProgress' } } });
        send({ method: 'turn/completed', params: { threadId: p.threadId, turn } }); return;
      }
      if (message.method === 'thread/resume') { send({ id: message.id, result: withPolicy(threads.get(p.threadId)) }); return; }
      if (message.method === 'thread/read') {
        const thread = structuredClone(threads.get(p.threadId)); if (failure === 'readback' && count === 3) thread.turns[0].items[0].text = 'SYNTHETIC mismatch';
        send({ id: message.id, result: { thread } }); return;
      }
      throw new Error('unexpected synthetic method');
    })().then(() => callback()).catch(error => { callback(error); child.emit('error', error); });
  } });
  child.stdin.on('error', () => {});
  return { child, methods, count: () => count };
}

async function exercise(failure) {
  const fixture = setup(), remote = await server(fixture);
  try {
    const a = fixture.authorization.payload;
    const reserved = await remote.api.call('/v1/worker/runner/reserve', { worker_id: 'SYNTHETIC-worker-one', task_id: a.task_id, authorization: { task_id: a.task_id, input_sha256: a.input_sha256, runtime_sha256: sha(canonical(fixture.runtime)), authorization_sha256: sha(canonical(a)), max_turns: 3, expires_at: a.expires_at } });
    const reservation = reserved.reservation, journal = new HTTPJournal(remote.api, a.task_id, reservation.runner_key);
    const fake = syntheticAppServer(fixture.raw, journal, failure), rpc = new PrivateRPC(fake.child, protocol, failure === 'timeout' ? 80 : 1000);
    await rpc.rpc(INITIALIZE.method, INITIALIZE.params); rpc.notifyInitialized();
    const activation = validateActivation({ ...fixture, synthetic: true });
    const run = runCycle({ api: remote.api, controller, rpc, journal, reservation, runtime: fixture.runtime, gate: activation.gate, workerId: 'SYNTHETIC-worker-one' });
    if (!failure) { const result = await run; assert.equal(result.status, 'result_received'); assert.equal(result.client_turn_requests, 3); assert.equal(fake.count(), 3); assert.equal(result.per_turn_model_attestation, false); assert.equal(result.monetary_cost, null); }
    else { await assert.rejects(run); assert.equal((await journal.status()).state, 'needs_reconcile'); assert.equal(fake.count(), failure === 'risk' ? 2 : failure === 'readback' ? 3 : 1); }
    assert.equal(fake.methods.includes('account/read'), false); assert.equal(fake.methods.includes('model/list'), false);
    const retry = remote.api.call('/v1/worker/runner/reserve', { worker_id: 'SYNTHETIC-after-crash', task_id: a.task_id, authorization: { task_id: a.task_id, input_sha256: a.input_sha256, runtime_sha256: sha(canonical(fixture.runtime)), authorization_sha256: sha(canonical(a)), max_turns: 3, expires_at: a.expires_at } });
    if (failure) await assert.rejects(retry); else assert.equal((await retry).reservation, null);
  } finally { await remote.stop(); }
}

test('three-phase synthetic RPC plus original controller plus real HTTP/SQLite completes exact task', () => exercise());
test('actual event/readback mismatch seals journal after third intent and cannot replay', () => exercise('readback'));
test('server-initiated approval stops without an approval response or retry', () => exercise('approval'));
test('unknown RPC acceptance timeout seals first consumed intent', () => exercise('timeout'));
test('original Cost Guardian approval flag stops after actual synthetic assessment', () => exercise('risk'));
test('signed synthetic entitlement cannot activate production path', () => { assert.throws(() => validateActivation(setup()), /synthetic_evidence_forbidden/); });
test('production default disabled before reading private files or launching a process', async () => { await assert.rejects(workerOnce({ enabled: false }), /siwc_worker_disabled/); });
test('missing allowance, tampered signature, wrong input and expired authorization fail closed', () => {
  const f = setup(); const tampered = structuredClone(f.authorization); tampered.payload.max_turns = 4;
  assert.throws(() => validateActivation({ ...f, authorization: tampered, synthetic: true }), /signed_authority_required/);
  for (const change of [{ allowance_authorized: false }, { max_turns: 4 }, { expires_at: 0 }, { runtime_scope_sha256: 'x' }]) assert.throws(() => validateActivation({ ...f, authorization: signed({ ...f.authorization.payload, ...change }), synthetic: true }));
});
test('model catalog alone is insufficient and no credentials may enter shell tool env', () => {
  const f = setup(); const noAllowance = { ...f.entitlement.payload }; delete noAllowance.account_allowance; assert.throws(() => validateActivation({ ...f, entitlement: signed(noAllowance), synthetic: true }), /fresh_account_allowance/);
  const args = providerArgs().join(' '); assert.match(args, /shell_environment_policy.inherit="core"/); assert.match(args, /ACCESS_TOKEN"="exclude/); assert.match(args, /--disable multi_agent_v2_dynamic_tools/);
});
test('canonical assessment binds original input without model task echo', () => {
  const f = setup(); const actual = { task_id: f.raw.task_id, source_agent_id: role.source_agent_id, difficulty: 1, reason: 'SYNTHETIC', risk_flags: [] };
  assert.equal(bindAssessment(f.raw, role, JSON.stringify(actual)).task_input, f.raw.task);
  assert.throws(() => bindAssessment(f.raw, role, JSON.stringify({ ...actual, task_input: f.raw.task })));
});
test('Magentic receipt binds exact pending request while configured model is not hidden execution attestation', () => {
  const payload = { schema_version: 1, task_id: 'SYNTHETIC-magentic', mode: 'native_host', kind: 'manager_reasoning', role: 'kelion_manager', framework_commit: FRAMEWORK_COMMIT, config_sha256: sha('SYNTHETIC-config'), system_instructions: 'SYNTHETIC', messages: [{ role: 'user', text: 'SYNTHETIC', author_name: null }], host_requirements: { selected_by: 'Kelion' } };
  const id = sha(canonical(payload)), request = { request_id: id, input_sha256: id, dispatch_state: 'awaiting_native_host', ...payload };
  const proof = { state: 'readback_complete', prompt_sha256: id, output: 'SYNTHETIC-output', output_sha256: sha('SYNTHETIC-output'), thread_id: 'SYNTHETIC-thread', turn_id: 'SYNTHETIC-turn', configured_model: 'SYNTHETIC-model', configured_effort: 'low', configured_binding_source: 'thread/start + thread/resume + thread/read' };
  const authorization = { task_id: payload.task_id, no_new_spend: true, max_turns: 3, expires_at: Date.now() / 1000 + 300, authorized_request_ids: [id] };
  const converted = magenticReceipt({ request, proof, resultRef: 'SYNTHETIC-artifact', authorization });
  assert.equal(converted.receipt.native_surface, 'codex'); assert.equal(converted.receipt.actual_model_attested, false); assert.equal(converted.receipt.actual_effort_attested, false); assert.equal(converted.receipt.actual_monetary_cost, null); assert.equal(converted.framework_execution_claimed, false);
  assert.throws(() => magenticReceipt({ request, proof: { ...proof, prompt_sha256: sha('wrong') }, resultRef: 'SYNTHETIC', authorization }));
  assert.throws(() => magenticReceipt({ request, proof, resultRef: 'SYNTHETIC', authorization: { ...authorization, max_turns: 129 } }));
});
test('six recovered Magentic source hashes are checked without importing or simulating framework', async () => {
  const result = await verifyMagenticSources(path.resolve(HERE, '../../.runtime/magentic-recovered'));
  assert.equal(result.recovered_sources_verified, true); assert.equal(result.framework_installed_or_executed, false);
});

test('real synthetic subprocess receives exact original CLI argv and no provider credential', async () => {
  const { FrameworkCLI } = await import('./framework-cli.mjs');
  const dir=await fs.mkdtemp(path.join(os.tmpdir(),'siwc-cli-contract-'));
  try {
    const source=path.join(dir,'source'),module=path.join(source,'orchestration/magentic_candidate'),artifacts=path.join(dir,'artifacts');
    await fs.mkdir(module,{recursive:true});await fs.mkdir(artifacts);
    const frozen=path.resolve(HERE,'../../.runtime/magentic-recovered');
    for(const name of Object.keys(JSON.parse(await fs.readFile(path.join(HERE,'magentic-source-pins.json'),'utf8'))))await fs.copyFile(path.join(frozen,name),path.join(module,name));
    let count=0;
    const framework=new FrameworkCLI({python:PYTHON,sourceRoot:source,runDirectory:path.join(dir,'run'),artifactDirectory:artifacts,writeFn:(file,value)=>fs.writeFile(file,value),spawnFn:(exe,args,options)=>{
      count++;assert.equal(exe,PYTHON);assert.equal(options.shell,false);assert.equal(options.cwd,source);assert.equal(options.env.ACCESS_TOKEN,undefined);
      return spawn(exe,['-c','import json,sys,os; print(json.dumps({"argv":sys.argv[1:],"cwd":os.getcwd(),"synthetic":True}))',...args],options);
    }});
    assert.equal(count,0);
    const value={task_id:'SYNTHETIC-cli',objective:'SYNTHETIC'};
    const initialized=await framework.call('init',value);
    assert.deepEqual(initialized.argv.slice(0,7),['-m','orchestration.magentic_candidate.cli','--run-dir',path.join(dir,'run'),'--timeout','20','init']);
    assert.equal(initialized.argv[7],'--file');assert.equal(await fs.readFile(initialized.argv[8],'utf8'),canonical(value));
    const read=await framework.call('readback','a'.repeat(64));assert.deepEqual(read.argv.slice(-3),['readback','--request-id','a'.repeat(64)]);
    await fs.appendFile(path.join(module,'cli.py'),'# tampered fixture');
    await assert.rejects(framework.call('pending'),/magentic_recovered_source_changed/);assert.equal(count,2);
  } finally { await fs.rm(dir,{recursive:true,force:true}); }
});

test('first bounded request needs no completed-model history or separate signing authority', () => {
  const f = setup();
  const a = { ...f.authorization.payload, kind: 'operator_bounded_siwc_job' };
  const e = { ...f.entitlement.payload, kind: 'siwc_account_readiness' };
  f.runtime.siwc_worker.authorization_sha256 = sha(canonical(a));
  const activation = validateActivation({ ...f, authorization: a, entitlement: e, authorityKey: undefined });
  assert.equal(e.completed_model_readbacks, undefined);
  activation.gate({ model: 'fixture-economy', reasoning_effort: 'low' });
  activation.gate({ model: 'fixture-critical', reasoning_effort: 'high' });
  assert.throws(() => activation.gate({ model: 'unconfigured-model', reasoning_effort: 'high' }));
});
test('current account allowance and actual credential isolation remain necessary', () => {
  const f = setup();
  for (const change of [{ credential_isolation_verified: false }, { grant_fingerprint: sha('wrong-account') }, { account_allowance: { ...f.entitlement.payload.account_allowance, available: false } }, { account_allowance: { ...f.entitlement.payload.account_allowance, expires_at: 0 } }]) {
    assert.throws(() => validateActivation({ ...f, entitlement: signed({ ...f.entitlement.payload, ...change }), synthetic: true }));
  }
});

test('named permissions deny private paths and keep independent workspace read-only', () => {
 const root = path.resolve(HERE, 'synthetic-empty-workspace');
 const secret = path.resolve(HERE, 'synthetic-private');
 const p = permissionConfiguration({ workspace: root, protectedPaths: [secret], platform: 'linux' });
 const fs = p.permissions[PERMISSION_PROFILE].filesystem;
 assert.equal(fs[':root'], 'deny'); assert.equal(fs[':minimal'], 'read'); assert.equal(fs[secret], 'deny'); assert.equal(fs['/proc'], 'deny'); assert.equal(fs['/run/credentials'], 'deny');
 assert.deepEqual(fs[':workspace_roots'], { '.': 'read' }); assert.equal(p.permissions[PERMISSION_PROFILE].network.enabled, false);
 const args = permissionArgs(p).join(' '); assert.match(args, /default_permissions/); assert.doesNotMatch(args, /sandbox_mode|sandboxPolicy/);
 assert.throws(() => permissionConfiguration({ workspace: root, protectedPaths: [path.join(root, 'private')] }));
});


test('Magentic driver contract fixture consumes multiple request phases through real HTTP persistence', async () => {
  const { MagenticHTTPJournal, boundFrameworkConfig, runMagenticCycle } = await import('./magentic-driver.mjs');
  const f = setup();
  const frameworkConfig = { enabled: true, mode: 'native_host', task_id: f.raw.task_id, objective: f.raw.task, participants: [role.name], max_rounds: 2, max_resets: 1, max_stalls: 1, max_requests: 3 };
  const configHash = sha(canonical(boundFrameworkConfig(frameworkConfig, f.raw, registry)));
  const a = { ...f.authorization.payload, mode: 'magentic', max_turns: 4, framework_config_sha256: configHash };
  f.authorization = signed(a);
  f.runtime.siwc_magentic = { enabled: true, task_id: a.task_id, input_sha256: a.input_sha256, authorization_sha256: sha(canonical(a)), max_turns: a.max_turns, expires_at: a.expires_at, framework_config_sha256: configHash };
  const remote = await server(f);
  try {
    const { reservation } = await remote.api.call('/v1/worker/magentic/reserve', { task_id: a.task_id, worker_id: 'SYNTHETIC-magentic', authorization: { task_id: a.task_id, input_sha256: a.input_sha256, runtime_sha256: sha(canonical(f.runtime)), authorization_sha256: sha(canonical(a)), max_turns: 4, expires_at: a.expires_at, framework_config_sha256: configHash } });
    const journal = new MagenticHTTPJournal(remote.api, a.task_id, reservation.runner_key, 'SYNTHETIC-magentic');
    const fake = syntheticAppServer(f.raw, journal), rpc = new PrivateRPC(fake.child, protocol);
    await rpc.rpc(INITIALIZE.method, INITIALIZE.params); rpc.notifyInitialized();
    const requests = ['manager_reasoning','participant_execution','manager_reasoning'].map((kind,i) => {
      const payload = { schema_version: 1, task_id: a.task_id, mode: 'native_host', kind, role: kind === 'manager_reasoning' ? 'kelion_manager' : role.name, framework_commit: FRAMEWORK_COMMIT, config_sha256: configHash, system_instructions: 'SYNTHETIC framework request '+i, messages: [{role:'user',text:'SYNTHETIC request '+i,author_name:null}], host_requirements: {}, ...(kind === 'participant_execution' ? { native_profile: role } : {}) };
      const id = sha(canonical(payload)); return { ...payload, request_id: id, input_sha256: id, dispatch_state: 'awaiting_native_host' };
    });
    let position = 0, response, final; const seen=[];
    // Explicit contract fixture; this is NOT a framework execution proof.
    const framework = { async call(op,value) {
      seen.push(op);
      if (op === 'init') return {status:'initialized',synthetic:true};
      if (op === 'advance') {
        if(position < requests.length) return {status:'awaiting_native_host'};
        final={status:'framework_completed_requires_independent_verification',task_id:a.task_id,mode:'native_host',text:response.text,output_sha256:response.output_sha256}; return final;
      }
      if(op === 'pending') return {pending:[requests[position]]};
      if(op === 'dispatched') { assert.equal(value.role,requests[position].role);return {status:'receipt_recorded'}; }
      if(op === 'submit') { response=value;return {status:'output_readback_recorded'}; }
      if(op === 'readback') { assert.equal(value,requests[position].request_id);position++;return response; }
      if(op === 'status') return {status:final.status,final,pending_count:0};
      throw new Error('unexpected fixture operation');
    }};
    const activation = validateActivation({...f,synthetic:true});
    const writes=[];
    const result = await runMagenticCycle({ api:remote.api,controller,rpc,journal,reservation,runtime:f.runtime,gate:activation.gate,authorization:a,framework,frameworkConfig,artifactDirectory:HERE,bindAssessment,writeArtifact:async(file,text)=>writes.push({file,text}) });
    assert.equal(result.client_turn_requests,4);assert.equal(fake.count(),4);assert.equal(result.status,'result_received');assert.equal(writes.length,3);
    assert.equal((await journal.status()).state,'completed');assert.equal(seen.filter(x=>x==='readback').length,3);
    await assert.rejects(journal.call('turn-intent',{request_id:requests[0].request_id,phase:'manager',data:{thread_id:'SYNTHETIC',turn_request_sha256:sha('retry')}}));
  } finally { await remote.stop(); }
});

test('finite owner pump binds each new admission and stops without retry on uncertainty', async () => {
  const {finitePump}=await import('./owner-poll.mjs');
  const policy={max_jobs:2,expires_at:Date.now()/1000+100},states=[];let calls=0,executed=0;
  const admission=n=>({reservation:{task_id:'SYNTHETIC-owner-'+n,runner_key:'SYNTHETIC-key'}});
  const result=await finitePump({policy,workerId:'SYNTHETIC-worker',readiness:async()=>{},saveState:async s=>states.push(s),makeJob:async a=>a,executeJob:async a=>{executed++;return{status:'result_received',task_id:a.reservation.task_id,output_sha256:sha('SYNTHETIC')};},api:{async call(endpoint,body){assert.equal(endpoint,'/v1/worker/magentic/admit');assert.equal(body.policy_sha256,sha(canonical(policy)));assert.equal(states.at(-1).state,'admission_intent');return{admission:admission(++calls)};}}});
  assert.equal(calls,2);assert.equal(executed,2);assert.equal(result.completed.length,2);
  let uncertain=0;
  await assert.rejects(finitePump({policy,workerId:'SYNTHETIC-worker',readiness:async()=>{},saveState:async()=>{},makeJob:async()=>{throw Error('must not execute');},executeJob:async()=>{},api:{async call(){uncertain++;throw Error('synthetic uncertain HTTP');}}}),/uncertain/);
  assert.equal(uncertain,1);
});
