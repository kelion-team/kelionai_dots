"""Task-specific byte/terminal proof; model prose alone is never success."""
import hashlib
import json
import re
import sys
from pathlib import Path
from appserver_transport import ProtocolError
from store import canonical, digest

TASK_ID = 'kelion-appserver-native-probe-20261013'


def parse_json(text):
    text = text.strip()
    if text.startswith('```'):
        text = text.split('\n', 1)[1].rsplit('```', 1)[0].strip()
    return json.loads(text)


def byte_result(workspace, task_id=TASK_ID):
    base = Path(workspace).resolve() / 'service'
    manifest = json.loads((base / 'PROVENANCE.json').read_text(encoding='utf-8'))
    files = manifest['files']
    if len(files) != 4 or len({item['path'] for item in files}) != 4:
        raise ProtocolError('Exactly four distinct provenance sources required')
    rows = []
    for item in files:
        target = (base / item['path']).resolve()
        if not target.is_relative_to(base) or not target.is_file():
            raise ProtocolError('Provenance source escaped service or is missing')
        actual = hashlib.sha256(target.read_bytes()).hexdigest()
        if actual != item['sha256']:
            raise ProtocolError('Independent immutable source hash mismatch')
        rows.append({'file': item['path'], 'expected_sha256': item['sha256'],
                     'actual_sha256': actual, 'match': True})
    return {'task_id': task_id, 'verified_count': 4, 'mismatches': 0, 'results': rows}


def terminal_command(workspace, python_executable, task_id=TASK_ID):
    manifest = (Path(workspace).resolve() / 'service/PROVENANCE.json').as_posix()
    code = ("import hashlib,json; from pathlib import Path; "
            f"p=Path({manifest!r}); m=json.loads(p.read_text(encoding='utf-8')); "
            "r=[dict(file=f['path'],expected_sha256=f['sha256'],"
            "actual_sha256=hashlib.sha256((p.parent/f['path']).read_bytes()).hexdigest()) for f in m['files']]; "
            "[x.update(match=x['expected_sha256']==x['actual_sha256']) for x in r]; "
            f"print(json.dumps(dict(task_id={task_id!r},verified_count=len(r),"
            "mismatches=sum(not x['match'] for x in r),results=r))); "
            "assert len(r)==4 and all(x['match'] for x in r)")
    quote = lambda value: "'" + str(value).replace("'", "''") + "'"
    return '& ' + quote(python_executable) + ' -c ' + quote(code)


def raw_terminal_items(client, thread, turn, workspace, task_id=TASK_ID):
    """Read only the official thread/read rollout, filtering the exact turn's tools.

    Legacy AppServer readback omits custom exec items. Never accept a caller's
    arbitrary receipt file: the path comes from the official readback and must
    remain within this official client's existing sessions directory.
    """
    raw_path = thread.get('path')
    state = getattr(client, 'environment', {}).get('CODEX_HOME')
    if not raw_path or not state:
        raise ProtocolError('Official rollout path and existing Codex state required for custom exec proof')
    path = Path(raw_path).resolve(); sessions = (Path(state) / 'sessions').resolve()
    if not path.is_relative_to(sessions) or path.suffix != '.jsonl' or not path.is_file():
        raise ProtocolError('Official rollout path escaped the existing sessions directory')
    if path.stat().st_size > 64 * 1024 * 1024:
        raise ProtocolError('Scoped rollout exceeds finite read limit')
    calls = {}; outputs = {}; meta_ok = False
    with path.open(encoding='utf-8') as stream:
        for line in stream:
            record = json.loads(line); payload = record.get('payload', {})
            if record.get('type') == 'session_meta':
                meta_ok = (payload.get('id') == thread['id']
                           and Path(payload.get('cwd', '')).resolve() == Path(workspace).resolve())
            if record.get('type') != 'response_item':
                continue
            if payload.get('internal_chat_message_metadata_passthrough', {}).get('turn_id') != turn['id']:
                continue
            kind = payload.get('type'); call_id = payload.get('call_id')
            if kind == 'custom_tool_call':
                if not call_id or call_id in calls or payload.get('name') != 'exec':
                    raise ProtocolError('Unknown/duplicate custom tool cannot prove scoped terminal calculation')
                calls[call_id] = payload
            elif kind == 'custom_tool_call_output':
                if not call_id or call_id in outputs or record.get('metadata', {}).get('client_authored') is not False:
                    raise ProtocolError('Custom tool output is duplicate or not server-authored')
                outputs[call_id] = payload
    if not meta_ok or not calls or set(calls) != set(outputs):
        raise ProtocolError('Rollout session mismatch or missing/refused/pending correlated tool output')
    receipts = []
    for call_id, call in calls.items():
        # An exact transparent wrapper avoids accepting text manufactured by exec JS.
        match = re.fullmatch(r'\s*const r = await tools\.exec_command\((\{.*\})\);\s*text\(r\);\s*',
                             call.get('input', ''), flags=re.DOTALL)
        if not match or call.get('status') != 'completed':
            raise ProtocolError('Custom exec did not use the required transparent terminal receipt wrapper')
        params = json.loads(match[1])
        if (set(params) - {'cmd', 'workdir', 'max_output_tokens'} or not isinstance(params.get('cmd'), str)
                or Path(params.get('workdir', '')).resolve() != Path(workspace).resolve()
                or params['cmd'] != terminal_command(workspace, sys.executable, task_id)):
            raise ProtocolError('Custom exec command/workspace scope differs')
        blocks = outputs[call_id].get('output')
        if not isinstance(blocks, list):
            raise ProtocolError('Custom tool output is not the observed official text-block protocol')
        values = []
        for block in blocks:
            if block.get('type') != 'input_text':
                continue
            try:
                value = json.loads(block.get('text', ''))
            except (ValueError, TypeError):
                continue
            if isinstance(value, dict) and 'exit_code' in value and 'output' in value:
                values.append(value)
        if len(values) != 1 or values[0].get('session_id') is not None:
            raise ProtocolError('Custom exec lacks one complete actual terminal receipt')
        result = values[0]
        receipts.append({'type': 'commandExecution', 'id': call_id, 'status': 'completed',
                         'exitCode': result['exit_code'], 'command': params['cmd'],
                         'aggregatedOutput': result['output'], 'evidence_kind': 'official_rollout_custom_exec',
                         'call_sha256': digest(canonical(call)),
                         'receipt_sha256': digest(canonical(outputs[call_id]))})
    return receipts


def verify_official(client, thread, turn, workspace, task_id=TASK_ID):
    items = turn.get('items', [])
    commands = [item for item in items if item.get('type') == 'commandExecution']
    if not commands:
        commands = raw_terminal_items(client, thread, turn, workspace, task_id)
    return verify(workspace, __import__('local_runner').output_items(items), commands, task_id), commands


def verify(workspace, output, items, task_id=TASK_ID):
    expected = byte_result(workspace, task_id)
    try:
        reported = parse_json(output)
    except (ValueError, TypeError, IndexError) as exc:
        raise ProtocolError('Work final output is not result JSON') from exc
    if (reported != expected or type(reported.get('verified_count')) is not int
            or type(reported.get('mismatches')) is not int):
        raise ProtocolError('Work semantic failure: final result differs from four independent source hashes')
    commands = [item for item in items if item.get('type') == 'commandExecution']
    if not commands:
        raise ProtocolError('No actual commandExecution: model-only result is not success')
    if any(item.get('status') != 'completed' or type(item.get('exitCode')) is not int
           or item['exitCode'] != 0 for item in commands):
        raise ProtocolError('Failed, refused, pending or unknown terminal execution')
    manifest = (Path(workspace).resolve() / 'service/PROVENANCE.json').as_posix()
    proofs = []
    for item in commands:
        command, stdout = item.get('command'), item.get('aggregatedOutput')
        if not isinstance(command, str) or not isinstance(stdout, str):
            continue
        # The prescribed computation must be visible in the official command item.
        normalized = command.replace('\\\\', '/').replace('\\', '/')
        if manifest not in normalized or 'hashlib.sha256' not in command or '.read_bytes()' not in command:
            continue
        try:
            actual_stdout = parse_json(stdout)
            if (actual_stdout != expected or type(actual_stdout.get('verified_count')) is not int
                    or type(actual_stdout.get('mismatches')) is not int):
                continue
        except (ValueError, TypeError, IndexError):
            continue
        proofs.append({'item_id': item.get('id'), 'command_sha256': digest(command),
                       'output_sha256': digest(stdout), 'exit_code': 0})
    if not proofs:
        raise ProtocolError('No successful byte calculation with matching actual terminal JSON output')
    return {'semantic_success': True, 'independent_files_verified': 4,
            'terminal_calculation_receipt_verified': True, 'commands': proofs,
            'result_sha256': digest(canonical(expected))}
