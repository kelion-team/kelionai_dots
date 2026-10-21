"""Read-only projection of issue #48 KC comments; no execution or identity grants.

GitHub is the durable history. Supply all pages and retain comment URLs. Header
roles are claims, not authenticated agent identities (historically one GitHub
account authored both sides). This module never treats 'done' as verification.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

TOKEN = r'[A-Za-z0-9_.:-]{1,160}'
HEADER = re.compile(r'\[KC\] id=(?P<id>'+TOKEN+r') from=(?P<sender>claude|kelion|openai)'
                    r' to=(?P<recipient>claude|kelion|openai) task=(?P<task>'+TOKEN+r')'
                    r' type=(?P<kind>msg|ack|reply|done) ref=(?P<ref>'+TOKEN+r')')


def project(comments):
    records, conflicts, warnings = {}, set(), []
    for comment in comments:
        body = comment.get('body', '')
        if not isinstance(body, str) or not body.startswith('[KC]'):
            continue
        match = HEADER.fullmatch(body.split('\n', 1)[0].rstrip('\r'))
        if not match:
            warnings.append({'comment': comment.get('id'), 'reason': 'invalid_header'})
            continue
        record = match.groupdict()
        mid = record['id']
        digest = hashlib.sha256(body.encode()).hexdigest()
        if mid in records:
            if records[mid]['sha256'] != digest:
                conflicts.add(mid)
            continue
        record.update(sha256=digest, comment_url=comment.get('url'),
                      github_author=(comment.get('user') or {}).get('login'),
                      body=body, provenance_authenticated=False)
        records[mid] = record
    messages = {mid: dict(id=mid, task=r['task'], sender=r['sender'],
                         recipient=r['recipient'], status='unacknowledged',
                         acknowledgements=[], replies=[], done_claims=[],
                         verified=False, comment_url=r['comment_url'])
                for mid, r in records.items() if r['kind'] == 'msg'}
    # Resolve references in a second pass: GitHub pagination/order is irrelevant.
    for mid, r in records.items():
        if mid in conflicts:
            warnings.append({'id': mid, 'reason': 'id_content_conflict'})
            continue
        if r['kind'] == 'msg':
            continue
        parent = records.get(r['ref'])
        if parent is None or r['ref'] in conflicts:
            warnings.append({'id': mid, 'reason': 'unknown_or_conflicting_reference'})
            continue
        if (r['task'] != parent['task'] or r['sender'] != parent['recipient']
                or r['recipient'] != parent['sender']):
            warnings.append({'id': mid, 'reason': 'reference_task_or_direction_mismatch'})
            continue
        # ACK of a reply is not ACK of the original message. Preserve it in history.
        target = messages.get(r['ref'])
        if target is None:
            continue
        field = {'ack': 'acknowledgements', 'reply': 'replies', 'done': 'done_claims'}[r['kind']]
        target[field].append(mid)
    for mid, message in messages.items():
        if mid in conflicts:
            message['status'] = 'blocked_id_conflict'
        elif message['done_claims'] or message['replies']:
            message['status'] = 'result_claim_requires_readback'
        elif message['acknowledgements']:
            message['status'] = 'acknowledged_awaiting_result'
        if message['recipient'] == 'claude':
            message['migration'] = 'legacy_recipient_no_automatic_openai_alias'
    return {'messages': list(messages.values()), 'warnings': warnings,
            'fully_verified': False, 'execution_started': False,
            'note': 'Header roles do not authenticate agents; no automatic resend or dispatch.'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('snapshot', help='JSON list of all issue comments from authorized read')
    args = p.parse_args()
    snapshot = json.loads(Path(args.snapshot).read_text())
    print(json.dumps(project(snapshot), indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
