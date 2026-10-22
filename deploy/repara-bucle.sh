#!/usr/bin/env bash
# R5/R32/S8 + R12/A19 (22.10.2026): verificatorul și testerul nu mai pun la fiecare rulare o sarcină nouă pentru același defect;
# testerul local primește diagnosticul corect al lui Kelion (#70): nu mai raportează ca defect LIVE ruta portalului lipsă din adaptor.
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
curl -fsSL "https://raw.githubusercontent.com/kelion-team/kelionai_dots/$REF/scripts/legacy-tester-audit/prepare.py" -o "$tmp/diag.py" || echec "descărcare eșuată. Nimic schimbat."
mkdir -p "$tmp/live" && cp -a "$DIR/verifica-site.py" "$DIR/tester-ui.py" "$tmp/live/" || echec "copie eșuată. Nimic schimbat."
# 1) Diagnosticul corect al lui Kelion (#70): testerul local nu mai cere reparații LIVE pentru ruta portalului lipsă din adaptor.
if grep -q 'live_acceptance' "$tmp/live/tester-ui.py"; then
  echo "diagnosticul testerului (#70) e deja aplicat"
elif python3 -B "$tmp/diag.py" --source "$tmp/live/tester-ui.py" --output "$tmp/diag.patch"; then
  patch -s "$tmp/live/tester-ui.py" < "$tmp/diag.patch" || echec "patch-ul de diagnostic nu s-a aplicat pe copie. Nimic schimbat."
  python3 -m py_compile "$tmp/live/tester-ui.py" || echec "copia testerului nu compilează după diagnostic. Nimic schimbat."
  echo "diagnosticul testerului (#70) aplicat pe copie"
else
  echo "ATENȚIE: testerul live diferă de sursa revizuită în #70; diagnosticul NU se aplică (doar reparația buclei)."
fi
# 2) Bucla: fără sarcini repetate pentru același defect.
python3 -B "$tmp/r.py" "$tmp/live" "$tmp/nou" || echec "proba a picat. Nimic schimbat."
bk="$DIR/backup-bucle-$ts"; mkdir -p "$bk" && cp -a "$DIR/verifica-site.py" "$DIR/tester-ui.py" "$bk/" || echec "backup eșuat."
for f in verifica-site.py tester-ui.py; do
  install -o brain -g brain -m 644 "$tmp/nou/$f" "$DIR/$f" || { cp -a "$bk/"* "$DIR/"; echec "instalare $f eșuată; revenit la backup."; }
done
inainte=$(find "$DIR/work/coada" -name '*.json' -mmin -1440 | xargs grep -l '"stare": "blocata"' 2>/dev/null | wc -l)
echo "dovadă: $(grep -c 'cheie fără cifre' "$DIR/verifica-site.py") + $(grep -c 'stare_rep = OUT' "$DIR/tester-ui.py") marcaje; backup $bk"
echo "sarcini blocate în ultimele 24 h acum: $inainte (scad pe măsură ce ies din fereastră; noi nu ar trebui să mai apară pentru aceleași defecte)"
echo "GATA."
