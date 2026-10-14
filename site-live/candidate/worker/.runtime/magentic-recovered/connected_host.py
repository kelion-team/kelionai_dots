"""Bind original Magentic requests to actual native host output artifacts.

The native conversation performs dispatch through its exposed collaboration tools.
This bridge never calls a model provider, fabricates a reply, or infers provenance
from a checksum. It consumes only request-bound artifacts read back from disk.
Frozen framework/candidate sources and the previous proof are read-only inputs.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
CANDIDATE = ROOT.parent if Path(__file__).name == 'magentic_host.py' else ROOT / 'integrated'
PYTHON = Path('/workspace/kelion-magentic-integration-20261012/.venv/bin/python')
RUN = ROOT / 'magentic-connected-run'
LOG = ROOT / 'connected-command-evidence.jsonl'
REQUESTED_MODEL = 'gpt-6-luna'
REQUESTED_EFFORT = 'xhigh'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def validate_request_id(request_id):
    if not isinstance(request_id, str) or not re.fullmatch(r'[a-f0-9]{64}', request_id):
        raise ValueError('Malformed original request identifier')
    return request_id


def execute(*arguments):
    argv = [str(PYTHON), '-m', 'orchestration.magentic_candidate.cli',
            '--run-dir', str(RUN), *arguments]
    start = time.monotonic()
    result = subprocess.run(argv, cwd=CANDIDATE, capture_output=True, timeout=20)
    record = {'argv': argv, 'cwd': str(CANDIDATE), 'rc': result.returncode,
              'seconds': round(time.monotonic() - start, 4),
              'child_timeout_seconds': 20,
              'stdout_sha256': digest(result.stdout),
              'stderr_sha256': digest(result.stderr)}
    with LOG.open('a') as log:
        log.write(json.dumps(record) + '\n')
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors='replace')[-2000:])
    return json.loads(result.stdout)


def export_pending():
    pending = execute('pending')['pending']
    paths = []
    directory = ROOT / 'host-input'
    directory.mkdir(mode=0o700, exist_ok=True)
    for request in pending:
        request_id = validate_request_id(request['request_id'])
        path = directory / (request_id + '.json')
        data = (json.dumps(request, ensure_ascii=False, indent=2) + '\n').encode()
        if path.exists() and path.read_bytes() != data:
            # Dispatch status can change while the original input remains identical.
            saved = json.loads(path.read_bytes())
            if {k:v for k,v in saved.items() if k!='dispatch_state'} != {
                    k:v for k,v in request.items() if k!='dispatch_state'}:
                raise ValueError('Conflicting original request artifact')
        else:
            path.write_bytes(data)
        paths.append({'request_id': request['request_id'], 'role': request['role'],
                      'path': str(path), 'sha256': digest(path.read_bytes())})
    return {'pending_count': len(pending), 'requests': paths}


def ingest(path, actor, dispatch_ref, assessment_path=None):
    original = path.read_bytes()
    output = json.loads(original)
    if output.get('source_actor') != actor:
        raise ValueError('Original output actor differs from actual dispatch actor')
    request_id = output.get('request_id')
    validate_request_id(request_id)
    request_path = ROOT / 'host-input' / (str(request_id) + '.json')
    request = json.loads(request_path.read_bytes())
    if request['request_id'] != request_id:
        raise ValueError('Original output request binding mismatch')
    original_request = {k:v for k,v in request.items()
                        if k not in ('request_id', 'input_sha256', 'dispatch_state')}
    encoded_request = json.dumps(original_request, ensure_ascii=False, sort_keys=True,
                                separators=(',', ':'), allow_nan=False).encode()
    if digest(encoded_request) != request_id:
        raise ValueError('Original request artifact integrity mismatch')
    text = output.get('text')
    if not isinstance(text, str) or not text.strip():
        raise ValueError('Original output must contain nonempty text')
    receipt = {'request_id': request_id, 'input_sha256': request_id,
        'task_id': request['task_id'], 'role': request['role'],
        'execution_kind': 'native_host', 'native_surface': 'Kelion native collaboration runtime',
        'host_run_id': actor, 'dispatch_ref': dispatch_ref, 'selected_by': 'Kelion',
        'model': None, 'reasoning_effort': None, 'cost_evidence_ref': None,
        'actual_model_attested': False, 'actual_effort_attested': False,
        'model_execution_attested': False, 'cost_authorized_no_new_cost': None,
        'requested_model': REQUESTED_MODEL, 'requested_reasoning_effort': REQUESTED_EFFORT,
        'original_output_ref': str(path), 'original_output_sha256': digest(original)}
    if request['kind'] == 'participant_execution':
        if assessment_path is None:
            raise ValueError('Actual request-bound native participant assessment required')
        receipt['assessment'] = json.loads(assessment_path.read_bytes())
    response = {'request_id': request_id, 'input_sha256': request_id,
        'task_id': request['task_id'], 'host_run_id': actor,
        'execution_kind': 'native_host', 'text': text,
        'output_sha256': digest(text.encode()), 'result_ref': str(path)}
    directory = ROOT / 'host-ingested'
    directory.mkdir(mode=0o700, exist_ok=True)
    files = []
    for label, value in [('receipt', receipt), ('response', response)]:
        target = directory / (request_id + '-' + label + '.json')
        data = (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()
        if target.exists() and target.read_bytes() != data:
            raise ValueError('Conflicting immutable host ingestion artifact')
        target.write_bytes(data)
        files.append(target)
    execute('dispatched', '--file', str(files[0]))
    execute('submit', '--file', str(files[1]))
    recovered = execute('readback', '--request-id', request_id)
    if recovered != response or path.read_bytes() != original:
        raise ValueError('Readback differs from original actual output')
    return {'request_id': request_id, 'actual_actor': actor,
            'original_output_sha256': digest(original),
            'readback_identical': True, 'output_sha256': response['output_sha256'],
            'provenance_authenticated_by_hash': False,
            'actual_model_and_effort_attested': False,
            'actual_cost_attested': False}


def main():
    global ROOT, CANDIDATE, PYTHON, RUN, LOG, REQUESTED_MODEL, REQUESTED_EFFORT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, default=CANDIDATE)
    parser.add_argument('--framework-python', type=Path, default=PYTHON)
    parser.add_argument('--state-root', type=Path, default=ROOT)
    parser.add_argument('--run-dir', type=Path, default=RUN)
    parser.add_argument('--requested-model', default=REQUESTED_MODEL)
    parser.add_argument('--requested-effort', default=REQUESTED_EFFORT)
    sub = parser.add_subparsers(dest='operation', required=True)
    for name in ['advance', 'pending', 'status']:
        sub.add_parser(name)
    init_parser = sub.add_parser('init')
    init_parser.add_argument('--file', required=True, type=Path)
    import_parser = sub.add_parser('ingest')
    import_parser.add_argument('--file', required=True, type=Path)
    import_parser.add_argument('--actor', required=True)
    import_parser.add_argument('--dispatch-ref', required=True)
    import_parser.add_argument('--assessment', type=Path)
    args = parser.parse_args()
    ROOT, CANDIDATE, PYTHON, RUN = args.state_root, args.source_root, args.framework_python, args.run_dir
    REQUESTED_MODEL, REQUESTED_EFFORT = args.requested_model, args.requested_effort
    LOG = ROOT / 'connected-command-evidence.jsonl'
    if args.operation == 'ingest':
        result = ingest(args.file, args.actor, args.dispatch_ref, args.assessment)
    elif args.operation == 'advance':
        result = execute('advance')
        result = {k:v for k,v in result.items() if k!='pending'}
        result['host_requests'] = export_pending()
    elif args.operation == 'pending':
        result = export_pending()
    elif args.operation == 'init':
        result = execute('init', '--file', str(args.file))
    else:
        result = execute('status')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
