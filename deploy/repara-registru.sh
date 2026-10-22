#!/usr/bin/env bash
# R5/R17/R20/R33/A12 (22.10.2026): registrul verifică funcțiile acolo unde sunt acum; procedura-nou.md intră în fiecare lucrare.
# Rulat ca root de Kelion (admin pe server) sau de Adrian. Fără repornire: coada-lucru.py e citit din nou la următoarea pornire
# a supraveghetorului cozii (și de verificator la fiecare rulare). Re-rulabil: coada-lucru.py deja reparat rămâne neschimbat.
# R32: pașii «in executie» cu procesul mort sunt marcați «esuat» (cu motiv), după un backup al jurnalului.
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
curl -fsSL "$RAW/inchide_pasi_orfani.py" -o "$tmp/o.py" || echec "descărcare eșuată. Nimic schimbat."
chmod 755 "$tmp"; chmod 644 "$tmp/o.py"
python3 -B "$tmp/r.py" "$DIR" "$tmp/nou" || echec "proba a picat. Nimic schimbat."
bk="$DIR/backup-registru-$ts"; mkdir -p "$bk" && cp -a "$DIR/coada-lucru.py" "$DIR/cerinte/registru-zi.json" "$bk/" || echec "backup eșuat."
revino() {   # ambele fișiere înapoi; o restaurare eșuată se spune explicit
  if cp -a "$bk/coada-lucru.py" "$DIR/" && cp -a "$bk/registru-zi.json" "$DIR/cerinte/"; then
    echec "$*; revenit la backup ($bk)."
  fi
  echec "$*; REVENIRE INCOMPLETĂ: verifică manual $DIR/coada-lucru.py și $DIR/cerinte/registru-zi.json față de $bk"
}
install -o brain -g brain -m 644 "$tmp/nou/coada-lucru.py" "$DIR/coada-lucru.py" || revino "instalare coada-lucru.py eșuată"
install -o brain -g brain -m 644 "$tmp/nou/cerinte/registru-zi.json" "$DIR/cerinte/registru-zi.json" || revino "instalare registru eșuată"
python3 -m py_compile "$DIR/coada-lucru.py" || revino "compilare eșuată"
[ -r "$DIR/cerinte/procedura-nou.md" ] || revino "cerinte/procedura-nou.md lipsește: lucrările s-ar opri toate"
JUR="$DIR/work/jurnal-cereri.sqlite3"   # totul ca brain: root nu creează fișiere -wal/-shm cu alt proprietar
if install -d -o brain -g brain "$bk/jurnal" && runuser -u brain -- python3 -B -c \
     "import sqlite3,sys; sqlite3.connect(sys.argv[1], timeout=30).backup(sqlite3.connect(sys.argv[2]))" "$JUR" "$bk/jurnal/jurnal-cereri.sqlite3"; then
  runuser -u brain -- python3 -B "$tmp/o.py" "$JUR" || echo "ATENȚIE: pașii orfani nu s-au putut închide (registrul e aplicat). Backup jurnal: $bk/jurnal" >&2
else
  echo "ATENȚIE: backup-ul jurnalului a eșuat; pașii orfani NU au fost atinși (registrul e aplicat)." >&2
fi
echo "dovadă: $(grep -c 'A12 (22.10)' "$DIR/coada-lucru.py") marcaj în coada-lucru.py; registru actualizat; backup $bk"
echo "GATA. La următoarea verificare (max 10 min) R5, R17, R20, R33, A4, A12 sunt verificate în fișierele corecte."
