#!/usr/bin/env bash
# Grupurile WhatsApp cu Kelion (Adrian, 21.10.2026) — rulat de Adrian ca root, o singură comandă.
#  1. Verifică întâi condiția Meta (Official Business Account). Dacă nu e îndeplinită: oprire, nimic schimbat.
#  2. Doar fără apel în curs (kelion-whatsapp transmite și apelurile către pod).
#  3. Probă pe copie, backup, instalare, repornire kelion-whatsapp, verificare; la eșec revine singur.
# După instalare, scrie-i lui Kelion pe WhatsApp: «grup nou Familie», apoi «grup nou Prieteni» (primești linkurile).
set -euo pipefail
REF="${KELION_REF:-fix/locuri-asteptare-sunet}"
RAW="https://raw.githubusercontent.com/kelion-team/kelionai_dots/$REF"
DIR=/opt/kelion-brain
ts=$(date +%Y%m%d-%H%M%S)
tmp=$(mktemp -d); trap 'rm -rf "$tmp"; unset T' EXIT
[ "$(id -u)" = 0 ] || { echo "Rulează ca root."; exit 1; }

echo "== 1/4 Condiția Meta: Official Business Account"
P=$(systemctl show kelion-whatsapp -p MainPID --value)
T=$(tr '\0' '\n' < /proc/$P/environ | sed -n 's/^KELION_WA_TOKEN=//p')
ID=$(tr '\0' '\n' < /proc/$P/environ | sed -n 's/^KELION_WA_PHONE_ID=//p')
OBA=$(curl -s -m 20 -H "Authorization: Bearer $T" "https://graph.facebook.com/v23.0/$ID?fields=is_official_business_account" \
      | python3 -c 'import json,sys; print(json.load(sys.stdin).get("is_official_business_account"))' || echo eroare)
unset T
echo "is_official_business_account: $OBA"
if [ "$OBA" != "True" ]; then
  echo "OPRIT: Meta nu permite grupuri pentru acest număr fără Official Business Account. Nimic schimbat."; exit 1
fi

echo "== 2/4 Niciun apel în curs?"
curl -s -m 5 http://127.0.0.1:8095/sanatate | grep -q '"apel_in_curs": false' || { echo "OPRIT: apel în curs. Nimic schimbat."; exit 1; }

echo "== 3/4 Probă pe copie"
curl -fsSL "$RAW/whatsapp_grupuri/whatsapp_grupuri.py" -o "$tmp/whatsapp_grupuri.py"
curl -fsSL "$RAW/deploy/repara_grupuri.py" -o "$tmp/repara_grupuri.py"
python3 -B "$tmp/repara_grupuri.py" "$DIR" "$tmp/nou"
cp "$tmp/whatsapp_grupuri.py" "$tmp/nou/" && (cd "$tmp/nou" && python3 -B -c 'import whatsapp_grupuri as G; assert G.cerere_pentru_kelion("Kelion, salut tuturor") and G.cerere_pentru_kelion("salut") is None; print("modul OK")')

echo "== 4/4 Backup, instalare, repornire"
bk="$DIR/backup-grupuri-$ts"; mkdir -p "$bk"; cp -a "$DIR/whatsapp.py" "$bk/"
install -o brain -g brain -m 644 "$tmp/whatsapp_grupuri.py" "$DIR/whatsapp_grupuri.py"
install -o brain -g brain -m 644 "$tmp/nou/whatsapp.py" "$DIR/whatsapp.py"
systemctl restart kelion-whatsapp
sleep 8
if ! systemctl is-active -q kelion-whatsapp || journalctl -u kelion-whatsapp --since "-15s" --no-pager | grep -q Traceback; then
  echo "EȘEC: revin la backup"; cp -a "$bk/whatsapp.py" "$DIR/whatsapp.py"; rm -f "$DIR/whatsapp_grupuri.py"
  systemctl restart kelion-whatsapp; journalctl -u kelion-whatsapp -n 15 --no-pager; exit 1
fi
echo "kelion-whatsapp: $(systemctl is-active kelion-whatsapp); backup: $bk"
echo
echo "GATA. Scrie-i lui Kelion pe WhatsApp: «grup nou Familie», apoi «grup nou Prieteni». Primești linkurile de invitație."
echo "În grup, Kelion răspunde doar la mesaje care încep sau conțin «Kelion» plus cererea."
