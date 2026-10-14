"""Prepare explicit native spawn arguments from Kelion's cost decision.

The parent orchestrator invokes its native tool; this module makes no API call.
No Workspace Agent identity, plugin attachment or runtime is impersonated.
"""
import argparse
import json
from pathlib import Path
from kelion_brain import _router


def plan(request, assessment, manifest, registry):
    role = next((r for r in registry['roles'] if r['role'] == request.get('role')), None)
    if role is None:
        raise ValueError('Unknown native DOTS role')
    if role.get('requires_logic_validation') and request.get('logic_validation_required') is not True:
        raise ValueError('This role is only allowed for necessary logic validation')
    if not isinstance(assessment, dict):
        raise ValueError('Native DOTS assessment required')
    for key, expected in [('task_id', request.get('task_id')),
                          ('source_agent_id', role['source_agent_id']),
                          ('task_input', request.get('task'))]:
        if not isinstance(expected, str) or not expected or assessment.get(key) != expected:
            raise ValueError('Assessment mismatch: ' + key)
    difficulty = assessment.get('difficulty')
    if type(difficulty) is not int or not 1 <= difficulty <= 4:
        raise ValueError('Invalid difficulty')
    if not isinstance(assessment.get('reason'), str) or not assessment['reason'].strip():
        raise ValueError('Assessment reason required')
    envelope = {'task': request['task'], 'surface': request.get('surface', 'work'),
                'min_tier': difficulty, 'risk_flags': assessment.get('risk_flags', [])}
    if envelope['surface'] not in ('work', 'codex'):
        raise ValueError('Native dispatch requires Work/Codex; plain Chat is not a native runtime')
    result = _router.route(envelope, manifest)
    if result['requires_action_approval']:
        raise ValueError('Action approval must be resolved separately')
    classified, why = _router.classify(envelope)
    # A lexical classifier's uncertain baseline must not override an explicit
    # DOTS assessment. Actual difficulty/risk indicators can raise it.
    tier = difficulty if classified == 2 and len(why) == 1 else max(difficulty, classified)
    model = _router.select_model(_router._validated_models(manifest), envelope['surface'], tier)
    if model is None:
        raise ValueError('blocked_no_verified_included_model')
    selected = next(m for m in manifest['models'] if m['id'] == model['id'] and m['surface'] == envelope['surface'])
    if selected.get('native_spawn_supported') is not True:
        raise ValueError('Selected model is not verified for native spawn')
    message = {'phase': 'work', 'task_id': request['task_id'], 'source_agent_id': role['source_agent_id'],
               'native_role': role['name'], 'task': request['task'], 'dots_assessment': assessment,
               'kelion_decision': model, 'role_description': role['description'],
               'source_scope': role.get('scope'), 'use_guard': role.get('guard'),
               'developer_instructions': role.get('developer_instructions'),
               'skill_migration_verified': role.get('skill_migration_verified', False)}
    return {'status': 'native_spawn_prepared', 'decision_by': 'Kelion',
            'policy_tier': tier,
            'spawn_request': {'task_name': role['name'], 'fork_turns': 'none',
                              'model': model['id'], 'reasoning_effort': model['reasoning'],
                              'message': json.dumps(message, ensure_ascii=False)},
            'cost_rank_type': model['cost_rank_type'], 'dispatch_performed': False,
            'settings_changed': False, 'measured_credit_cost': None}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    for name in ('request', 'assessment', 'manifest'):
        parser.add_argument('--' + name, required=True, type=Path)
    args = parser.parse_args()
    registry = json.loads(Path(__file__).with_name('native_roles.json').read_text())
    try:
        print(json.dumps(plan(*[json.loads(getattr(args, k).read_text()) for k in
                              ('request', 'assessment', 'manifest')], registry), ensure_ascii=False, indent=2))
    except (ValueError, KeyError, TypeError) as error:
        parser.exit(2, str(error) + '\n')
