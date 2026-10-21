#!/usr/bin/env bash
# Toate reparațiile rămase, într-o singură comandă (Adrian, după ce închizi apelul):
#   pasul 2 — companion așezat corect, locuri nelogate recunoscute, fără «ocupat» fals la vârf de încărcare;
#   pasul 3 — orice număr WhatsApp primește răspuns, necunoscuții pe ruta izolată de invitați.
# Fiecare pas își face proba pe server, backup și revenire; nimic nu se aplică în timpul unui apel.
set -uo pipefail
REF="${KELION_REF:-}"
# Commit fix obligatoriu (40 hex), același cu cel din URL-ul scriptului: fără ramuri care se pot schimba între revizuire și rulare.
[[ "$REF" =~ ^[0-9a-f]{40}$ ]] || { echo "OPRIT: setează KELION_REF=<commit complet, 40 hex>. Nimic schimbat."; exit 1; }
RAW="https://raw.githubusercontent.com/kelion-team/kelionai_dots/$REF/deploy"
[ "$(id -u)" = 0 ] || { echo "Rulează ca root."; exit 1; }
if ! curl -s -m 5 http://127.0.0.1:8095/sanatate | grep -q '"apel_in_curs": false'; then
  echo "OPRIT: e un apel în curs (serverul îl vede activ). Închide apelul și rulează din nou. Nimic schimbat."; exit 1
fi
echo "########## PASUL 2"; curl -fsSL "$RAW/repara-pas2.sh" | KELION_REF="$REF" bash; r2=$?
sleep 5
echo "########## PASUL 3"; curl -fsSL "$RAW/repara-pas3.sh" | KELION_REF="$REF" bash; r3=$?
echo; echo "REZUMAT: pasul 2 cod=$r2, pasul 3 cod=$r3 (0 = reușit)"
# Codul de ieșire spune adevărul: diferit de 0 dacă oricare pas nu s-a aplicat complet.
[ "$r2" = 0 ] && [ "$r3" = 0 ] || { echo "NEREUȘIT: cel puțin un pas nu s-a aplicat (vezi mai sus)."; exit 1; }
echo "REUȘIT: ambii pași aplicați."
