#!/usr/bin/env bash
# Doar CITIRE (21.10.2026): poate numărul WhatsApp al lui Kelion să folosească grupurile Meta (Groups API)?
# Condiția Meta: «Official Business Account». Tokenul e luat din serviciul kelion-whatsapp și NU se afișează.
set -uo pipefail
[ "$(id -u)" = 0 ] || { echo "Rulează ca root."; exit 1; }
P=$(systemctl show kelion-whatsapp -p MainPID --value)
[ -n "$P" ] && [ "$P" != 0 ] || { echo "kelion-whatsapp nu rulează."; exit 1; }
T=$(tr '\0' '\n' < /proc/$P/environ | sed -n 's/^KELION_WA_TOKEN=//p')
ID=$(tr '\0' '\n' < /proc/$P/environ | sed -n 's/^KELION_WA_PHONE_ID=//p')
V=$(tr '\0' '\n' < /proc/$P/environ | sed -n 's/^KELION_WA_GRAPH_VER=//p'); V=${V:-v23.0}
[ -n "$T" ] && [ -n "$ID" ] || { echo "Lipsește tokenul sau phone_id în mediul serviciului."; exit 1; }
echo "== Numărul lui Kelion (Meta):"
curl -s -m 20 -H "Authorization: Bearer $T" \
  "https://graph.facebook.com/$V/$ID?fields=display_phone_number,verified_name,is_official_business_account,name_status,quality_rating,messaging_limit_tier,platform_type" \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); [print(f"  {k}: {v}") for k,v in d.items() if k!="id"]'
echo "== Grupuri existente (dacă API-ul e permis):"
curl -s -m 20 -H "Authorization: Bearer $T" "https://graph.facebook.com/$V/$ID/groups?limit=5" \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); e=d.get("error"); print("  EROARE Meta:", e.get("code"), e.get("message")) if e else print("  permis; grupuri:", len(d.get("data",[])))'
unset T
echo "Rezultat: «is_official_business_account: True» = grupurile se pot face. Altfel Meta le refuză."
