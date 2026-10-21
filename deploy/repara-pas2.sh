#!/usr/bin/env bash
# Pasul 2 (21.10.2026), rulat ca root pe server de Kelion (admin) sau de Adrian, o singură comandă:
#  A) așezarea companionului (robot sus, kelionDots sub el, Microfon stânga + Cameră dreapta) — fără repornire;
#  B) locurile de apel nelogate în ChatGPT sunt recunoscute, cer logarea cu adresa corectă și revin singure după logare.
# B repornește kelion-pod, deci se aplică DOAR fără apel în curs (altfel îl sare și spune să rulezi din nou).
set -uo pipefail
REF="${KELION_REF:-}"
# Commit fix obligatoriu (40 hex), același cu cel din URL-ul scriptului: fără ramuri care se pot schimba între revizuire și rulare.
[[ "$REF" =~ ^[0-9a-f]{40}$ ]] || { echo "OPRIT: setează KELION_REF=<commit complet, 40 hex>. Nimic schimbat."; exit 1; }
RAW="https://raw.githubusercontent.com/kelion-team/kelionai_dots/$REF/deploy"
POD=/opt/kelion-pod
ASSETS=/opt/kelion-control/assets
J=/var/lib/kelion-pod/pod.jsonl
ts=$(date +%Y%m%d-%H%M%S)
tmp=$(mktemp -d)
pas() { echo; echo "== $*"; }
[ "$(id -u)" = 0 ] || { echo "Rulează ca root."; exit 1; }

pas "A) Companion"
if grep -q KELION_COMPANION_LAYOUT_20261021 "$ASSETS/portal.css"; then
  echo "deja aplicat"
elif curl -fsSL "$RAW/companion-layout.css" -o "$tmp/c.css" && grep -q KELION_COMPANION_LAYOUT_20261021_END "$tmp/c.css"; then
  cp -a "$ASSETS/portal.css" "$ASSETS/portal.css.backup-$ts"
  cp -a "$ASSETS/portal.html" "$ASSETS/portal.html.backup-$ts"
  cat "$tmp/c.css" >> "$ASSETS/portal.css"
  # versiune nouă în adresa stilului, ca browserul să nu folosească stilul vechi din cache
  sed -i 's/portal\.css?v=\([A-Za-z0-9._-]*\)/portal.css?v=\1-c1/' "$ASSETS/portal.html"
  echo "aplicat; backup portal.css.backup-$ts"
  echo "dovadă: $(grep -c KELION_COMPANION_LAYOUT_20261021 "$ASSETS/portal.css") marcaje în portal.css; $(grep -o 'portal\.css?v=[A-Za-z0-9._-]*' "$ASSETS/portal.html" | head -1)"
else
  echo "OPRIT la A: nu am putut descărca stilul. Nimic schimbat la A."
fi

pas "B) Locuri nelogate"
if ! curl -s -m 5 http://127.0.0.1:8095/sanatate | grep -q '"apel_in_curs": false'; then
  echo "SĂRIT: e un apel în curs. Rulează aceeași comandă din nou după apel (A nu se repetă)."
  rm -rf "$tmp"; exit 2   # nu e reușită: B nu s-a aplicat
fi
curl -fsSL "$RAW/repara_logare_locuri.py" -o "$tmp/r.py" || { echo "OPRIT: descărcare eșuată. Nimic schimbat la B."; exit 1; }
python3 -B "$tmp/r.py" "$POD" "$tmp/nou" || { echo "OPRIT: proba a picat. Nimic schimbat la B."; exit 1; }
# A doua verificare, imediat înainte de instalare și repornire: un apel început între timp oprește totul.
curl -s -m 5 http://127.0.0.1:8095/sanatate | grep -q '"apel_in_curs": false' || { echo "OPRIT: a început un apel în timpul pregătirii. Nimic instalat. Rulează din nou după apel."; rm -rf "$tmp"; exit 1; }
bk="$POD/backup-$ts"; mkdir -p "$bk" && cp -a "$POD/pod_locuri" "$bk/"
for f in executor_server.py locuri.py resurse.py; do install -m 644 "$tmp/nou/pod_locuri/$f" "$POD/pod_locuri/$f"; done
rm -rf "$POD/pod_locuri/__pycache__"
inainte=$(wc -l < "$J")
systemctl restart kelion-pod
sleep 25
if ! systemctl is-active -q kelion-pod || ! curl -s -m 5 http://127.0.0.1:8095/sanatate | grep -q '"ok": true'; then
  echo "EȘEC: revin la backup"; rm -rf "$POD/pod_locuri"; cp -a "$bk/pod_locuri" "$POD/pod_locuri"; systemctl restart kelion-pod; exit 1
fi
sleep 20
echo "--- dovezi după repornire:"
tail -n +"$((inainte + 1))" "$J" | grep -E 'loc_stare|canal_login|alerta|sunet_loc_esuat|locuri_retry' | cut -c1-240
curl -s -m 5 http://127.0.0.1:8095/sanatate | head -c 300; echo
echo
echo "GATA. Acum: deschide ecranul serverului și loghează-te în ChatGPT în ferestrele noi (locul 2 și canalul):"
echo "  https://kelionai.app/app/pod-ecran/vnc.html?autoconnect=1&resize=scale&path=app/pod-ecran/websockify"
echo "După logare, locurile revin singure în ~1 minut (nu mai trebuie niciun fișier-marcaj)."
rm -rf "$tmp"
