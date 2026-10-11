#!/usr/bin/env python3
"""Run installed upstream tests sequentially and save measured outcomes."""
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = Path(os.environ.get('KELION_RUNTIME_DIR', ROOT.parent / 'agent-runtime'))
TARGETS = {
    'mini-swe-agent': ('mini-swe', ['tests/agents/test_default.py', 'tests/environments/test_local.py', 'tests/models/test_test_models.py', 'tests/config/test_init.py']),
    'agentd': ('agentd', ['tests']),
}


def main():
    result_dir = RUNTIME / 'results'
    result_dir.mkdir(parents=True, exist_ok=True)
    results = {}
    for name, (venv, paths) in TARGETS.items():
        source = ROOT / 'vendor' / name
        commit = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
        report = result_dir / (name + '.xml')
        report.unlink(missing_ok=True)
        env = os.environ | {'XDG_CONFIG_HOME': str(RUNTIME / 'config'), 'XDG_CACHE_HOME': str(RUNTIME / 'cache')}
        command = [sys.executable, str(ROOT / 'scripts/run_tests.py'), str(RUNTIME / (venv + '-venv') / 'bin/python'), '-m', 'pytest', *paths, '-q', '--junitxml=' + str(report), '-o', 'cache_dir=' + str(RUNTIME / ('pytest-' + name))]
        started = time.monotonic()
        process = subprocess.run(command, cwd=source, env=env)
        summary = {'commit': commit, 'command': command, 'exit_code': process.returncode, 'elapsed_seconds': round(time.monotonic()-started, 3), 'checked_at': dt.datetime.now(dt.timezone.utc).isoformat(), 'live_model_verified': False}
        if report.exists():
            suites = list(ET.parse(report).getroot().iter('testsuite'))
            summary.update({key: sum(int(s.attrib[key]) for s in suites) for key in ('tests', 'failures', 'errors', 'skipped')})
            summary['passed'] = summary['tests']-summary['failures']-summary['errors']-summary['skipped']
        summary['tests_passed'] = process.returncode == 0 and summary.get('passed', 0) > 0
        summary['import_ready'] = False
        results[name] = summary
        (result_dir / 'validation.json').write_text(json.dumps(results, indent=2) + '\n')
    return int(any(not s['tests_passed'] for s in results.values()))


if __name__ == '__main__':
    raise SystemExit(main())
