#!/usr/bin/env bash
# (22.10.2026) Reparațiile de siguranță din recenziile Codex la #87, #88, #89 + livrarea pe live doar cu aprobarea lui Adrian.
#   preluare_redistribuire.py  indexul pregătit nu se atinge; commit doar pe căile filtrate; escaladarea marcată după anunț
#   verificare_izolata.py      fără secrete și fără .git în sandbox; ieșire limitată; VERIFICAT doar cu dovada «roșu → verde»
#   copie_live.py              legăturile simbolice nu se urmează; senzorii trec prin filtrul de secrete
#   coada-lucru.py             livrarea pe live așteaptă aprobarea (kelion-aproba-livrare <lucrare>)
# Probă pe copie, backup al tuturor fișierelor atinse, revenire completă la orice eșec; timerul cozii repornit garantat.
set -uo pipefail
echec() { echo "OPRIT: $*" >&2; exit 1; }
REF="${KELION_REF:-}"
[[ "$REF" =~ ^[0-9a-f]{40}$ ]] || { echo "OPRIT: setează KELION_REF=<commit complet, 40 hex>. Nimic schimbat." >&2; exit 1; }
RAW="https://raw.githubusercontent.com/kelion-team/kelionai_dots/$REF/deploy"
DIR=/opt/kelion-brain
SBIN=/usr/local/sbin/kelion-aproba-livrare
ts=$(date +%Y%m%d-%H%M%S)
[ "$(id -u)" = 0 ] || echec "rulează ca root."
tmp=$(mktemp -d) && [ -d "$tmp" ] || echec "director temporar; nimic schimbat."
TIMER_OPRIT=0
curata() {   # timerul cozii pornit din nou garantat; dacă nu pornește, se spune clar (coada nu rămâne oprită pe tăcute)
  if [ "$TIMER_OPRIT" = 1 ] && ! systemctl start kelion-coada.timer; then
    echo "ATENȚIE: timerul cozii NU a pornit din nou; coada e OPRITĂ. Rulează: systemctl start kelion-coada.timer" >&2
  fi
  rm -rf "$tmp"
}
trap curata EXIT
MODULE="preluare_redistribuire.py verificare_izolata.py copie_live.py"
for f in $MODULE repara_livrare_aprobata.py kelion-aproba-livrare; do
  curl -fsSL "$RAW/$f" -o "$tmp/$f" || echec "descărcare $f eșuată. Nimic schimbat."
done
chmod 755 "$tmp"; chmod 644 "$tmp"/*
python3 -B "$tmp/repara_livrare_aprobata.py" "$DIR" "$tmp/nou" || echec "proba pe copie (coada) a picat. Nimic schimbat."
for f in $MODULE; do cp "$tmp/$f" "$tmp/nou/" || echec "copiere $f"; done
python3 -m py_compile "$tmp/nou/"*.py "$tmp/kelion-aproba-livrare" || echec "un fișier nu compilează. Nimic schimbat."
chmod -R a+rX "$tmp"
# proba izolării, ca utilizatorul serviciului: testul NU vede /opt/kelion-brain, NU are rețea, NU vede .env
mkdir -p "$tmp/pr" && printf '%s\n' 'if ls /opt/kelion-brain >/dev/null 2>&1; then echo VEDE_OPT; exit 9; fi' \
  'if getent hosts github.com >/dev/null 2>&1; then echo ARE_RETEA; exit 8; fi' 'if [ -e .env ]; then echo VEDE_ENV; exit 7; fi' \
  'echo izolat' > "$tmp/pr/test.sh" && echo "K=1" > "$tmp/pr/.env" && chmod -R a+rX "$tmp/pr"
prob=$(cd /tmp && runuser -u brain -- python3 -B -c "import sys; sys.path.insert(0, sys.argv[1]); import verificare_izolata as V; t = V.verifica(sys.argv[2], 'proba'); print(t[:300]); sys.exit(0 if t.startswith('PARTIAL (fara dovada rosu->verde') else 1)" "$tmp/nou" "$tmp/pr" 2>&1)
rc=$?; echo "proba izolare: ${prob:0:300}"
[ "$rc" = 0 ] || echec "verificarea izolată nu se comportă corect pe server (vezi proba). Nimic schimbat."

bk="$DIR/backup-securitate-$ts"; mkdir -p "$bk" || echec "backup eșuat. Nimic schimbat."
cp -a "$DIR/coada-lucru.py" "$bk/" || echec "backup coada-lucru.py eșuat. Nimic schimbat."
for f in $MODULE; do
  if [ -e "$DIR/$f" ]; then cp -a "$DIR/$f" "$bk/" || echec "backup $f eșuat. Nimic schimbat."; fi
done
if [ -e "$SBIN" ]; then cp -a "$SBIN" "$bk/" || echec "backup $SBIN eșuat. Nimic schimbat."; fi
revino() {
  ok=1; cp -a "$bk/coada-lucru.py" "$DIR/" || ok=0
  for f in $MODULE; do
    if [ -e "$bk/$f" ]; then cp -a "$bk/$f" "$DIR/" || ok=0; else rm -f "$DIR/$f" || ok=0; fi
  done
  if [ -e "$bk/kelion-aproba-livrare" ]; then cp -a "$bk/kelion-aproba-livrare" "$SBIN" || ok=0; else rm -f "$SBIN" || ok=0; fi
  [ "$ok" = 1 ] && echec "$*; revenit la backup ($bk)."
  echec "$*; REVENIRE INCOMPLETĂ: compară manual $DIR și $SBIN cu $bk"
}
systemctl stop kelion-coada.timer && TIMER_OPRIT=1 || echec "nu pot opri timerul cozii. Nimic schimbat."
for i in $(seq 1 90); do systemctl is-active --quiet kelion-coada.service || break; sleep 2; done
systemctl is-active --quiet kelion-coada.service && echec "coada încă rulează după 3 min. Nimic schimbat."
for f in $MODULE coada-lucru.py; do
  install -o brain -g brain -m 644 "$tmp/nou/$f" "$DIR/$f" || revino "instalare $f eșuată"
done
install -o root -g root -m 755 "$tmp/kelion-aproba-livrare" "$SBIN" || revino "instalare $SBIN eșuată"
install -d -o root -g root -m 755 /var/lib/kelion-livrare || revino "directorul aprobărilor nu a putut fi creat"
python3 -c "import ast,sys; [ast.parse(open(f).read()) for f in sys.argv[1:]]" "$DIR/coada-lucru.py" $(for f in $MODULE; do echo "$DIR/$f"; done) \
  || revino "compilare eșuată"
grep -q "(22.10) livrare doar cu aprobare v2" "$DIR/coada-lucru.py" || revino "poarta de aprobare (v2) lipsește din coada instalată"
systemctl start kelion-coada.timer && TIMER_OPRIT=0 || { echo "PARȚIAL: instalat, dar timerul cozii NU a pornit: systemctl start kelion-coada.timer" >&2; exit 2; }
echo "GATA. Backup $bk. Livrarea pe live cere acum aprobarea: kelion-aproba-livrare <lucrare> (lista: kelion-aproba-livrare --lista)."
