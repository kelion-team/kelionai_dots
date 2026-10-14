#!/usr/bin/env bash
# Adaptor magistrală → Codex CLI (contul ChatGPT deja autentificat pe server, fără chei API).
# Folosit pentru suprafețele "chat" (model Astra) și "codex". Cererea vine pe stdin;
# modelul și raționamentul vin de la magistrală (KELION_MODEL, KELION_EFFORT).
# Răspunsul final al modelului se scrie pe stdout.
set -euo pipefail
: "${KELION_MODEL:?model lipsă în config}" "${KELION_EFFORT:?efort lipsă}"
CODEX="${CODEX_BIN:-codex}"
HOME_DIR="${CODEX_HOME:-$HOME/.codex}"
if ! "$CODEX" login status >/dev/null 2>&1; then
  echo "{\"status\":\"failed\",\"detail\":\"Codex nu este autentificat în CODEX_HOME=$HOME_DIR (utilizator $(id -un)). Setați codex_home în config la directorul în care s-a făcut login-ul.\"}"
  exit 0
fi
WORK=$(mktemp -d); trap 'rm -rf "$WORK"' EXIT
SANDBOX="read-only"; [ "${KELION_SURFACE:-}" = "codex" ] && SANDBOX="${KELION_CODEX_SANDBOX:-read-only}"
# Căutare pe internet (unealta web_search a Codex), pornită din config: "web_search": true.
SEARCH=(); [ "${KELION_WEB_SEARCH:-0}" = "1" ] && SEARCH=(-c "tools.web_search=true")
if ! "$CODEX" exec --skip-git-repo-check --sandbox "$SANDBOX" -C "$WORK" \
  -m "$KELION_MODEL" -c "model_reasoning_effort=\"$KELION_EFFORT\"" "${SEARCH[@]}" \
  --output-last-message "$WORK/last.txt" - < /dev/stdin > "$WORK/log.txt" 2>&1; then
  # Motivul real (ultimele rânduri din jurnalul Codex), ca JSON valid, ca să apară în monitor.
  python3 -c 'import json,sys; t=open(sys.argv[1],errors="replace").read()[-400:]; print(json.dumps({"status":"failed","detail":"Codex ("+sys.argv[2]+"): "+t.strip()}))' "$WORK/log.txt" "$KELION_MODEL"
  exit 0
fi
cat "$WORK/last.txt"
