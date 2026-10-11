#!/usr/bin/env python3
"""Export a source package only after all recorded required checks pass."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('agent_id')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    catalog = ROOT / 'catalog/import-ready.json'
    if not catalog.exists():
        print('Export refused: no approval catalog exists.', file=sys.stderr)
        return 2
    approved = json.loads(catalog.read_text())
    entries = [agent for agent in approved if agent['id'] == args.agent_id]
    if not entries:
        print('Export refused: agent has no complete successful verification record.', file=sys.stderr)
        return 2
    agent = entries[0]
    if not agent.get('import_ready') or not agent.get('live_model_verified') or agent.get('passed', 0) <= 0 or any(agent.get(k, 1) != 0 for k in ('failures', 'errors', 'skipped')):
        print('Export refused: incomplete or failed checks.', file=sys.stderr)
        return 2
    source = ROOT / agent['source_path']
    actual = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    if actual != agent['commit']:
        print('Export refused: source revision differs from tested revision.', file=sys.stderr)
        return 2
    if subprocess.check_output(['git', '-C', str(source), 'status', '--porcelain'], text=True).strip():
        print('Export refused: source has local modifications.', file=sys.stderr)
        return 2
    archive = subprocess.check_output(['git', '-C', str(source), 'archive', 'HEAD'])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.output, 'w', zipfile.ZIP_DEFLATED) as output:
        output.writestr('agent.json', json.dumps(agent, indent=2))
        with tarfile.open(fileobj=io.BytesIO(archive)) as files:
            for member in files:
                if member.isfile():
                    output.writestr('source/' + member.name, files.extractfile(member).read())
    print(hashlib.sha256(args.output.read_bytes()).hexdigest() + '  ' + str(args.output))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
