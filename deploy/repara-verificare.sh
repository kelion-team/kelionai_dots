#!/usr/bin/env bash
# S5 (22.10.2026): lucrările terminate trec prin verificarea IZOLATĂ (copie, bwrap fără rețea și fără acces la server), apoi prin fluxul
# complet existent: poarta de reguli, livrarea automată pe live (backup, probă, rollback; aprobată de Adrian 04:33), «rezolvata».
# Rulat ca root de Kelion (admin) sau de Adrian. Fără repornirea serviciilor (coada rulează pe timer). Timerul cozii e oprit cât se
# instalează și se repun sarcinile, apoi pornit din nou (garantat).
set -uo pipefail
echec() { echo "OPRIT: $*" >&2; exit 1; }
REF="${KELION_REF:-}"
[[ "$REF" =~ ^[0-9a-f]{40}$ ]] || { echo "OPRIT: setează KELION_REF=<commit complet, 40 hex>. Nimic schimbat." >&2; exit 1; }
RAW="https://raw.githubusercontent.com/kelion-team/kelionai_dots/$REF/deploy"
DIR=/opt/kelion-brain
ts=$(date +%Y%m%d-%H%M%S)
[ "$(id -u)" = 0 ] || echec "rulează ca root."
command -v bwrap >/dev/null || echec "bwrap lipsește. Nimic schimbat."
tmp=$(mktemp -d) && [ -d "$tmp" ] || echec "director temporar; nimic schimbat."
TIMER_OPRIT=0
curata() { [ "$TIMER_OPRIT" = 1 ] && systemctl start kelion-coada.timer; rm -rf "$tmp"; }
trap curata EXIT
for f in repara_verificare_izolata.py verificare_izolata.py repune_blocate.py; do
  curl -fsSL "$RAW/$f" -o "$tmp/$f" || echec "descărcare $f eșuată. Nimic schimbat."
done
chmod 755 "$tmp"; chmod 644 "$tmp"/*
python3 -B "$tmp/repara_verificare_izolata.py" "$DIR" "$tmp/nou" || echec "proba pe copie a picat. Nimic schimbat."
cp "$tmp/verificare_izolata.py" "$tmp/nou/" && python3 -m py_compile "$tmp/nou/verificare_izolata.py" || echec "modulul nu compilează. Nimic schimbat."
# proba reală a izolării, ca utilizatorul serviciului: testul NU trebuie să vadă /opt/kelion-brain și NU trebuie să aibă rețea
mkdir -p "$tmp/pr" && printf '%s\n' 'if ls /opt/kelion-brain >/dev/null 2>&1; then echo VEDE_OPT; exit 9; fi' \
  'if getent hosts github.com >/dev/null 2>&1; then echo ARE_RETEA; exit 8; fi' 'echo izolat' > "$tmp/pr/test.sh" && chmod -R a+rX "$tmp/pr"
prob=$(cd /tmp && runuser -u brain -- python3 -B -c "import sys; sys.path.insert(0, sys.argv[1]); import verificare_izolata as V; t = V.verifica(sys.argv[2], 'proba'); print(t[:300]); sys.exit(0 if t.startswith(('VERIFICAT', 'PARTIAL (fara dovada rosu->verde')) else 1)" "$tmp/nou" "$tmp/pr" 2>&1)
rc=$?; echo "proba izolare: ${prob:0:300}"
[ "$rc" = 0 ] || echec "verificarea izolată nu merge pe server (vezi proba). Nimic schimbat."

bk="$DIR/backup-verificare-$ts"; mkdir -p "$bk" && cp -a "$DIR/coada-lucru.py" "$bk/" || echec "backup eșuat. Nimic schimbat."
if [ -e "$DIR/verificare_izolata.py" ]; then cp -a "$DIR/verificare_izolata.py" "$bk/" || echec "backup verificare_izolata.py eșuat. Nimic schimbat."; fi
revino() {
  ok=1; cp -a "$bk/coada-lucru.py" "$DIR/" || ok=0
  if [ -e "$bk/verificare_izolata.py" ]; then cp -a "$bk/verificare_izolata.py" "$DIR/" || ok=0; else rm -f "$DIR/verificare_izolata.py" || ok=0; fi
  [ "$ok" = 1 ] && echec "$*; revenit la backup ($bk)."
  echec "$*; REVENIRE INCOMPLETĂ: compară manual $DIR/coada-lucru.py și $DIR/verificare_izolata.py cu $bk"
}
systemctl stop kelion-coada.timer && TIMER_OPRIT=1 || echec "nu pot opri timerul cozii. Nimic schimbat."
for i in $(seq 1 90); do systemctl is-active --quiet kelion-coada.service || break; sleep 2; done
systemctl is-active --quiet kelion-coada.service && echec "coada încă rulează după 3 min. Nimic schimbat."
install -o brain -g brain -m 644 "$tmp/nou/verificare_izolata.py" "$DIR/verificare_izolata.py" || revino "instalare verificare_izolata.py eșuată"
install -o brain -g brain -m 644 "$tmp/nou/coada-lucru.py" "$DIR/coada-lucru.py" || revino "instalare coada-lucru.py eșuată"
python3 -c "import ast,sys; [ast.parse(open(f).read()) for f in sys.argv[1:]]" "$DIR/coada-lucru.py" "$DIR/verificare_izolata.py" || revino "compilare eșuată"
echo "OK: verificare izolată + flux complet (livrare automată) instalate. Backup $bk"
rep=$(cd "$DIR" && runuser -u brain -- python3 -B "$tmp/repune_blocate.py" "$DIR/coada-lucru.py" 2>&1); rc=$?
echo "$rep" | tail -25
systemctl start kelion-coada.timer && TIMER_OPRIT=0 || { echo "PARȚIAL: instalat, dar timerul cozii NU a pornit: systemctl start kelion-coada.timer" >&2; exit 2; }
[ "$rc" = 0 ] || { echo "PARȚIAL: instalat și timerul pornit; repunerea sarcinilor a eșuat (cod $rc, mesajul de mai sus)." >&2; exit 2; }
echo "GATA. Lucrările terminate de acum: verificare izolată -> livrare automată pe live (backup, probă, rollback) -> rezolvată; ce pică se redistribuie cu motivul."
