#!/usr/bin/env bash
# Rutina Kelion: exporta codul site-ului kelionai.app si diagnosticul serverului,
# FARA secrete, intr-un director gata de urcat in GitHub (ramura site/ingress-v2).
# Ruleaza pe serverul kelion-nou. Nu modifica nimic in /opt; doar citeste si copiaza.
#
# Utilizare:  bash export_site_snapshot.sh [/opt/kelion-app/ingress-v2] [/tmp/kelion-site-export]
set -euo pipefail

SRC="${1:-/opt/kelion-app/ingress-v2}"
OUT="${2:-/tmp/kelion-site-export}"

if [[ ! -d "$SRC" ]]; then
  echo "EROARE: nu exista $SRC" >&2
  exit 1
fi

rm -rf "$OUT"
mkdir -p "$OUT/site" "$OUT/diagnostic"

# 1) Copiaza codul, excluzand secretele, dependintele si datele utilizatorilor.
#    Se copiaza versiunea activa (current) daca exista, altfel radacina.
CODE="$SRC"
[[ -e "$SRC/current" ]] && CODE="$(readlink -f "$SRC/current")"

tar -C "$CODE" -cf - \
  --exclude='.env' --exclude='.env.*' --exclude='*.env' \
  --exclude='*.pem' --exclude='*.key' --exclude='id_*' --exclude='*secret*' --exclude='*credential*' \
  --exclude='node_modules' --exclude='.git' --exclude='./data' --exclude='*.db' --exclude='*.sqlite*' \
  --exclude='./logs' --exclude='*.log' --exclude='./releases' \
  . | tar -C "$OUT/site" -xf -

# Lista de variabile de configurare cerute (DOAR numele, fara valori).
for f in "$CODE/.env" "$SRC/.env" "$CODE/.env.example"; do
  [[ -f "$f" ]] && sed -E 's/=.*$/=<ascuns>/' "$f" > "$OUT/diagnostic/env-chei-$(basename "$(dirname "$f")").txt" || true
done

# 2) Diagnostic fara secrete.
{
  echo "# Diagnostic kelion-nou — $(date -u +%FT%TZ)"
  echo "## Release activ";       readlink -f "$SRC/current" 2>/dev/null || echo "(fara symlink current)"
  echo "## Release-uri";          ls -1 "$SRC/releases" 2>/dev/null || true
  echo "## Servicii kelion";      systemctl list-units --all --no-pager 2>/dev/null | grep -i kelion || true
  echo "## Porturi ascultate";    ss -ltnp 2>/dev/null | grep -Ei 'node|python|kelion' || true
  echo "## /api/config local";    curl -s --max-time 5 http://127.0.0.1/api/config 2>/dev/null || true
  echo; echo "## Versiuni";       node -v 2>/dev/null || true; python3 -V 2>/dev/null || true
} > "$OUT/diagnostic/stare.md"

# Ultimele linii din jurnalele de preflight (fara environ).
for f in /opt/kelion-siwc/preflight-*/final-preflight.stderr; do
  [[ -f "$f" ]] && tail -n 200 "$f" > "$OUT/diagnostic/$(basename "$(dirname "$f")")-final-preflight.stderr.txt"
done

# 3) Plasa de siguranta: daca apare ceva ce seamana cu un secret, oprire.
if grep -RInE '(sk-[A-Za-z0-9_-]{20,}|sk-ant-|sk-or-v1-|github_pat_|ghp_[A-Za-z0-9]{20,}|GOCSPX-|BEGIN [A-Z ]*PRIVATE KEY|AIza[0-9A-Za-z_-]{30,})' "$OUT" >/dev/null; then
  echo "OPRIT: exportul contine ce pare a fi un secret. Nu urca nimic. Fisiere:" >&2
  grep -RIlE '(sk-[A-Za-z0-9_-]{20,}|sk-ant-|sk-or-v1-|github_pat_|ghp_[A-Za-z0-9]{20,}|GOCSPX-|BEGIN [A-Z ]*PRIVATE KEY|AIza[0-9A-Za-z_-]{30,})' "$OUT" >&2
  exit 3
fi

echo "OK: export gata in $OUT ($(find "$OUT" -type f | wc -l) fisiere)."
echo "Urmatorul pas: urca continutul lui $OUT in kelion-team/kelionai_dots, ramura site/ingress-v2, folder site-live/."
