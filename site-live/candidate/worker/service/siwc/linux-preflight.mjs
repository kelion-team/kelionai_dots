// Explicit finite Linux command/sandbox verification. No OAuth, thread or turn.
import { promises as fs } from 'node:fs';
import path from 'node:path';
import net from 'node:net';
import { randomUUID } from 'node:crypto';
import { pathToFileURL } from 'node:url';
import { permissionConfiguration, PERMISSION_PROFILE } from './permissions.mjs';
import { assertPrivateDirectory } from './crypto-store.mjs';
import { spawnProvider, INITIALIZE } from './provider.mjs';
import { GeneratedProtocol, PrivateRPC, sha, canonical } from './private-rpc.mjs';
import { requireValue, SiwcError } from './oauth.mjs';

export async function linuxPreflight(settings) {
  requireValue(process.platform==='linux','linux_preflight_requires_linux');
  requireValue([settings.codex_executable,settings.python_executable,settings.protocol_directory,settings.preflight_root].every(path.isAbsolute),'absolute_preflight_paths_required');
  await assertPrivateDirectory(settings.preflight_root);
  const root=await fs.mkdtemp(path.join(settings.preflight_root,'siwc-synthetic-'));
  await fs.chmod(root,0o700);
  const workspace=path.join(root,'empty-workspace'),home=path.join(root,'codex-home'),vault=path.join(root,'vault'),credentials=path.join(root,'credentials');
  for(const d of [workspace,home,vault,credentials])await fs.mkdir(d,{mode:0o700});
  const allowed=path.join(workspace,'allowed-synthetic'),denied=[path.join(vault,'sentinel'),path.join(credentials,'sentinel'),path.join(home,'sentinel')];
  for(const file of [allowed,...denied])await fs.writeFile(file,'SYNTHETIC_ONLY',{mode:0o600});
  const permissions=permissionConfiguration({workspace,protectedPaths:[home,vault,credentials],codexExecutable:settings.codex_executable});
  const pins=JSON.parse(await fs.readFile(new URL('./protocol-pins.json',import.meta.url),'utf8'));
  const protocol=await GeneratedProtocol.load(settings.protocol_directory,pins);
  let child;const listener=net.createServer(socket=>socket.destroy());
  try {
    await new Promise((resolve,reject)=>{listener.once('error',reject);listener.listen(0,'127.0.0.1',resolve);});
    const record={schema:1,status:'ready',issuer:'https://auth.openai.com',subject:'SYNTHETIC',client_id:'oaiapp_SYNTHETIC',ext_agent_host_id:randomUUID(),access_token:'SYNTHETIC-NOT-A-GRANT-'+randomUUID(),expires_at:Date.now()+600000,scopes:['openid','offline_access','resource.invoke','chatgpt.tokens.use.direct']};
    child=await spawnProvider({executable:settings.codex_executable,codexHome:home,record,permissions});
    const rpc=new PrivateRPC(child,protocol,30000);await rpc.rpc(INITIALIZE.method,INITIALIZE.params);rpc.notifyInitialized();
    const probe=`import os,json,socket\nchecks={}\nchecks['workspace_read']=open(${JSON.stringify(allowed)}).read()=='SYNTHETIC_ONLY'\nchecks['env_filtered']='ACCESS_TOKEN' not in os.environ\nfor i,p in enumerate(${JSON.stringify(denied.concat(['/proc/'+child.pid+'/environ','/proc/self/environ']))}):\n try:\n  fd=os.open(p,os.O_RDONLY);os.close(fd);checks['deny_'+str(i)]=False\n except OSError:checks['deny_'+str(i)]=True\ntry:\n f=open(${JSON.stringify(allowed)},'a');f.close();checks['workspace_write_denied']=False\nexcept OSError:checks['workspace_write_denied']=True\ns=None\ntry:\n s=socket.socket();s.settimeout(1)\n s.connect(('127.0.0.1',${listener.address().port}));checks['network_denied']=False\nexcept OSError:checks['network_denied']=True\nfinally:\n if s is not None:s.close()\nprint(json.dumps(checks))\n`;
    const result=await rpc.rpc('command/exec',{command:[settings.python_executable,'-c',probe],cwd:workspace,permissionProfile:PERMISSION_PROFILE,timeoutMs:10000,outputBytesCap:8192});
    requireValue(result.exitCode===0,'synthetic_sandbox_probe_failed');
    const checks=JSON.parse(result.stdout);requireValue(Object.keys(checks).length===9&&Object.values(checks).every(x=>x===true),'synthetic_secret_isolation_checks_failed');
    const evidence={kind:'actual_linux_sandbox_synthetic_sentinels',checked_at:new Date().toISOString(),executable_sha256:sha(await fs.readFile(settings.codex_executable)),permission_configuration_sha256:sha(canonical(permissions)),permission_implementation_sha256:sha(await fs.readFile(new URL('./permissions.mjs',import.meta.url))),checks,model_turns:0,oauth_requests:0,actual_secrets_used:false,scope:'command/exec named-profile sandbox and computed shell environment; production paths must use the same deny-policy construction'};
    await fs.writeFile(path.join(root,'evidence.json'),JSON.stringify(evidence,null,2),{mode:0o600});
    return evidence;
  } finally {
    listener.close();
    if(child&&child.exitCode===null)await new Promise(resolve=>{const timer=setTimeout(()=>{child.kill('SIGKILL');resolve();},3000);child.once('exit',()=>{clearTimeout(timer);resolve();});child.kill();});
  }
}
if(process.argv[1]&&import.meta.url===pathToFileURL(path.resolve(process.argv[1])).href){
  (async()=>{requireValue(process.argv.length===3,'usage_linux_preflight_SETTINGS_JSON');return linuxPreflight(JSON.parse(await fs.readFile(process.argv[2],'utf8')));})()
    .then(result=>console.log(JSON.stringify(result))).catch(e=>{console.error(JSON.stringify({status:'failed',code:e instanceof SiwcError?e.code:'linux_preflight_failed',isolation_verified:false}));process.exitCode=1;});
}
