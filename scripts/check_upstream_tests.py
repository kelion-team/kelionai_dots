#!/usr/bin/env python3
"""Record current GitHub checks for benchmark candidates without approving import."""
import datetime as dt
import fcntl
import json

from scan_github import ROOT, persist
from scan_github_api import api


def main():
    output = ROOT / 'catalog/scan.json'
    lock = output.with_suffix('.lock').open('w')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    state = json.loads(output.read_text())
    for name, candidate in state['candidates'].items():
        if not candidate.get('commit') or not candidate.get('measurement_excerpts') or not candidate.get('test_paths') or candidate.get('upstream_checks_observed'):
            continue
        if candidate['status'] == 'rejected_checks_failed':
            continue
        try:
            checks = api(f'repos/{name}/commits/{candidate["commit"]}/check-runs?per_page=100')
            latest = {}
            for check in checks['check_runs']:
                key = (check['app']['slug'], check['name'])
                timestamp = check.get('completed_at') or check.get('started_at') or ''
                if key not in latest or timestamp > latest[key]['observed_run_timestamp']:
                    latest[key] = {'name': check['name'], 'status': check['status'], 'conclusion': check['conclusion'], 'url': check['html_url'], 'observed_run_timestamp': timestamp}
            candidate['upstream_checks'] = list(latest.values())
            candidate['upstream_check_count'] = checks['total_count']
            candidate['upstream_checks_page_truncated'] = checks['total_count'] > 100
            candidate['upstream_checks_observed'] = dt.datetime.now(dt.timezone.utc).isoformat()
            bad = [c for c in latest.values() if c['conclusion'] in ('failure', 'timed_out', 'cancelled', 'action_required', 'startup_failure')]
            candidate['known_upstream_check_errors'] = bool(bad)
            if bad:
                candidate['status'] = 'rejected_upstream_checks_failed'
            # Green CI is recorded evidence, never functional approval in this environment.
            print(name + ': ' + ('rejected failing checks' if bad else 'checks recorded; runtime still unverified'), flush=True)
        except RuntimeError as error:
            candidate['upstream_check_blocker'] = str(error)
            print(name + ': upstream checks unavailable', flush=True)
        persist(state, output)


if __name__ == '__main__':
    main()
