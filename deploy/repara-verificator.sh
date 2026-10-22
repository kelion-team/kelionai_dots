#!/usr/bin/env bash
# S7 + S14 (22.10.2026): verificatorul site-ului nu mai raportează defecte false (/app/cont, kitul Linux retras).
# Rulat ca root de Kelion (admin pe server) sau de Adrian. Nu repornește niciun serviciu (scriptul rulează la fiecare verificare).
set -uo pipefail
echec() { echo "OPRIT: $*" >&2; exit 1; }
REF="${KELION_REF:-}"
[[ "$REF" =~ ^[0-9a-f]{40}$ ]] || { echo "OPRIT: setează KELION_REF=<commit complet, 40 hex>. Nimic schimbat." >&2; exit 1; }
RAW="https://raw.githubusercontent.com/kelion-team/kelionai_dots/$REF/deploy"
DIR=/opt/kelion-brain
ts=$(date +%Y%m%d-%H%M%S)
[ "$(id -u)" = 0 ] || echec "rulează ca root."
tmp=$(mktemp -d) && [ -d "$tmp" ] || echec "director temporar; nimic schimbat."
trap 'rm -rf "$tmp"' EXIT
curl -fsSL "$RAW/repara_verificator.py" -o "$tmp/r.py" || echec "descărcare eșuată. Nimic schimbat."
python3 -B "$tmp/r.py" "$DIR" "$tmp/nou" || echec "proba a picat. Nimic schimbat."
cp -a "$DIR/verifica-site.py" "$DIR/verifica-site.py.backup-$ts" || echec "backup eșuat."
install -o brain -g brain -m 644 "$tmp/nou/verifica-site.py" "$DIR/verifica-site.py" || echec "instalare eșuată. Backup: $DIR/verifica-site.py.backup-$ts"
python3 -m py_compile "$DIR/verifica-site.py" || { cp -a "$DIR/verifica-site.py.backup-$ts" "$DIR/verifica-site.py"; echec "compilare eșuată; revenit la backup."; }
echo "dovadă: $(grep -c PORTAL_PREFIX "$DIR/verifica-site.py") marcaje; backup $DIR/verifica-site.py.backup-$ts"
echo "GATA. La următoarea verificare (max 10 min): S7 «nu se aplica: kitul Linux retras», S14 fără cele 2 legături /app/cont."
