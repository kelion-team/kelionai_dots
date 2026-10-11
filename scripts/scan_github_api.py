#!/usr/bin/env python3
"""Paginated authenticated GitHub discovery, then sequential README inspection."""
import base64
import datetime as dt
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import time
import urllib.parse

from scan_github import BENCHMARKS, QUERIES, ROOT, persist

try:
    import requests
except ModuleNotFoundError:
    requests = None

SESSION = requests.Session() if requests else None
if SESSION is not None:
    SESSION.headers['Accept'] = 'application/vnd.github+json'
    SESSION.headers['User-Agent'] = 'kelionai-dots-research/1.0'
    if os.environ.get('GH_TOKEN'):
        SESSION.headers['Authorization'] = 'Bearer ' + os.environ['GH_TOKEN']


def api(endpoint):
    if SESSION is not None:
        try:
            response = SESSION.get('https://api.github.com/' + endpoint, timeout=30)
        except requests.RequestException as error:
            raise RuntimeError(str(error)) from error
        if response.status_code != 200:
            try:
                detail = response.json().get('message', 'request failed')
            except ValueError:
                detail = 'non-JSON error response'
            raise RuntimeError(f'GitHub API HTTP {response.status_code}: {detail}')
        try:
            return response.json()
        except ValueError as error:
            raise RuntimeError('GitHub returned an invalid JSON response') from error
    result = subprocess.run(['gh', 'api', endpoint], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stderr.strip())
    return json.loads(result.stdout)


def main():
    output = ROOT / 'catalog/scan.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    lock = output.with_suffix('.lock').open('w')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    state = json.loads(output.read_text()) if output.exists() else {'coverage': {}, 'candidates': {}, 'accepted': []}
    coverage = state.setdefault('api_coverage', {})
    for query in QUERIES:
        record = coverage.setdefault(query, {'pages': [], 'complete': False, 'per_page': 100})
        page = 1
        while page <= 10:
            if page in record['pages']:
                page += 1
                continue
            try:
                params = urllib.parse.urlencode({'q': query, 'per_page': 100, 'page': page})
                data = api('search/repositories?' + params)
            except RuntimeError as error:
                record['blocker'] = str(error)
                print(f'{query}: blocked discovery', flush=True)
                persist(state, output)
                break
            record['total_count'] = data['total_count']
            record['incomplete_results'] = data['incomplete_results']
            record['pages'].append(page)
            record['complete'] = page*100 >= data['total_count'] and not data['incomplete_results'] and data['total_count'] <= 1000
            record['search_cap_reached'] = data['total_count'] > 1000
            record.pop('blocker', None)
            for repo in data['items']:
                name = repo['full_name']
                item = state['candidates'].setdefault(name, {'source': repo['html_url'], 'queries': [], 'status': 'discovered', 'functional_verified': False})
                if query not in item['queries']:
                    item['queries'].append(query)
                item.update(archived=repo['archived'], fork=repo['fork'], branch=repo['default_branch'], size_kib=repo['size'])
            persist(state, output)
            print(f'{query}: page {page}, candidates={len(state["candidates"])}', flush=True)
            if page*100 >= data['total_count']:
                break
            page += 1
            time.sleep(2.1)
    for name, item in state['candidates'].items():
        if item.get('parser_version') == 2 or item.get('api_inspected') or item.get('status') in ['rejected_checks_failed', 'pending_live_model_validation', 'pending_live_model_and_skipped_checks']:
            continue
        if item.get('archived') or item.get('size_kib') == 0:
            item['status'] = 'excluded_archived_or_empty'
            item['api_inspected'] = True
            persist(state, output)
            continue
        try:
            readme = api(f'repos/{name}/readme')
            if readme.get('encoding') != 'base64' or not readme.get('content'):
                raise RuntimeError('README content unavailable through this API response')
            text = base64.b64decode(readme['content']).decode('utf-8', errors='replace')
            item['readme_url'] = readme['html_url']
            item['readme_blob_sha'] = readme['sha']
            item['benchmark_mentions'] = [b for b in BENCHMARKS if b.lower() in text.lower()]
            item['measurement_excerpts'] = [re.sub(r'\s+', ' ', text[max(0,m.start()-120):m.end()+120]) for m in list(re.finditer(r'\d+(?:\.\d+)?\s*%', text))[:8]]
            item['status'] = 'needs_runtime_validation' if item['benchmark_mentions'] else 'rejected_no_benchmark_evidence'
            if item['benchmark_mentions'] and item['measurement_excerpts']:
                ref = urllib.parse.quote(item['branch'], safe='')
                item['commit'] = api(f'repos/{name}/commits/{ref}')['sha']
                files = api(f'repos/{name}/contents?ref=' + item['commit'])
                item['root_files'] = [f['name'] for f in files]
                item['test_paths'] = [f for f in item['root_files'] if f.lower() in ('test','tests','__tests__','pytest.ini','tox.ini')]
            item['api_inspected'] = True
            item['checked_at'] = dt.datetime.now(dt.timezone.utc).isoformat()
            print(name + ': ' + item['status'], flush=True)
        except RuntimeError as error:
            item['status'] = 'blocked_inspection'
            item['blocker'] = str(error)
            if 'HTTP 404' in str(error):
                item['api_inspected'] = True
            print(name + ': blocked_inspection', flush=True)
        persist(state, output)
    print('Sequential discovery and inspection completed; this is not functional approval.', flush=True)


if __name__ == '__main__':
    main()
