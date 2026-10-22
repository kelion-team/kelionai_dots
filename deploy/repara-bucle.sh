#!/usr/bin/env bash
# R5/R32/S8 (22.10.2026): verificatorul și testerul nu mai pun la fiecare rulare o sarcină nouă pentru același defect.
# Rulat ca root de Kelion (admin pe server) sau de Adrian. Fără repornire de servicii (scripturile rulează la fiecare verificare).
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
curl -fsSL "$RAW/repara_bucle_remediere.py" -o "$tmp/r.py" || echec "descărcare eșuată. Nimic schimbat."
python3 -B "$tmp/r.py" "$DIR" "$tmp/nou" || echec "proba a picat. Nimic schimbat."
bk="$DIR/backup-bucle-$ts"; mkdir -p "$bk" && cp -a "$DIR/verifica-site.py" "$DIR/tester-ui.py" "$bk/" || echec "backup eșuat."
for f in verifica-site.py tester-ui.py; do
  install -o brain -g brain -m 644 "$tmp/nou/$f" "$DIR/$f" || { cp -a "$bk/"* "$DIR/"; echec "instalare $f eșuată; revenit la backup."; }
done
inainte=$(find "$DIR/work/coada" -name '*.json' -mmin -1440 | xargs grep -l '"stare": "blocata"' 2>/dev/null | wc -l)
echo "dovadă: $(grep -c 'cheie fără cifre' "$DIR/verifica-site.py") + $(grep -c 'stare_rep = OUT' "$DIR/tester-ui.py") marcaje; backup $bk"
echo "sarcini blocate în ultimele 24 h acum: $inainte (scad pe măsură ce ies din fereastră; noi nu ar trebui să mai apară pentru aceleași defecte)"
echo "GATA."
