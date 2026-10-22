#!/usr/bin/env bash
# (22.10.2026) Fiecare lucrare primește copia live DOAR DE CITIT în <proiect>/.kelion/live/ (fără secrete și date personale),
# ca executanții să poată diagnostica live-ul fără să li se ridice bariera. Fără repornirea serviciilor; timerul cozii e oprit cât
# se instalează, apoi pornit din nou (garantat).
set -uo pipefail
echec() { echo "OPRIT: $*" >&2; exit 1; }
REF="${KELION_REF:-}"
[[ "$REF" =~ ^[0-9a-f]{40}$ ]] || { echo "OPRIT: setează KELION_REF=<commit complet, 40 hex>. Nimic schimbat." >&2; exit 1; }
RAW="https://raw.githubusercontent.com/kelion-team/kelionai_dots/$REF/deploy"
DIR=/opt/kelion-brain
ts=$(date +%Y%m%d-%H%M%S)
[ "$(id -u)" = 0 ] || echec "rulează ca root."
tmp=$(mktemp -d) && [ -d "$tmp" ] || echec "director temporar; nimic schimbat."
TIMER_OPRIT=0
curata() { [ "$TIMER_OPRIT" = 1 ] && systemctl start kelion-coada.timer; rm -rf "$tmp"; }
trap curata EXIT
for f in repara_copie_live.py copie_live.py; do curl -fsSL "$RAW/$f" -o "$tmp/$f" || echec "descărcare $f eșuată. Nimic schimbat."; done
chmod 755 "$tmp"; chmod 644 "$tmp"/*
python3 -B "$tmp/repara_copie_live.py" "$DIR" "$tmp/nou" || echec "proba pe copie a picat. Nimic schimbat."
cp "$tmp/copie_live.py" "$tmp/nou/" && python3 -m py_compile "$tmp/nou/copie_live.py" || echec "modulul nu compilează. Nimic schimbat."
chmod -R a+rX "$tmp"
mkdir -p "$tmp/pr" && chown brain:brain "$tmp/pr"
prob=$(cd /tmp && runuser -u brain -- python3 -B -c "import sys; sys.path.insert(0, sys.argv[1]); import copie_live as C; print(C.sincronizeaza(sys.argv[2])[:160])" "$tmp/nou" "$tmp/pr" 2>&1) \
  || echec "copia live nu merge ca brain: ${prob:0:300}. Nimic schimbat."
echo "proba copiei: $prob"
echo "fișiere care seamănă a secrete (necopiate): $(grep -c '^- ' "$tmp/pr/.kelion/live/INDEX.md" 2>/dev/null || echo 0)"
bk="$DIR/backup-copie-live-$ts"; mkdir -p "$bk" && cp -a "$DIR/coada-lucru.py" "$bk/" || echec "backup eșuat. Nimic schimbat."
revino() {
  ok=1; cp -a "$bk/coada-lucru.py" "$DIR/" || ok=0; rm -f "$DIR/copie_live.py" || ok=0
  [ "$ok" = 1 ] && echec "$*; revenit la backup ($bk)."
  echec "$*; REVENIRE INCOMPLETĂ: compară manual $DIR/coada-lucru.py cu $bk"
}
systemctl stop kelion-coada.timer && TIMER_OPRIT=1 || echec "nu pot opri timerul cozii. Nimic schimbat."
for i in $(seq 1 90); do systemctl is-active --quiet kelion-coada.service || break; sleep 2; done
systemctl is-active --quiet kelion-coada.service && echec "coada încă rulează după 3 min. Nimic schimbat."
install -o brain -g brain -m 644 "$tmp/nou/copie_live.py" "$DIR/copie_live.py" || revino "instalare copie_live.py eșuată"
install -o brain -g brain -m 644 "$tmp/nou/coada-lucru.py" "$DIR/coada-lucru.py" || revino "instalare coada-lucru.py eșuată"
python3 -c "import ast,sys; [ast.parse(open(f).read()) for f in sys.argv[1:]]" "$DIR/coada-lucru.py" "$DIR/copie_live.py" || revino "compilare eșuată"
systemctl start kelion-coada.timer && TIMER_OPRIT=0 || { echo "PARȚIAL: instalat, dar timerul cozii NU a pornit: systemctl start kelion-coada.timer" >&2; exit 2; }
echo "GATA. Backup $bk. De la următoarea lucrare, executantul are copia live (doar citire) în .kelion/live/."
