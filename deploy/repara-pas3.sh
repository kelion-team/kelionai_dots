#!/usr/bin/env bash
# Pasul 3 (21.10.2026, cerința 8 din apel): orice număr WhatsApp primește răspuns; necunoscuții pe ruta IZOLATĂ de invitați.
# Rulat de Adrian ca root. Se aplică DOAR fără apel în curs (repornește kelion-pod); probă pe copie, backup, revenire.
set -uo pipefail
REF="${KELION_REF:-fix/locuri-asteptare-sunet}"
RAW="https://raw.githubusercontent.com/kelion-team/kelionai_dots/$REF/deploy"
POD=/opt/kelion-pod
J=/var/lib/kelion-pod/pod.jsonl
ts=$(date +%Y%m%d-%H%M%S)
tmp=$(mktemp -d)
[ "$(id -u)" = 0 ] || { echo "Rulează ca root."; exit 1; }
if ! curl -s -m 5 http://127.0.0.1:8095/sanatate | grep -q '"apel_in_curs": false'; then
  echo "OPRIT: e un apel în curs. Nimic schimbat. Rulează din nou după apel."; exit 1
fi
curl -fsSL "$RAW/repara_necunoscuti.py" -o "$tmp/r.py" || { echo "OPRIT: descărcare eșuată. Nimic schimbat."; exit 1; }
python3 -B "$tmp/r.py" "$POD" "$tmp/nou" || { echo "OPRIT: proba a picat. Nimic schimbat."; exit 1; }
bk="$POD/backup-$ts"; mkdir -p "$bk" && cp -a "$POD/kelion_pod.py" "$POD/apel_invitat.py" "$bk/"
install -m 644 "$tmp/nou/kelion_pod.py" "$POD/kelion_pod.py"
install -m 644 "$tmp/nou/apel_invitat.py" "$POD/apel_invitat.py"
rm -rf "$POD/__pycache__"
inainte=$(wc -l < "$J")
systemctl restart kelion-pod
sleep 25
if ! systemctl is-active -q kelion-pod || ! curl -s -m 5 http://127.0.0.1:8095/sanatate | grep -q '"ok": true'; then
  echo "EȘEC: revin la backup"; cp -a "$bk/kelion_pod.py" "$bk/apel_invitat.py" "$POD/"; systemctl restart kelion-pod; exit 1
fi
echo "--- dovezi:"
grep -c necunoscut_pe_ruta_invitat "$POD/kelion_pod.py" | sed 's/^/marcaje în cod: /'
tail -n +"$((inainte + 1))" "$J" | grep -E 'pornit|chrome_|loc_stare' | head -5 | cut -c1-200
curl -s -m 5 http://127.0.0.1:8095/sanatate | head -c 200; echo
echo "GATA. Backup: $bk. Probă: sună Kelion de pe un număr care NU e al tău și nu e în lista de invitați."
rm -rf "$tmp"
