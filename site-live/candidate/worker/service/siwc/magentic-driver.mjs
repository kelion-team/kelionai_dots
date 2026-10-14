import path from 'node:path';
import { canonical, sha, actualPhase } from './private-rpc.mjs';
import { FRAMEWORK_COMMIT, magenticReceipt } from './magentic-receipt.mjs';
import { requireValue, SiwcError } from './oauth.mjs';
import { writePrivate } from './crypto-store.mjs';

export class MagenticHTTPJournal {
  constructor(api, taskId, runnerKey, workerId) { Object.assign(this,{api,taskId,runnerKey,workerId});this.phases={}; }
  async call(operation,body={}) { return this.api.call('/v1/worker/magentic/'+operation,{task_id:this.taskId,runner_key:this.runnerKey,worker_id:this.workerId,...body}); }
  status(){return this.call('status');}
  phaseJournal(requestId) {
    return { phase:async(phase,update)=>{
      const k=requestId+'/'+phase, data={...(this.phases[k]??{}),...update};this.phases[k]=data;
      await this.call('checkpoint',{request_id:requestId,phase,data});
    },turnIntent:async(phase,params)=>{
      const k=requestId+'/'+phase,data={...this.phases[k],state:'turn_start_intent',turn_request_sha256:sha(canonical(params))};
      const r=await this.call('turn-intent',{request_id:requestId,phase,data});
      requireValue(Number.isInteger(r.index)&&r.index>0,'magentic_durable_intent_missing');this.phases[k]={...data,client_turn_request_index:r.index};
    }};
  }
}
export function boundFrameworkConfig(config,raw,registry) {
  requireValue(config?.enabled===true&&config.mode==='native_host'&&config.task_id===raw.task_id&&config.objective===raw.task&&Array.isArray(config.participants),'exact_framework_job_required');
  const roles=config.participants.map(n=>registry.roles.find(r=>r.name===n));
  requireValue(roles.every(Boolean)&&new Set(config.participants).size===roles.length,'canonical_framework_participants_required');
  return {...config,roles,framework_commit:FRAMEWORK_COMMIT};
}
export async function runMagenticCycle({api,controller,rpc,journal,reservation,runtime,gate,authorization,framework,frameworkConfig,artifactDirectory,bindAssessment,writeArtifact=writePrivate}) {
  const raw=reservation.payload.request;
  requireValue(reservation.state==='running_kelion'&&reservation.input_hash===sha(canonical(raw))&&!raw.role,'new_owned_raw_task_required');
  const {registry}=await controller.call({action:'registry'});
  const bound=boundFrameworkConfig(frameworkConfig,raw,registry);
  requireValue(sha(canonical(bound))===authorization.framework_config_sha256,'framework_configuration_binding_mismatch');
  let calls=0;
  const operation=async(name,value)=>{
    requireValue(++calls<=8*authorization.max_turns+8,'finite_framework_operation_limit');
    const result=await framework.call(name,value);
    if(['init','advance','pending','status'].includes(name))await journal.call('operation',{operation:name,result_sha256:sha(canonical(result))});
    return result;
  };
  const bootstrap=async task=>{const p=await controller.call({action:'bootstrap',task,manifest:runtime.manifest});return{model:p.host_model.id,reasoning_effort:p.host_model.reasoning};};
  try {
    const initial=await operation('init',frameworkConfig);requireValue(initial.status==='initialized','framework_initialization_failed');
    for(let iteration=0;iteration<=authorization.max_turns;iteration++) {
      const advanced=await operation('advance');
      if(advanced.status==='framework_completed_requires_independent_verification') {
        const status=await operation('status');
        requireValue(canonical(status.final)===canonical(advanced)&&status.pending_count===0,'framework_final_readback_mismatch');
        const result=await journal.call('complete',{final:advanced,status_readback:status});
        requireValue(result.state==='result_received'&&result.output_hash===advanced.output_sha256&&result.output===advanced.text,'web_job_persistence_mismatch');
        return {task_id:raw.task_id,status:'result_received',output_sha256:result.output_hash,client_turn_requests:(await journal.status()).journal.client_turn_requests,framework_terminal_readback:true,monetary_cost:null,per_turn_model_attestation:false};
      }
      requireValue(advanced.status==='awaiting_native_host','unsupported_framework_state');
      const pending=await operation('pending');requireValue(Array.isArray(pending.pending)&&pending.pending.length>0,'framework_pending_request_missing');
      for(const request of pending.pending) {
        const {request_id,input_sha256,dispatch_state,...payload}=request;
        requireValue(request_id===input_sha256&&request_id===sha(canonical(payload))&&dispatch_state==='awaiting_native_host'&&request.task_id===raw.task_id&&request.config_sha256===authorization.framework_config_sha256&&request.framework_commit===FRAMEWORK_COMMIT,'original_framework_pending_binding_mismatch');
        await journal.call('request',{request});
        const phaseJournal=journal.phaseJournal(request_id), prompt=canonical(payload);
        let chosen,assessment,developer=request.system_instructions,phase;
        if(request.kind==='manager_reasoning') {
          requireValue(request.role==='kelion_manager','framework_manager_role_mismatch');
          chosen=await bootstrap('Planifică și coordonează cererea Magentic Kelion');phase='manager';
        } else {
          requireValue(request.kind==='participant_execution','unsupported_framework_request_kind');
          const role=registry.roles.find(r=>r.name===request.role);requireValue(role&&canonical(role)===canonical(request.native_profile),'canonical_framework_profile_mismatch');
          const assessed=await actualPhase({rpc,journal:phaseJournal,gate,phase:'assessment',chosen:await bootstrap('Clasifica dificultatea cererii pentru profilul DOTS ales'),workspace:runtime.workspace,developer:role.developer_instructions,prompt:canonical({phase:'assessment',task_id:raw.task_id,source_agent_id:role.source_agent_id,task_input:prompt,return_fields:['task_id','source_agent_id','difficulty','reason','risk_flags']})});
          assessment=bindAssessment({task_id:raw.task_id,task:prompt},role,assessed.output);
          const plan=await controller.call({action:'plan',request:{task_id:raw.task_id,task:prompt,role:role.role,surface:'codex',logic_validation_required:frameworkConfig.logic_validation_required===true},assessment,manifest:runtime.manifest});
          requireValue(plan.status==='native_spawn_prepared'&&plan.requires_action_approval!==true,'original_controller_action_approval_or_plan_blocked');
          chosen={model:plan.spawn_request.model,reasoning_effort:plan.spawn_request.reasoning_effort};
          // Keep the exact original framework payload as the user request; carry
          // the original controller's complete work envelope in developer scope.
          developer=role.developer_instructions+'\n'+request.system_instructions+'\n'+plan.spawn_request.message;
          assessment={...assessment,input_sha256:request_id};phase='work';
        }
        const proof=await actualPhase({rpc,journal:phaseJournal,gate,phase,chosen,workspace:runtime.workspace,developer,prompt});
        const resultRef=path.join(artifactDirectory,request_id+'-actual-output.json');
        const artifact=canonical({request_id,text:proof.output,source_actor:proof.thread_id,dispatch_ref:proof.turn_id,proof});
        await writeArtifact(resultRef,artifact);
        const converted=magenticReceipt({request,proof,resultRef,originalOutputSha256:sha(artifact),assessment,authorization:{...authorization,authorized_request_ids:[request_id]}});
        const receiptResult=await operation('dispatched',converted.receipt);requireValue(receiptResult.status==='receipt_recorded','framework_dispatch_receipt_missing');
        const submitted=await operation('submit',converted.response);requireValue(submitted.status==='output_readback_recorded','framework_output_not_persisted');
        const recovered=await operation('readback',request_id);requireValue(canonical(recovered)===canonical(converted.response),'framework_output_readback_mismatch');
        await journal.call('readback',{request_id,receipt:converted.receipt,response:recovered});
      }
    }
    throw new SiwcError('finite_framework_iteration_limit');
  } catch(e) {
    try{await journal.call('fail',{reason:e instanceof SiwcError?e.code:'magentic_driver_failed'});}catch{}
    throw new SiwcError(e instanceof SiwcError?e.code:'magentic_requires_reconciliation');
  }
}
