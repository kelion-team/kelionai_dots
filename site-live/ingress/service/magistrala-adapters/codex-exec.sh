#!/usr/bin/env bash
# Adaptor magistrală → Codex CLI (contul ChatGPT deja autentificat pe server, fără chei API).
# Folosit pentru suprafețele "chat" (model Astra) și "codex". Cererea vine pe stdin;
# modelul și raționamentul vin de la magistrală (KELION_MODEL, KELION_EFFORT).
# Răspunsul final al modelului se scrie pe stdout.
set -euo pipefail
: "${KELION_MODEL:?model lipsă în config}" "${KELION_EFFORT:?efort lipsă}"
CODEX="${CODEX_BIN:-codex}"
WORK=$(mktemp -d); trap 'rm -rf "$WORK"' EXIT
SANDBOX="read-only"; [ "${KELION_SURFACE:-}" = "codex" ] && SANDBOX="${KELION_CODEX_SANDBOX:-read-only}"
"$CODEX" exec --skip-git-repo-check --sandbox "$SANDBOX" -C "$WORK" \
  -m "$KELION_MODEL" -c "model_reasoning_effort=\"$KELION_EFFORT\"" \
  --output-last-message "$WORK/last.txt" - < /dev/stdin > "$WORK/log.txt" 2>&1
cat "$WORK/last.txt"
