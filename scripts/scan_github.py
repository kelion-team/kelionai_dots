#!/usr/bin/env python3
"""Discover candidates sequentially. Discovery never grants functional approval."""
import argparse
import datetime as dt
import html
import fcntl
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUERIES = ['agent SWE-bench', 'agent GAIA', 'agent WebArena', 'agent OSWorld', 'agent tau-bench', 'agent AgentBench']
BENCHMARKS = ['SWE-bench', 'GAIA', 'WebArena', 'OSWorld', 'tau-bench', 'AgentBench', 'HumanEval', 'polyglot', 'agents_medium_benchmark']


def read_page(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'kelionai-dots-research/1.0'})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode('utf-8')


def payloads(page):
    for raw in re.findall(r'<script[^>]*type="application/json"[^>]*>(.*?)</script>', page, re.S):
        try:
            yield json.loads(raw).get('payload', {})
        except json.JSONDecodeError:
            continue


def persist(state, path):
    state['updated_at'] = dt.datetime.now(dt.timezone.utc).isoformat()
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(state, indent=2, ensure_ascii=False) + '\n')
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pages-per-query', type=int, default=1)
    parser.add_argument('--output', type=Path, default=ROOT / 'catalog' / 'scan.json')
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    lock = args.output.with_suffix('.lock').open('w')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    state = json.loads(args.output.read_text()) if args.output.exists() else {'coverage': {}, 'candidates': {}, 'accepted': []}
    for query in QUERIES:
        coverage = state['coverage'].setdefault(query, {'pages': [], 'complete': False})
        for number in range(1, args.pages_per_query + 1):
            if number in coverage['pages']:
                continue
            url = 'https://github.com/search?' + urllib.parse.urlencode({'q': query, 'type': 'repositories', 'p': number})
            try:
                data = next(p['blackbirdSearchRoute'] for p in payloads(read_page(url)) if 'blackbirdSearchRoute' in p)
            except (urllib.error.URLError, StopIteration) as error:
                coverage['blocker'] = str(error)
                persist(state, args.output)
                print(f'Discovery blocked for {query}: {error}', flush=True)
                break
            coverage['result_count'] = data['result_count']
            coverage['page_count'] = data['page_count']
            coverage['pages'].append(number)
            coverage['search_cap_reached'] = data['result_count'] >= 1000
            coverage['complete'] = len(coverage['pages']) >= data['page_count'] and not coverage['search_cap_reached']
            coverage.pop('blocker', None)
            for result in data['results']:
                repo = result['repo']['repository']
                name = repo['owner_login'] + '/' + repo['name']
                candidate = state['candidates'].setdefault(name, {'source': 'https://github.com/' + name, 'queries': [], 'status': 'discovered', 'functional_verified': False})
                if query not in candidate['queries']:
                    candidate['queries'].append(query)
            persist(state, args.output)
            time.sleep(1)
            if number >= data['page_count']:
                break
    for name, candidate in state['candidates'].items():
        if candidate.get('parser_version') == 2:
            continue
        try:
            data = next(p['codeViewRepoRoute'] for p in payloads(read_page(candidate['source'])) if 'codeViewRepoRoute' in p)
            candidate['commit'] = data['refInfo']['currentOid']
            candidate['branch'] = data['refInfo']['name']
            files = data.get('tree', {}).get('items', [])
            candidate['root_files'] = [item['name'] for item in files]
            rendered = data.get('overview', {}).get('overviewFiles', [])
            texts = [str(item.get('richText', '')) for item in rendered if str(item.get('displayName', item.get('path', ''))).lower().startswith('readme')]
            text = html.unescape(re.sub('<[^>]+>', ' ', '\n'.join(texts)))
            candidate['benchmark_mentions'] = [b for b in BENCHMARKS if b.lower() in text.lower()]
            candidate['measurement_excerpts'] = [re.sub(r'\s+', ' ', text[max(0, m.start()-120):m.end()+120]) for m in list(re.finditer(r'\d+(?:\.\d+)?\s*%', text))[:8]]
            candidate['test_paths'] = [p for p in candidate['root_files'] if p.lower() in ('test', 'tests', '__tests__', 'pytest.ini', 'tox.ini')]
            candidate['status'] = 'needs_runtime_validation'
            if not candidate['benchmark_mentions']:
                candidate['status'] = 'rejected_no_benchmark_evidence'
            candidate['checked_at'] = dt.datetime.now(dt.timezone.utc).isoformat()
            candidate['parser_version'] = 2
            print(name + ': ' + candidate['status'], flush=True)
        except (urllib.error.URLError, StopIteration, KeyError) as error:
            candidate['status'] = 'blocked_inspection'
            candidate['blocker'] = str(error)
            print(name + ': blocked_inspection', flush=True)
        persist(state, args.output)
        time.sleep(0.25)
    print(f"Inspected {len(state['candidates'])} candidates. Functional approval requires separate tests.")


if __name__ == '__main__':
    main()
