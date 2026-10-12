#!/usr/bin/env python3
"""Offline, fail-closed readback integrity gate for a Workspace Agent run.

It cannot authenticate the origin of an externally supplied record or itself
fetch ChatGPT responses. The caller must retrieve the output from a connected
source and independently validate who supplied the source record.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

TASK = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{3,127}$')
AGENT = re.compile(r'^agt_[A-Za-z0-9_-]+$')
RUN = re.compile(r'^apirun_[A-Za-z0-9_-]+$')
SHA = re.compile(r'^[a-f0-9]{64}$')


def digest(content):
    if not isinstance(content, (bytes, bytearray)):
        raise ValueError('Bytes required for content integrity check')
    return hashlib.sha256(content).hexdigest()


def _same(field, a, b):
    if a != b:
        raise ValueError('Mismatch: ' + field)


def evaluate(receipt, result, input_bytes, output_bytes, verifier):
    """Check associations/integrity, NOT independent source authenticity.

    result and verifier are records fetched from real connected sources by
    the caller; callers must preserve source URLs, authors, and tool receipts.
    """
    for val, rule, label in ((receipt.get('task_id'), TASK, 'task_id'),
                             (receipt.get('agent_id'), AGENT, 'agent_id')):
        if not isinstance(val, str) or not rule.fullmatch(val):
            raise ValueError('Missing or invalid ' + label)
    run_id = receipt.get('agent_trigger_run_id')
    if run_id is not None and (not isinstance(run_id, str) or not RUN.fullmatch(run_id)):
        raise ValueError('Invalid optional run_id')
    if receipt.get('status') not in ('run_completed_result_not_retrieved', 'trigger_accepted'):
        raise ValueError('No accepted/completed trigger receipt')
    if receipt.get('agent_run_status') != 'completed':
        raise ValueError('A confirmed completed run is required')
    for field in ('task_id', 'agent_id', 'agent_trigger_run_id'):
        _same(field, receipt.get(field), result.get(field))
    _same('task_id verifier', receipt['task_id'], verifier.get('task_id'))
    _same('agent_id verifier', receipt['agent_id'], verifier.get('agent_id'))
    _same('agent_trigger_run_id verifier', receipt['agent_trigger_run_id'], verifier.get('agent_trigger_run_id'))
    if not output_bytes:
        raise ValueError('No output retrieved')
    if len(output_bytes) > 10000000 or len(input_bytes) > 10000000:
        raise ValueError('Oversized artifact')
    actual_input = digest(input_bytes)
    actual_output = digest(output_bytes)
    for name, actual in (('input_sha256', actual_input), ('result_sha256', actual_output)):
        declared = result.get(name)
        if not isinstance(declared, str) or not SHA.fullmatch(declared):
            raise ValueError('Missing or invalid ' + name)
        _same(name, actual, declared)
    _same('verification input sha', actual_input, verifier.get('input_sha256'))
    _same('verification result sha', actual_output, verifier.get('result_sha256'))
    if result.get('result_ref') is None or not isinstance(result.get('result_ref'), str):
        raise ValueError('Missing result reference')
    if not result['result_ref'].startswith('https://'):
        raise ValueError('Untrusted result reference format')
    if not isinstance(verifier.get('verifier'), str) or not verifier['verifier'].strip():
        raise ValueError('Missing independent verifier ID')
    if verifier['verifier'] == receipt.get('agent_id'):
        raise ValueError('Verifier must not be the producing agent')
    if verifier.get('passed') is not True or not isinstance(verifier.get('evidence_ref'), str) or not verifier['evidence_ref'].startswith('https://'):
        raise ValueError('Independent verification evidence missing')
    return {
        'task_id': receipt['task_id'],
        'agent_id': receipt['agent_id'],
        'run_id': receipt['agent_trigger_run_id'],
        'integrity_checks_passed': True,
        'independent_verification_claim_present': True,
        'provenance_authenticated': False,
        'fully_verified': False,
        'status': 'integrity_passed_requires_authenticated_source_provenance',
        'input_sha256': actual_input,
        'result_sha256': actual_output,
        'result_ref': result['result_ref'],
        'verification_ref': verifier['evidence_ref'],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--receipt', required=True)
    parser.add_argument('--result', required=True)
    parser.add_argument('--input-file', required=True)
    parser.add_argument('--output-file', required=True)
    parser.add_argument('--verifier', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args(argv)
    try:
        data = evaluate(*[json.loads(Path(p).read_text(encoding='utf-8')) for p in (args.receipt, args.result)],
                        Path(args.input_file).read_bytes(), Path(args.output_file).read_bytes(),
                        json.loads(Path(args.verifier).read_text(encoding='utf-8')))
        dest = Path(args.out)
        if dest.exists():
            raise ValueError('Refusing to overwrite existing report')
        dest.write_text(json.dumps(data, indent=2, sort_keys=True) + '\n', encoding='utf-8')
        print(data['status'])
        return 0
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print('RESULT_GATE_ERROR: ' + str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
