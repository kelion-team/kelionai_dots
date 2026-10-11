#!/usr/bin/env bash
set -euo pipefail
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
runtime="${KELION_RUNTIME_DIR:-$(dirname "$repo")/agent-runtime}"
export UV_CACHE_DIR="$runtime/uv-cache"
mkdir -p "$runtime/logs" "$runtime/results" "$runtime/config" "$runtime/cache"
cd "$repo"
git submodule update --init --recursive
for agent in mini-swe agentd; do
  if [[ ! -x "$runtime/$agent-venv/bin/python" ]]; then
    uv venv "$runtime/$agent-venv"
  fi
done
uv --system-certs pip install --python "$runtime/mini-swe-venv/bin/python" \
  --default-index https://pypi.org/simple -c locks/mini-swe-agent.txt \
  ./vendor/mini-swe-agent pytest pytest-asyncio
uv --system-certs pip install --python "$runtime/agentd-venv/bin/python" \
  --default-index https://pypi.org/simple -c locks/agentd.txt './vendor/agentd[dev,api]'
