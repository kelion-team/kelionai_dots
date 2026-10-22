#!/usr/bin/env bash
# (22.10.2026) Laptopul AE nu se mai folosește: Kelion primește regula (cerinte/laptop-retras.md + AE1 în registru), iar
# verificatorul nu mai cere raportul ChatGPT de pe laptop. Fără reporniri. Rulat ca root.
set -uo pipefail
echec() { echo "OPRIT: $*" >&2; exit 1; }
REF="${KELION_REF:-}"
[[ "$REF" =~ ^[0-9a-f]{40}$ ]] || { echo "OPRIT: setează KELION_REF=<commit complet, 40 hex>. Nimic schimbat." >&2; exit 1; }
RAW="https://raw.githubusercontent.com/kelion-team/kelionai_dots/$REF/deploy/laptop"
DIR=/opt/kelion-brain
ts=$(date +%Y%m%d-%H%M%S)
[ "$(id -u)" = 0 ] || echec "rulează ca root."
tmp=$(mktemp -d) && [ -d "$tmp" ] || echec "director temporar; nimic schimbat."
trap 'rm -rf "$tmp"' EXIT
for f in repara_laptop_retras.py laptop-retras.md; do curl -fsSL "$RAW/$f" -o "$tmp/$f" || echec "descărcare $f eșuată. Nimic schimbat."; done
python3 -B "$tmp/repara_laptop_retras.py" "$DIR" "$tmp/nou" "$tmp/laptop-retras.md" || echec "proba pe copie a picat. Nimic schimbat."
bk="$DIR/backup-laptop-$ts"; mkdir -p "$bk/cerinte" || echec "backup eșuat."
cp -a "$DIR/verifica-site.py" "$bk/" && cp -a "$DIR/cerinte/registru-zi.json" "$DIR/cerinte/reguli.json" "$bk/cerinte/" || echec "backup eșuat. Nimic schimbat."
revino() {
  ok=1; cp -a "$bk/verifica-site.py" "$DIR/" || ok=0; cp -a "$bk/cerinte/registru-zi.json" "$bk/cerinte/reguli.json" "$DIR/cerinte/" || ok=0
  rm -f "$DIR/cerinte/laptop-retras.md"
  [ "$ok" = 1 ] && echec "$*; revenit la backup ($bk)."
  echec "$*; REVENIRE INCOMPLETĂ: compară manual cu $bk"
}
install -o brain -g brain -m 644 "$tmp/nou/verifica-site.py" "$DIR/verifica-site.py" || revino "instalare verificator eșuată"
for f in registru-zi.json reguli.json laptop-retras.md; do
  install -o brain -g brain -m 644 "$tmp/nou/cerinte/$f" "$DIR/cerinte/$f" || revino "instalare cerinte/$f eșuată"
done
reg=$(cd "$DIR" && runuser -u brain -- python3 -B -c "import reguli_obligatorii as R; s=R.incarca(); print(s['stare'])" 2>&1 | tail -1)
[ "$reg" = ok ] || revino "regulile nu mai sunt «ok» după schimbare: $reg"
echo "GATA. Kelion primește regula «laptopul AE nu se mai folosește» la fiecare apel; verificatorul nu mai cere laptopul. Backup $bk"
