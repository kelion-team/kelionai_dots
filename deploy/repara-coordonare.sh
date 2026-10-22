#!/usr/bin/env bash
# (22.10.2026) Coada preia, analizează și redistribuie până la rezolvare; cerințele de coordonare din 21.10 devin obligatorii pentru Kelion.
# Rulat ca root de Kelion (admin) sau de Adrian. Fără repornirea serviciilor: coada și verificatorul rulează pe timer și citesc codul nou
# la următoarea rulare. Timerul cozii e oprit cât timp se instalează și se repun sarcinile blocate, apoi pornit din nou (garantat).
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
for f in repara_coordonare.py preluare_redistribuire.py repune_blocate.py cerinte/coordonare-21-10.md; do
  curl -fsSL "$RAW/$f" -o "$tmp/$(basename "$f")" || echec "descărcare $f eșuată. Nimic schimbat."
done
chmod 755 "$tmp"; chmod 644 "$tmp"/*
python3 -B "$tmp/repara_coordonare.py" "$DIR" "$tmp/nou" "$tmp/coordonare-21-10.md" || echec "proba a picat. Nimic schimbat."
cp "$tmp/preluare_redistribuire.py" "$tmp/nou/" && python3 -m py_compile "$tmp/nou/preluare_redistribuire.py" || echec "modulul nu compilează. Nimic schimbat."

bk="$DIR/backup-coordonare-$ts"; mkdir -p "$bk/cerinte" || echec "backup eșuat."
cp -a "$DIR/coada-lucru.py" "$DIR/verifica-site.py" "$bk/" && cp -a "$DIR/cerinte/registru-zi.json" "$DIR/cerinte/reguli.json" "$bk/cerinte/" || echec "backup eșuat. Nimic schimbat."
[ -e "$DIR/preluare_redistribuire.py" ] && cp -a "$DIR/preluare_redistribuire.py" "$bk/"
[ -e "$DIR/cerinte/coordonare-21-10.md" ] && cp -a "$DIR/cerinte/coordonare-21-10.md" "$bk/cerinte/"
revino() {   # tot înapoi; fișierele noi (fără copie în backup) se scot; o restaurare eșuată se spune explicit
  ok=1
  cp -a "$bk/coada-lucru.py" "$bk/verifica-site.py" "$DIR/" || ok=0
  cp -a "$bk/cerinte/registru-zi.json" "$bk/cerinte/reguli.json" "$DIR/cerinte/" || ok=0
  if [ -e "$bk/preluare_redistribuire.py" ]; then cp -a "$bk/preluare_redistribuire.py" "$DIR/" || ok=0; else rm -f "$DIR/preluare_redistribuire.py" || ok=0; fi
  if [ -e "$bk/cerinte/coordonare-21-10.md" ]; then cp -a "$bk/cerinte/coordonare-21-10.md" "$DIR/cerinte/" || ok=0; else rm -f "$DIR/cerinte/coordonare-21-10.md" || ok=0; fi
  [ "$ok" = 1 ] && echec "$*; revenit la backup ($bk)."
  echec "$*; REVENIRE INCOMPLETĂ: compară manual $DIR cu $bk"
}
systemctl stop kelion-coada.timer && TIMER_OPRIT=1 || echec "nu pot opri timerul cozii. Nimic schimbat."
for i in $(seq 1 90); do systemctl is-active --quiet kelion-coada.service || break; sleep 2; done
systemctl is-active --quiet kelion-coada.service && echec "coada încă rulează după 3 min. Nimic schimbat."
for f in coada-lucru.py verifica-site.py preluare_redistribuire.py; do
  install -o brain -g brain -m 644 "$tmp/nou/$f" "$DIR/$f" || revino "instalare $f eșuată"
done
for f in registru-zi.json reguli.json coordonare-21-10.md; do
  install -o brain -g brain -m 644 "$tmp/nou/cerinte/$f" "$DIR/cerinte/$f" || revino "instalare cerinte/$f eșuată"
done
for f in coada-lucru.py verifica-site.py preluare_redistribuire.py; do
  runuser -u brain -- python3 -B -m py_compile "$DIR/$f" 2>/dev/null || python3 -c "import ast,sys; ast.parse(open(sys.argv[1]).read())" "$DIR/$f" || revino "$f nu compilează"
done
reg=$(cd "$DIR" && runuser -u brain -- python3 -B -c "import reguli_obligatorii as R; s=R.incarca(); print(s['stare'], '; '.join(s['motive']))" 2>&1 | tail -1)
case "$reg" in ok*) echo "reguli: ok (coordonare-21-10.md obligatoriu)";; *) revino "regulile nu mai sunt «ok» după schimbare: $reg";; esac
echo "OK: coada (preluare + redistribuire), verificator, registru (+27 cerințe K/P/I/M), reguli. Backup $bk"
rep=$(cd "$DIR" && runuser -u brain -- python3 -B "$tmp/repune_blocate.py" "$DIR/coada-lucru.py" 2>&1); rc=$?
echo "$rep" | tail -25
systemctl start kelion-coada.timer && TIMER_OPRIT=0 || { echo "PARȚIAL: totul e instalat, dar timerul cozii NU a pornit: systemctl start kelion-coada.timer" >&2; exit 2; }
[ "$rc" = 0 ] || { echo "PARȚIAL: codul e instalat și timerul pornit; repunerea sarcinilor blocate a eșuat (cod $rc, mesajul de mai sus)." >&2; exit 2; }
echo "GATA. Coada rulează din nou (la 2 min): sarcinile repuse pornesc pe rând în kelion-remediere; fiecare blocare se redistribuie cu motivul, de max 3 ori, apoi ajunge la Adrian."
