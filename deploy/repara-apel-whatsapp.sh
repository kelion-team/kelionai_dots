#!/usr/bin/env bash
# Reparațiile apelului WhatsApp (21.10.2026) pe serverul Contabo — rulat de Adrian, ca root, o singură comandă.
# Nu face nimic dacă e un apel în curs. Face backup, aplică, repornește, arată dovezile; dacă podul nu pornește, revine singur.
set -uo pipefail
REF="${KELION_REF:-}"
# Commit fix obligatoriu (40 hex), același cu cel din URL-ul scriptului: fără ramuri care se pot schimba între revizuire și rulare.
[[ "$REF" =~ ^[0-9a-f]{40}$ ]] || { echo "OPRIT: setează KELION_REF=<commit complet, 40 hex>. Nimic schimbat."; exit 1; }
POD=/opt/kelion-pod
J=/var/lib/kelion-pod/pod.jsonl
URL="https://raw.githubusercontent.com/kelion-team/kelionai_dots/$REF/deploy/repara_pod.py"
ts=$(date +%Y%m%d-%H%M%S)
pas() { echo; echo "== $*"; }

[ "$(id -u)" = 0 ] || { echo "Rulează ca root."; exit 1; }

pas "1/5 Niciun apel în curs?"
sanatate=$(curl -s -m 5 http://127.0.0.1:8095/sanatate || true)
if ! grep -q '"apel_in_curs": false' <<<"$sanatate"; then
  echo "OPRIT: e un apel în curs sau podul nu răspunde. Nu am schimbat nimic. Rulează din nou după apel."
  exit 1
fi
echo "da, liber"

pas "2/5 Reparațiile pe o copie + proba de comportament"
tmp=$(mktemp -d)
curl -fsSL "$URL" -o "$tmp/repara_pod.py" || { echo "OPRIT: nu am putut descărca $URL. Nimic schimbat."; exit 1; }
python3 -B "$tmp/repara_pod.py" "$POD" "$tmp/nou" || { echo "OPRIT: proba a picat. Nimic schimbat."; exit 1; }

pas "3/5 Backup"
bk="$POD/backup-$ts"
mkdir -p "$bk" && cp -a "$POD/kelion_pod.py" "$POD/pod_locuri" "$bk/" || { echo "OPRIT: backup eșuat. Nimic schimbat."; exit 1; }
echo "$bk"

pas "4/5 Aplicare + repornire kelion-pod"
# A doua verificare, imediat înainte de instalare și repornire: un apel început între timp oprește totul.
curl -s -m 5 http://127.0.0.1:8095/sanatate | grep -q '"apel_in_curs": false' || { echo "OPRIT: a început un apel în timpul pregătirii. Nimic instalat. Rulează din nou după apel."; rm -rf "$tmp"; exit 1; }
install -m 644 "$tmp/nou/kelion_pod.py" "$POD/kelion_pod.py"
for f in locuri.py executor_server.py resurse.py; do
  install -m 644 "$tmp/nou/pod_locuri/$f" "$POD/pod_locuri/$f"
done
rm -rf "$POD/pod_locuri/__pycache__"
inainte=$(wc -l < "$J")
systemctl restart kelion-pod
sleep 20
if ! systemctl is-active -q kelion-pod || ! curl -s -m 5 http://127.0.0.1:8095/sanatate | grep -q '"ok": true'; then
  echo "EȘEC: podul nu a pornit. Revin la backup."
  cp -a "$bk/kelion_pod.py" "$POD/kelion_pod.py"
  rm -rf "$POD/pod_locuri" && cp -a "$bk/pod_locuri" "$POD/pod_locuri"
  systemctl restart kelion-pod
  journalctl -u kelion-pod -n 20 --no-pager
  exit 1
fi
echo "podul rulează"

pas "5/5 Dovezi: 60 s de jurnal după repornire"
sleep 40
tail -n +"$((inainte + 1))" "$J" > "$tmp/dupa.jsonl"
echo "canal_dot_esuat în 60 s: $(grep -c canal_dot_esuat "$tmp/dupa.jsonl")   (înainte: la fiecare 4 s, adică ~15)"
echo "locuri_retry în 60 s:    $(grep -c locuri_retry "$tmp/dupa.jsonl")   (înainte: la fiecare 5 s, adică ~12)"
echo "--- evenimente (motivul exact al oricărei erori rămase):"
grep -E 'sunet_loc_esuat|locuri_retry|canal_dot_esuat|canal_login|loc_stare|chrome_' "$tmp/dupa.jsonl" | cut -c1-240
echo "--- stare acum:"
curl -s -m 5 http://127.0.0.1:8095/sanatate | head -c 300; echo
echo
echo "GATA. Backup în $bk. Acum poți suna Kelion pe WhatsApp."
rm -rf "$tmp"
