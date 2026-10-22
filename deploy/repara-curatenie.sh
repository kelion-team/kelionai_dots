#!/usr/bin/env bash
# A17 (22.10.2026): probele CDP nu mai lasă directoare goale playwright-artifacts-* în /tmp (~560/oră).
# Rulat ca root de Kelion (admin pe server) sau de Adrian. Repornește kelion-pod, deci DOAR fără apel în curs.
set -uo pipefail
echec() { echo "OPRIT: $*" >&2; exit 1; }
REF="${KELION_REF:-}"
[[ "$REF" =~ ^[0-9a-f]{40}$ ]] || { echo "OPRIT: setează KELION_REF=<commit complet, 40 hex>. Nimic schimbat." >&2; exit 1; }
RAW="https://raw.githubusercontent.com/kelion-team/kelionai_dots/$REF/deploy"
POD=/opt/kelion-pod
ts=$(date +%Y%m%d-%H%M%S)
liber() { curl -s -m 5 http://127.0.0.1:8095/sanatate | grep -q '"apel_in_curs": false'; }
numara() { find /tmp -maxdepth 1 -name 'playwright-artifacts-*' -user brain -empty | wc -l; }
[ "$(id -u)" = 0 ] || echec "rulează ca root."
liber || echec "e un apel în curs. Nimic schimbat."
tmp=$(mktemp -d) && [ -d "$tmp" ] || echec "director temporar; nimic schimbat."
trap 'rm -rf "$tmp"' EXIT
curl -fsSL "$RAW/repara_curatenie_playwright.py" -o "$tmp/r.py" || echec "descărcare eșuată. Nimic schimbat."
python3 -B "$tmp/r.py" "$POD" "$tmp/nou" || echec "proba a picat. Nimic schimbat."
liber || echec "a început un apel în timpul pregătirii. Nimic instalat."
bk="$POD/backup-curatenie-$ts"
mkdir -p "$bk/pod_locuri" && cp -a "$POD/pod_locuri/executor_server.py" "$bk/pod_locuri/" && cp -a "$POD/paznic.py" "$bk/" || echec "backup eșuat; nu instalez."
revino() {   # orice eșec după prima instalare: ambele fișiere înapoi, apoi repornire pe codul vechi
  echo "EȘEC: $*; revin la backup" >&2
  cp -a "$bk/pod_locuri/executor_server.py" "$POD/pod_locuri/" && cp -a "$bk/paznic.py" "$POD/" || echec "restaurare eșuată; nu repornesc. Backup: $bk"
  rm -rf "$POD/pod_locuri/__pycache__" "$POD/__pycache__"
  systemctl restart kelion-pod; exit 1
}
install -m 644 "$tmp/nou/pod_locuri/executor_server.py" "$POD/pod_locuri/executor_server.py" || revino "instalare executor_server.py"
install -m 644 "$tmp/nou/paznic.py" "$POD/paznic.py" || revino "instalare paznic.py"
rm -rf "$POD/pod_locuri/__pycache__" "$POD/__pycache__"
if cmp -s "$bk/pod_locuri/executor_server.py" "$POD/pod_locuri/executor_server.py"; then
  echo "executor_server.py era deja reparat: fără repornire (paznic.py rulează din timer, nu cere repornire)"
else
  systemctl restart kelion-pod || revino "repornirea kelion-pod"
fi
sleep 25
if ! systemctl is-active -q kelion-pod || ! curl -s -m 5 http://127.0.0.1:8095/sanatate | grep -q '"ok": true'; then
  revino "podul nu e sănătos după repornire"
fi
inainte=$(numara)
# Doar directoarele GOALE, ale utilizatorului brain, mai vechi de 10 minute (resturile vechii scurgeri).
find /tmp -maxdepth 1 -name 'playwright-artifacts-*' -user brain -empty -mmin +10 -delete
dupa_curatare=$(numara)
marcaj="$tmp/marcaj"; touch "$marcaj"
sleep 180
# Doar directoarele goale apărute după curățare și mai vechi de 1 minut (nu cele ale unei probe în curs).
noi=$(find /tmp -maxdepth 1 -name 'playwright-artifacts-*' -user brain -empty -newer "$marcaj" -mmin +1 | wc -l)
echo "--- dovezi:"
echo "directoare goale: înainte $inainte, după curățare $dupa_curatare; rămase noi în 3 minute: $noi (vechiul ritm: ~28)"
sanatate=$(curl -s -m 5 http://127.0.0.1:8095/sanatate); echo "${sanatate:0:250}"
problema=""
grep -q '"ok": true' <<<"$sanatate" || problema="podul nu mai e sănătos după 3 minute"
[ "$noi" -le 2 ] || problema="scurgerea continuă ($noi directoare noi în 3 minute)"
if [ -n "$problema" ]; then
  # Nu repornim peste un apel început între timp: revenirea se face manual, după apel.
  liber || echec "$problema; e un apel în curs, deci NU repornesc. După apel: cp -a $bk/pod_locuri/executor_server.py $POD/pod_locuri/ && cp -a $bk/paznic.py $POD/ && systemctl restart kelion-pod"
  revino "$problema"
fi
echo "GATA. Backup: $bk"
