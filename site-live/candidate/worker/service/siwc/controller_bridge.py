"""Invoke original, hash-pinned pure controller functions; no provider or database."""
import hashlib
import json
from pathlib import Path
import sys

SERVICE = Path(__file__).resolve().parents[1]
PINNED = {
    'core/orchestration/native_dispatch.py': '449ff958bf10c14bec95151d3a0e2447f2c2695c82fcbcb0ce148653f28db14d',
    'core/orchestration/kelion_brain.py': '15ce041c9e4aa835f9a6e9032e46c7a86e27edfe24a22a1a01ed955d45cdecc6',
    'core/orchestration/native_roles.json': 'c9c5ec7f3f3f4f816b0e0620f2dc115740ee068a97e1806cc9c8c355b3e53109',
    'core/skills/kelion-cost-guardian/scripts/route.py': '5e8a729dbc0bf6c4254a6d7879a6469b3075df732b4bc9c780b2c85a28cabb7b',
}


def execute(message):
    for name, expected in PINNED.items():
        if hashlib.sha256((SERVICE / name).read_bytes()).hexdigest() != expected:
            raise ValueError('original_controller_integrity_mismatch')
    sys.path.insert(0, str(SERVICE / 'core/orchestration'))
    from native_dispatch import plan
    from kelion_brain import _router
    registry = json.loads((SERVICE / 'core/orchestration/native_roles.json').read_text(encoding='utf-8'))
    action = message['action']
    if action == 'registry':
        return {'registry': registry, 'source_sha256': PINNED}
    if action == 'bootstrap':
        result = _router.route({'task': message['task'], 'surface': 'codex', 'min_tier': 1, 'risk_flags': []}, message['manifest'])
        if result['status'] != 'plan_only' or result['requires_action_approval']:
            raise ValueError('bootstrap_controller_blocked')
        return result
    if action == 'plan':
        # Preserve approval flags: never remove risk flags or bypass original plan.
        assessment = message['assessment']
        route = _router.route({'task': message['request']['task'], 'surface': 'codex', 'min_tier': assessment['difficulty'], 'risk_flags': assessment['risk_flags']}, message['manifest'])
        if route['requires_action_approval']:
            return {'status': 'blocked_action_approval', 'route': route, 'requires_action_approval': True}
        return plan(message['request'], assessment, message['manifest'], registry)
    raise ValueError('unsupported_controller_operation')


if __name__ == '__main__':
    try:
        raw = sys.stdin.buffer.read(1200001)
        if len(raw) > 1200000:
            raise ValueError('oversized_controller_input')
        result = execute(json.loads(raw))
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    except Exception:
        print(json.dumps({'error': 'controller_rejected'}))
        raise SystemExit(2)
