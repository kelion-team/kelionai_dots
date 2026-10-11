#!/usr/bin/env python3
"""Run the upstream coding agent with an existing OpenRouter binding."""
import argparse
import json
import os
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--task', required=True)
    parser.add_argument('--cwd', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    missing = [key for key in ['OPENROUTER_API_KEY', 'KELION_MODEL'] if not os.environ.get(key)]
    if missing:
        print('Missing environment bindings: ' + ', '.join(missing), file=sys.stderr)
        return 2
    from minisweagent.agents.default import DefaultAgent
    from minisweagent.config import get_config_from_spec
    from minisweagent.environments.local import LocalEnvironment
    from minisweagent.models.openrouter_model import OpenRouterModel

    args.cwd.mkdir(parents=True, exist_ok=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    model = OpenRouterModel(model_name=os.environ['KELION_MODEL'])
    config = get_config_from_spec('mini.yaml')['agent']
    config.update(step_limit=12, cost_limit=1.0, wall_time_limit_seconds=120, output_path=args.output)
    agent = DefaultAgent(model, LocalEnvironment(cwd=str(args.cwd.resolve())), **config)
    result = agent.run(args.task)
    print(json.dumps(result))
    return 0 if result.get('exit_status') == 'Submitted' else 1


if __name__ == '__main__':
    raise SystemExit(main())
