// Explicit finite service entry; imports never start a worker or OAuth flow.
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {readPrivate} from './crypto-store.mjs';
import {workerPoll} from './owner-poll.mjs';
import {requireValue,SiwcError} from './oauth.mjs';

export async function runSystemd() {
  const credentials=process.env.CREDENTIALS_DIRECTORY,state=process.env.STATE_DIRECTORY;
  requireValue(credentials&&state&&path.isAbsolute(credentials)&&path.isAbsolute(state)&&!state.includes(':'),'systemd_credentials_and_state_required');
  const privateConfig=path.join(credentials,'worker-config.json');
  const config=JSON.parse(await readPrivate(privateConfig));
  // Bind LoadCredential names and DynamicUser state to the operator's reviewed
  // document. Never silently rewrite the runtime or its hash for a new UID.
  requireValue(config.private_root===state&&config.worker_token_file===path.join(credentials,'worker.token')&&config.vault_key_file===path.join(credentials,'vault.key'),'systemd_paths_must_match_reviewed_configuration');
  return workerPoll({enabled:true,private_config:privateConfig});
}
if(process.argv[1]&&import.meta.url===pathToFileURL(path.resolve(process.argv[1])).href)runSystemd().then(r=>console.log(JSON.stringify(r))).catch(e=>{console.error(JSON.stringify({status:'stopped',code:e instanceof SiwcError?e.code:'finite_service_failed',live_success_claimed:false}));process.exitCode=1;});
