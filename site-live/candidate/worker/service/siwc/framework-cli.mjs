import { spawn } from 'node:child_process';
import path from 'node:path';
import { promises as fs } from 'node:fs';
import { verifyMagenticSources } from './magentic-receipt.mjs';
import { writePrivate } from './crypto-store.mjs';
import { canonical, sha } from './private-rpc.mjs';
import { requireValue, SiwcError } from './oauth.mjs';

export class FrameworkCLI {
  constructor({ python, sourceRoot, runDirectory, artifactDirectory, spawnFn = spawn, writeFn = writePrivate }) {
    requireValue([python,sourceRoot,runDirectory,artifactDirectory].every(path.isAbsolute), 'absolute_framework_paths_required');
    Object.assign(this,{python,sourceRoot,runDirectory,artifactDirectory,spawnFn,writeFn});
  }
  async call(operation, value) {
    requireValue(['init','advance','pending','status','dispatched','submit','readback'].includes(operation), 'unsupported_framework_operation');
    await verifyMagenticSources(path.join(this.sourceRoot,'orchestration/magentic_candidate'));
    const args=['-m','orchestration.magentic_candidate.cli','--run-dir',this.runDirectory,'--timeout','20',operation];
    if (['init','dispatched','submit'].includes(operation)) {
      const file=path.join(this.artifactDirectory,operation+'-'+sha(canonical(value))+'.json');
      try { requireValue((await fs.readFile(file,'utf8'))===canonical(value),'framework_artifact_conflict'); }
      catch (e) { if (e.code!=='ENOENT') throw e; await this.writeFn(file,canonical(value)); }
      args.push('--file',file);
    } else if (operation==='readback') { requireValue(/^[a-f0-9]{64}$/.test(value),'original_request_id_required'); args.push('--request-id',value); }
    const env={PYTHONDONTWRITEBYTECODE:'1',PYTHONIOENCODING:'utf-8'};
    for (const k of ['PATH','Path','SystemRoot','WINDIR','TEMP','TMP','LANG','LC_ALL']) if (process.env[k]) env[k]=process.env[k];
    return new Promise((resolve,reject)=>{
      const child=this.spawnFn(this.python,args,{cwd:this.sourceRoot,env,shell:false,windowsHide:true,stdio:['ignore','pipe','pipe']});
      let bytes=0,failed=false; const chunks=[];
      const timer=setTimeout(()=>{failed=true;child.kill();reject(new SiwcError('framework_timeout_requires_reconciliation'));},25000);
      child.stderr.resume();child.stdout.on('data',b=>{bytes+=b.length;if(bytes>2200000){failed=true;child.kill();reject(new SiwcError('framework_output_limit'));}else chunks.push(b);});
      child.on('error',()=>{clearTimeout(timer);reject(new SiwcError('framework_spawn_failed'));});
      child.on('close',code=>{clearTimeout(timer);if(failed)return;if(code!==0)return reject(new SiwcError('framework_operation_failed'));try{resolve(JSON.parse(Buffer.concat(chunks)));}catch{reject(new SiwcError('framework_invalid_response'));}});
    });
  }
}
