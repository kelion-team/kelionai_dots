#!/usr/bin/env python3
"""Summarize search coverage and unverified candidates without promoting them."""
import collections
import json

from scan_github import ROOT


def main():
    scan = json.loads((ROOT / 'catalog/scan.json').read_text())
    candidates = scan['candidates']
    counts = collections.Counter(c['status'] for c in candidates.values())
    inspected = sum(bool(c.get('api_inspected')) or c.get('parser_version') == 2 or bool(c.get('manual_inspection')) for c in candidates.values())
    lines = ['# Raportul scanării', '', f'Proiecte identificate: **{len(candidates)}**. Inspecții de metadate efectuate: **{inspected}**.', '', 'Inspecția README și verificările CI nu reprezintă validare funcțională locală. Catalogul de import este separat și exclude orice verificare eșuată sau incompletă.', '', '| Căutare | Rezultate raportate | Pagini API citite | Paginare completă |', '| --- | ---: | ---: | --- |']
    for query, coverage in scan.get('api_coverage', {}).items():
        lines.append(f'| {query} | {coverage.get("total_count", "necunoscut")} | {len(coverage["pages"])} | {"Da" if coverage["complete"] else "Nu"} |')
    lines += ['', 'Acoperirea este limitată la termenii de căutare și proiectele accesibile/indexate de GitHub. Nu este inventarul tuturor agenților existenți.', '', '| Stare | Proiecte |', '| --- | ---: |']
    for status, count in sorted(counts.items()):
        lines.append(f'| {status} | {count} |')
    queue = []
    for name, candidate in candidates.items():
        if candidate.get('benchmark_mentions') and candidate.get('measurement_excerpts') and candidate.get('test_paths') and not candidate.get('known_upstream_check_errors') and not candidate['status'].startswith('rejected'):
            queue.append({'repository': name, 'commit': candidate['commit'], 'source': candidate['source'], 'possible_measurement_evidence': candidate['measurement_excerpts'], 'tests_to_inspect': candidate['test_paths'], 'status': candidate['status'], 'functional_verified': False, 'import_ready': False})
    lines += ['', f'Coada pentru verificări ulterioare: **{len(queue)}** candidați. Niciun candidat nu devine aprobat doar prin intrarea în coadă.', '']
    (ROOT / 'catalog/report.md').write_text('\n'.join(lines))
    (ROOT / 'catalog/review-queue.json').write_text(json.dumps(queue, indent=2, ensure_ascii=False) + '\n')
    print(f'{len(candidates)} discovered; {inspected} metadata inspections; {len(queue)} unapproved candidates queued')


if __name__ == '__main__':
    main()
