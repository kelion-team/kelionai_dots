#!/usr/bin/env bash
# R17/R20/R33/A12 (22.10.2026): registrul verifică funcțiile acolo unde sunt acum; procedura-nou.md intră în fiecare lucrare.
# Rulat ca root de Kelion (admin pe server) sau de Adrian. Fără repornire: coada-lucru.py e citit din nou la următoarea pornire
# a supraveghetorului cozii (și de verificator la fiecare rulare).
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
curl -fsSL "$RAW/repara_registru_procedura.py" -o "$tmp/r.py" || echec "descărcare eșuată. Nimic schimbat."
python3 -B "$tmp/r.py" "$DIR" "$tmp/nou" || echec "proba a picat. Nimic schimbat."
bk="$DIR/backup-registru-$ts"; mkdir -p "$bk" && cp -a "$DIR/coada-lucru.py" "$DIR/cerinte/registru-zi.json" "$bk/" || echec "backup eșuat."
install -o brain -g brain -m 644 "$tmp/nou/coada-lucru.py" "$DIR/coada-lucru.py" || { cp -a "$bk/coada-lucru.py" "$DIR/"; echec "instalare eșuată; revenit."; }
install -o brain -g brain -m 644 "$tmp/nou/cerinte/registru-zi.json" "$DIR/cerinte/registru-zi.json" || { cp -a "$bk/coada-lucru.py" "$DIR/"; cp -a "$bk/registru-zi.json" "$DIR/cerinte/"; echec "instalare eșuată; revenit."; }
python3 -m py_compile "$DIR/coada-lucru.py" || { cp -a "$bk/coada-lucru.py" "$DIR/"; cp -a "$bk/registru-zi.json" "$DIR/cerinte/"; echec "compilare eșuată; revenit."; }
echo "dovadă: $(grep -c 'A12 (22.10)' "$DIR/coada-lucru.py") marcaj în coada-lucru.py; registru actualizat; backup $bk"
echo "GATA. La următoarea verificare (max 10 min) R17, R20, R33, A4, A12 sunt verificate în fișierele corecte."
