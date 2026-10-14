import { requireValue } from './oauth.mjs';
import { canonical, sha } from './private-rpc.mjs';
import { promises as fs } from 'node:fs';
import path from 'node:path';

export const FRAMEWORK_COMMIT = '2d58876e49d7569dafeac6b385a120514c1e6a12';

export async function verifyMagenticSources(sourceDirectory) {
  const pins = JSON.parse(await fs.readFile(new URL('./magentic-source-pins.json', import.meta.url), 'utf8'));
  for (const [name, expected] of Object.entries(pins)) {
    requireValue(path.basename(name) === name && sha(await fs.readFile(path.join(sourceDirectory, name))) === expected, 'magentic_recovered_source_changed');
  }
  return { framework_commit: FRAMEWORK_COMMIT, recovered_sources_verified: true, framework_installed_or_executed: false };
}

// This is only a translation of an actual, request-bound readback. It neither
// starts nor simulates the Magentic framework, selects a model or expands budget.
export function magenticReceipt({ request, proof, resultRef, originalOutputSha256 = proof.output_sha256, assessment, authorization }) {
  const { request_id, input_sha256, dispatch_state, ...payload } = request;
  requireValue(request.mode === 'native_host' && request.framework_commit === FRAMEWORK_COMMIT && request_id === input_sha256 && request_id === sha(canonical(payload)), 'magentic_original_request_mismatch');
  requireValue(authorization?.task_id === request.task_id && authorization.no_new_spend === true && Number.isInteger(authorization.max_turns) && authorization.max_turns > 0 && authorization.max_turns <= 128 && authorization.expires_at > Date.now() / 1000 && Array.isArray(authorization.authorized_request_ids) && authorization.authorized_request_ids.includes(request_id), 'magentic_request_specific_budget_required');
  requireValue(proof.state === 'readback_complete' && proof.prompt_sha256 === request_id && proof.output_sha256 === sha(proof.output) && proof.thread_id && proof.turn_id && proof.configured_model && proof.configured_effort && proof.configured_binding_source === 'thread/start + thread/resume + thread/read' && typeof resultRef === 'string' && resultRef.length > 0, 'magentic_actual_request_bound_readback_required');
  if (request.kind === 'participant_execution') requireValue(assessment?.task_id === request.task_id && assessment.input_sha256 === request_id && assessment.source_agent_id === request.native_profile?.source_agent_id && Number.isInteger(assessment.difficulty) && assessment.difficulty >= 1 && assessment.difficulty <= 4 && typeof assessment.reason === 'string' && assessment.reason.trim() && Array.isArray(assessment.risk_flags), 'magentic_actual_participant_assessment_required');
  requireValue(/^[a-f0-9]{64}$/.test(originalOutputSha256), 'actual_artifact_hash_required');
  const receipt = { request_id, input_sha256, task_id: request.task_id, role: request.role, execution_kind: 'native_host', native_surface: 'codex', host_run_id: proof.thread_id, dispatch_ref: proof.turn_id, selected_by: 'Kelion', model: proof.configured_model, reasoning_effort: proof.configured_effort, cost_evidence_ref: null, actual_model_attested: false, actual_effort_attested: false, model_execution_attested: false, cost_authorized_no_new_cost: true, configured_binding_source: proof.configured_binding_source, actual_monetary_cost: null, original_output_ref: resultRef, original_output_sha256: originalOutputSha256, ...(assessment ? { assessment } : {}) };
  const response = { request_id, input_sha256, task_id: request.task_id, host_run_id: proof.thread_id, execution_kind: 'native_host', text: proof.output, output_sha256: proof.output_sha256, result_ref: resultRef };
  return { receipt, response, provenance_authenticated_by_hash: false, framework_execution_claimed: false };
}
