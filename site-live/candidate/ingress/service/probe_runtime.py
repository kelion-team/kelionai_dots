"""Read-only official CLI probe. Never opens auth files or starts an inference turn."""
import argparse
import json
import os
import queue
import shutil
import subprocess
import threading
import time
from pathlib import Path


def child_environment(existing_codex_dir=None, source_environment=None):
    """Point official CODEX_HOME to existing state, without modifying parent env."""
    original = os.environ if source_environment is None else source_environment
    child = dict(original)
    configured = existing_codex_dir or original.get('CODEX_HOME')
    if not configured and original.get('USERPROFILE'):
        configured = str(Path(original['USERPROFILE']) / '.codex')
    if configured:
        existing = Path(configured).resolve()
        if not existing.is_dir():
            raise ValueError('Existing Codex state directory required; nothing is created or copied')
        child['CODEX_HOME'] = str(existing)
    return child


def probe(existing_codex_dir=None):
    executable=shutil.which('codex')
    report={'adapter_implemented':'native-parent','cli_executable':executable,
            'cli_auth_verified':False,'cli_model_support_verified':False,
            'inference_calls':0,'auth_file_read':False,'settings_changed':False}
    if not executable:
        report['cli_block']='official_codex_executable_not_found'
        return report
    environment = child_environment(existing_codex_dir)
    report['codex_home_resolution'] = 'existing_state_directory_child_environment'
    report['parent_environment_modified'] = False
    for name,args in (('version',['--version']),('exec_help',['exec','--help']),('auth_status',['login','status'])):
        try:
            result=subprocess.run([executable]+args,capture_output=True,text=True,timeout=15,env=environment)
            combined=result.stdout+'\n'+result.stderr
            entry={'exit_code':result.returncode}
            if name=='version':
                entry['version']=next((line for line in combined.splitlines() if line.startswith('codex-cli ')),None)
            elif name=='exec_help':
                entry['noninteractive_interface_documented']=('--json' in combined and '--output-last-message' in combined)
            elif result.returncode==0 and 'Logged in using ChatGPT' in combined:
                report['cli_auth_verified']=True
                entry['auth_type']='ChatGPT'
            elif 'Could not find home directory' in combined:
                report['cli_block']='home_resolution_failed_before_auth_status'
            else:
                report['cli_block']='authentication_not_verified_as_included_ChatGPT_usage'
            # Never retain raw login status: some auth modes print key identifiers.
            report[name]=entry
        except (OSError,subprocess.TimeoutExpired):
            report[name]={'error':'read_only_probe_failed_or_timed_out'}
    report['limit']='CLI auth status is verified only when cli_auth_verified=true. Model execution and hosted eligibility are not established. Native-parent is a separate runtime.'
    return report


def appserver_catalog(existing_codex_dir=None):
    """Only initialize/account/catalog/quota RPCs; never creates threads or turns."""
    report = {'transport':'stdio','inference_calls':0,'threads_started':0,'turns_started':0,
              'global_config_changed':False,'auth_file_read_by_probe':False,
              'model_execution_eligibility_verified':False,'catalog_retrieved':False}
    executable = shutil.which('codex')
    if not executable:
        return dict(report, failure='official_codex_executable_not_found')
    environment = child_environment(existing_codex_dir)
    # Official per-process state overrides; auth remains in the original directory.
    state = Path(__file__).resolve().parent / 'private/runtime-probe'
    state.mkdir(parents=True, exist_ok=True)
    report['sqlite_state_location'] = 'service/private/runtime-probe'
    args = [executable,'app-server','--stdio','-c','sqlite_home='+json.dumps(str(state)),
            '-c','log_dir='+json.dumps(str(state / 'logs'))]
    process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, encoding='utf-8', errors='replace', env=environment)
    messages = queue.Queue()
    warnings = {'access_denied':False,'sqlite_initialization_failed':False,'home_resolution_failed':False}
    def read_stdout():
        for line in process.stdout:
            try:
                messages.put(json.loads(line))
            except ValueError:
                pass
        messages.put(None)
    def read_stderr():
        for line in process.stderr:
            warnings['access_denied'] |= 'Access is denied' in line
            warnings['sqlite_initialization_failed'] |= 'failed to initialize sqlite state runtime' in line
            warnings['home_resolution_failed'] |= 'Could not find home directory' in line
        # Raw diagnostics are intentionally discarded, including all credential identifiers.
    readers = [threading.Thread(target=read_stdout,daemon=True),threading.Thread(target=read_stderr,daemon=True)]
    for reader in readers:
        reader.start()
    def send(value):
        process.stdin.write(json.dumps(value)+'\n')
        process.stdin.flush()
    def rpc(identity, method, params):
        send({'id':identity,'method':method,'params':params})
        end = time.monotonic()+20
        while time.monotonic() < end:
            try:
                value = messages.get(timeout=max(0.1,end-time.monotonic()))
            except queue.Empty:
                raise TimeoutError('Read-only RPC timeout')
            if value is None:
                raise RuntimeError('App-server exited before replying')
            if value.get('id') == identity:
                if 'error' in value:
                    return {'rpc_error_code':value['error'].get('code')}
                return value.get('result',{})
        raise TimeoutError('Read-only RPC timeout')
    try:
        init = rpc(1,'initialize',{'clientInfo':{'name':'kelion_runtime_probe',
                           'title':'Kelion local read-only runtime probe','version':'0.2.0'}})
        report['initialize_success'] = 'rpc_error_code' not in init
        if not report['initialize_success']:
            report['initialize_error_code'] = init['rpc_error_code']
            return report
        send({'method':'initialized','params':{}})
        account = rpc(2,'account/read',{'refreshToken':False})
        info = account.get('account') or {}
        report['account'] = {'type':info.get('type'),'plan_type':info.get('planType'),
                             'requires_openai_auth':account.get('requiresOpenaiAuth')}
        if 'rpc_error_code' in account:
            report['account_error_code'] = account['rpc_error_code']
        models = rpc(3,'model/list',{'limit':100,'includeHidden':False})
        report['catalog_retrieved'] = 'rpc_error_code' not in models
        report['catalog'] = [{'id':item.get('id'),'model':item.get('model'),
            'reasoning_efforts':[value.get('reasoningEffort') for value in item.get('supportedReasoningEfforts',[])],
            'default_reasoning_effort':item.get('defaultReasoningEffort'),'is_default':item.get('isDefault')}
            for item in models.get('data',[])]
        report['catalog_next_cursor'] = models.get('nextCursor')
        if 'rpc_error_code' in models:
            report['catalog_error_code'] = models['rpc_error_code']
        quota = rpc(4,'account/rateLimits/read',{})
        # Keep only limits, not workspace/account identifiers or diagnostic text.
        report['rate_limits'] = quota.get('rateLimits')
        if 'rpc_error_code' in quota:
            report['rate_limits_error_code'] = quota['rpc_error_code']
    except (OSError,RuntimeError,TimeoutError,ValueError) as exc:
        report['failure_type'] = type(exc).__name__
    finally:
        if process.stdin:
            process.stdin.close()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.terminate()
            process.wait(timeout=3)
        for reader in readers:
            reader.join(timeout=1)
        report['process_exit_code'] = process.returncode
        report['warnings'] = warnings
        if not report.get('initialize_success') and warnings['access_denied']:
            report['platform_block'] = 'access_denied_before_initialize'
    report['limit'] = 'Read-only catalog may be cached. No successful inference or hosted/commercial auth eligibility is established.'
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',required=True,type=Path)
    parser.add_argument('--existing-codex-dir',type=Path,help='Existing official state directory; no auth copy or global setting change')
    parser.add_argument('--catalog',action='store_true',help='Read-only AppServer account/catalog/quota probe with local state overrides')
    args=parser.parse_args()
    result=probe(args.existing_codex_dir)
    if args.catalog:
        result['appserver'] = appserver_catalog(args.existing_codex_dir)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))
