// A finite session pump. Every admitted task owns a fresh directory and the
// original task journal. Unknown admission/turn state is never retried.
import { promises as fs } from 'node:fs';
import path from 'node:path';
import { setTimeout as delay } from 'node:timers/promises';
import { readPrivate,writePrivate,assertPrivateDirectory,Vault } from './crypto-store.mjs';
import { requireValue } from './oauth.mjs';
import { validateReady } from './provider.mjs';
import { canonical,sha } from './private-rpc.mjs';
import { HttpWorker,workerOnce,grantFingerprint,runtimeScope,operatorPayload } from './worker.mjs';

export function verifyPollReadiness(config,readiness,record,now=Date.now()/1000,authorityKey) {
  const p=config.runtime.siwc_magentic,e=operatorPayload(readiness,authorityKey),q=e.account_allowance;
  requireValue(p?.enabled===true&&p.mode==='owner_gateway'&&p.dedicated_owner_gateway_client===true&&p.activated_at<=now&&now<p.expires_at&&p.expires_at<=p.activated_at+3600&&p.gateway_client_token_sha256===p.frontend_receipt_client_token_sha256&&/^[a-f0-9]{64}$/.test(p.gateway_client_token_sha256),'current_owner_gateway_policy_required');
  validateReady(record,now*1000,{allowExpiring:true});
  requireValue(e.kind==='siwc_account_readiness'&&e.grant_fingerprint===grantFingerprint(record)&&p.grant_fingerprint===e.grant_fingerprint&&e.runtime_scope_sha256===runtimeScope(config.runtime)&&e.expires_at>now&&e.credential_isolation_verified===true&&e.credential_isolation_evidence_ref,'actual_account_isolation_binding_required');
  requireValue(q?.available===true&&q.billing_mode==='included'&&q.observed_at>0&&q.observed_at<=now&&q.expires_at>now&&q.expires_at<=e.expires_at&&q.source_ref,'fresh_account_allowance_required');
  return p;
}

export async function finitePump({policy,workerId,api,readiness,saveState,makeJob,executeJob,sleep=delay,maxIdlePolls=30,pollMs=2000}) {
  requireValue(Number.isInteger(maxIdlePolls)&&maxIdlePolls>=1&&maxIdlePolls<=300&&Number.isInteger(pollMs)&&pollMs>=100&&pollMs<=30000,'finite_poll_configuration_required');
  const results=[];let idle=0;
  while(results.length<policy.max_jobs&&idle<maxIdlePolls&&Date.now()/1000<policy.expires_at) {
    await readiness();
    await saveState({state:'admission_intent',policy_sha256:sha(canonical(policy))});
    const response=await api.call('/v1/worker/magentic/admit',{worker_id:workerId,policy_sha256:sha(canonical(policy))});
    if(!response.admission) {
      await saveState({state:'idle',stop_reason:response.stop_reason});
      if(response.stop_reason!=='no_new_owner_gateway_task')return {status:response.stop_reason,completed:results};
      if(++idle<maxIdlePolls)await sleep(pollMs);continue;
    }
    idle=0;const admitted=response.admission;
    await saveState({state:'admitted',task_id:admitted.reservation.task_id,runner_key:admitted.reservation.runner_key});
    const job=await makeJob(admitted);
    const result=await executeJob(job,admitted);
    requireValue(result.status==='result_received'&&result.task_id===admitted.reservation.task_id,'completed_task_readback_required');
    results.push(result);
    await saveState({state:'completed',task_id:result.task_id,output_sha256:result.output_sha256});
  }
  return {status:'finite_poll_finished',completed:results};
}

export async function workerPoll(settings) {
  requireValue(settings.enabled===true,'siwc_worker_disabled');
  const config=JSON.parse(await readPrivate(settings.private_config));
  requireValue(config.private_root&&config.session_state_root&&config.session_jobs_root,'private_session_paths_required');
  await assertPrivateDirectory(config.session_state_root);await assertPrivateDirectory(config.session_jobs_root);
  const lock=path.join(config.session_state_root,'poll.lock'),stateFile=path.join(config.session_state_root,'poll-state.json');
  const handle=await fs.open(lock,'wx',0o600);let safe=false;
  try {
    await handle.writeFile(JSON.stringify({pid:process.pid,started_at:new Date().toISOString()}));await handle.sync();
    try {const previous=JSON.parse(await readPrivate(stateFile));requireValue(['idle','completed'].includes(previous.state),'previous_admission_requires_reconciliation');}catch(e){if(e.code!=='ENOENT')throw e;}
    const token=(await readPrivate(config.worker_token_file)).toString('utf8').trim(),api=new HttpWorker(config.api_origin,token);
    const ready=async()=>{
      const key=await readPrivate(config.vault_key_file),vault=new Vault(config.vault_root,key);key.fill(0);
      try {const state=await vault.read();requireValue(state.phase==='stopped','prior_provider_state_requires_reconciliation');const authorityKey=config.authority_public_key_file?(await readPrivate(config.authority_public_key_file)).toString('utf8'):undefined;return verifyPollReadiness(config,JSON.parse(await readPrivate(config.readiness_file)),state.record,Date.now()/1000,authorityKey);}finally{vault.close();}
    };
    const policy=await ready();
    const result=await finitePump({policy,workerId:config.worker_id,api,readiness:ready,saveState:s=>writePrivate(stateFile,canonical(s)),maxIdlePolls:config.max_idle_polls??30,pollMs:config.poll_ms??2000,
      makeJob:async admission=>{
        requireValue(admission.runtime_sha256===sha(canonical(config.runtime))&&admission.authorization.policy_sha256===sha(canonical(policy)),'admission_runtime_policy_mismatch');
        const id=admission.reservation.task_id;requireValue(/^[A-Za-z0-9][A-Za-z0-9_.-]{3,127}$/.test(id),'admitted_task_id_required');
        const root=path.join(config.session_jobs_root,id);await fs.mkdir(root,{mode:0o700});
        for(const name of ['operator','framework','artifacts','codex-home'])await fs.mkdir(path.join(root,name),{mode:0o700});
        const job={...config,operator_state_root:path.join(root,'operator'),framework_run_directory:path.join(root,'framework'),framework_artifact_directory:path.join(root,'artifacts'),codex_home:path.join(root,'codex-home'),authorization_file:path.join(root,'authorization.json'),framework_config_file:path.join(root,'framework.json')};
        await writePrivate(job.authorization_file,canonical(admission.authorization));await writePrivate(job.framework_config_file,canonical(admission.framework_config));return job;
      },executeJob:(job,admission)=>workerOnce(settings,{config:job,admission})});
    safe=true;return result;
  } finally {
    await handle.close();
    // Preserve the lock after any failure or unknown HTTP outcome. A later
    // process cannot turn a crash into another admission or model request.
    if(safe)await fs.unlink(lock);
  }
}
