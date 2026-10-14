"""Coordinator-only bounded metadata diagnostic. NEVER sends turn/start or resumes jobs."""
import argparse
import json
from pathlib import Path
from appserver_transport import AppServer, Protocol, ProtocolError, RPCRejected, Attention
from local_runner import private_json


def start_params(model, workspace):
    return {'model':model,'modelProvider':'openai','allowProviderModelFallback':False,
        'cwd':str(workspace),'developerInstructions':'Metadata diagnostic only. No turn is authorized.',
        'config':{'model_reasoning_effort':'low'},'approvalPolicy':'never','approvalsReviewer':'user',
        'sandbox':'read-only','historyMode':'legacy','ephemeral':False,'serviceTier':'default'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--discovery',required=True,type=Path)
    parser.add_argument('--workspace',required=True,type=Path)
    parser.add_argument('--existing-codex-dir',type=Path)
    args=parser.parse_args()
    private=Path(__file__).resolve().parent/'private'
    if not args.discovery.resolve().is_relative_to(private):parser.error('Discovery must be private')
    if not args.workspace.is_absolute() or not args.workspace.is_dir():parser.error('Existing absolute workspace required')
    saved=json.loads(args.discovery.read_text(encoding='utf-8'))
    candidates=[entry['model'] for entry in saved.get('catalog',[]) if 'low' in entry.get('reasoning_levels',[])]
    if not candidates:parser.error('An actual discovery advertising low reasoning is required')
    protocol=Protocol(private/'appserver-protocol')
    if saved.get('protocol_sha256') != protocol.hashes:parser.error('Discovery protocol binding changed')
    import hashlib, shutil
    executable=shutil.which('codex')
    if not executable or hashlib.sha256(Path(executable).read_bytes()).hexdigest()!=saved.get('executable_sha256'):
        parser.error('Exact discovered executable required')
    outcomes=[]
    for experimental in (False,True):
        evidence={'experimental_api':experimental,'turn_start_requests':0}
        try:
            with AppServer(protocol,private/'appserver-state',args.existing_codex_dir,
                           experimental_api=experimental) as client:
                result=client.rpc('thread/start',start_params(candidates[0],args.workspace))
                evidence.update(status='thread_started_no_turn',response=result)
        except RPCRejected as exc:evidence.update(status='rpc_rejected',private_error=exc.private_error)
        except Attention as exc:evidence.update(status='attention_no_approval',request=exc.request)
        except (OSError,ProtocolError,TimeoutError) as exc:evidence.update(status='blocked',failure_type=type(exc).__name__)
        outcomes.append(evidence)
        private_json(private/'thread-start-diagnostic.json',{'variants':outcomes,'inference_requests':0})
    print(json.dumps({'private_evidence':'service/private/thread-start-diagnostic.json',
                     'variants':[{'experimental_api':x['experimental_api'],'status':x['status']} for x in outcomes],
                     'turn_start_requests':0,'job_replayed':False}))


if __name__=='__main__':main()
