#!/usr/bin/env bash
# Auto-deploy pentru interfața web kelionai.app (web-v1).
# Rulează pe kelion-nou, periodic (systemd timer). Citește repo-ul PUBLIC
# kelion-team/kelionai_dots, ramura main; nu are nevoie de chei sau parole.
#
# Dacă site-live/web/ s-a schimbat în main:
#   1. salvează copia fișierelor live,
#   2. copiază fișierele noi în WEB_DIR,
#   3. repornește serviciul web,
#   4. verifică /api/config local; la eșec pune înapoi copia și repornește.
# Nu atinge .env, baza de date, sesiunile sau serviciul ingress.
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/kelion-team/kelionai_dots.git}"
BRANCH="${BRANCH:-main}"
WEB_DIR="${WEB_DIR:-/opt/kelion-app/web-v1}"
STATE_DIR="${STATE_DIR:-/var/lib/kelion-deploy}"
WEB_PORT="${WEB_PORT:-8766}"
FILES=(index.html app.js auth.mjs server.mjs style.css)

log() { echo "[kelion-deploy] $*"; }

# Serviciul systemd care rulează WEB_DIR/server.mjs (detectat dacă nu e dat).
detect_service() {
  local unit
  for unit in $(systemctl list-units --type=service --all --no-legend --plain | awk '{print $1}'); do
    if systemctl cat "$unit" 2>/dev/null | grep -q "${WEB_DIR}/server.mjs"; then echo "$unit"; return 0; fi
  done
  return 1
}
WEB_SERVICE="${WEB_SERVICE:-$(detect_service || true)}"
if [[ -z "$WEB_SERVICE" ]]; then log "EROARE: nu găsesc serviciul systemd pentru ${WEB_DIR}/server.mjs; setează WEB_SERVICE."; exit 1; fi

mkdir -p "$STATE_DIR"
exec 9>"$STATE_DIR/lock"
flock -n 9 || { log "alt deploy rulează deja"; exit 0; }

REPO="$STATE_DIR/repo"
if [[ ! -d "$REPO/.git" ]]; then
  git clone -q --depth 1 --branch "$BRANCH" "$REPO_URL" "$REPO"
else
  git -C "$REPO" fetch -q --depth 1 origin "$BRANCH"
  git -C "$REPO" reset -q --hard FETCH_HEAD
fi

NEW_TREE="$(git -C "$REPO" rev-parse HEAD:site-live/web)"
LAST_TREE="$(cat "$STATE_DIR/deployed-tree" 2>/dev/null || true)"
if [[ "$NEW_TREE" == "$LAST_TREE" ]]; then exit 0; fi
# O versiune care a picat deja nu se reîncearcă la fiecare rulare; se așteaptă un commit nou.
if [[ "$NEW_TREE" == "$(cat "$STATE_DIR/failed-tree" 2>/dev/null || true)" ]]; then exit 0; fi

# Prima rulare: dacă fișierele live sunt deja identice, doar notează starea.
same=1
for f in "${FILES[@]}"; do cmp -s "$REPO/site-live/web/$f" "$WEB_DIR/$f" || same=0; done
if [[ $same -eq 1 ]]; then echo "$NEW_TREE" > "$STATE_DIR/deployed-tree"; log "deja la zi ($NEW_TREE)"; exit 0; fi

COMMIT="$(git -C "$REPO" rev-parse --short HEAD)"
BACKUP="$STATE_DIR/backup-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$BACKUP"
for f in "${FILES[@]}"; do [[ -f "$WEB_DIR/$f" ]] && cp -p "$WEB_DIR/$f" "$BACKUP/$f"; done
log "deploy commit $COMMIT în $WEB_DIR (copie: $BACKUP)"

owner="$(stat -c '%U:%G' "$WEB_DIR/server.mjs" 2>/dev/null || echo root:root)"
for f in "${FILES[@]}"; do install -m 0644 -o "${owner%%:*}" -g "${owner##*:}" "$REPO/site-live/web/$f" "$WEB_DIR/$f"; done

check() {
  local i
  for i in $(seq 1 15); do
    if curl -fsS --max-time 3 -H 'Host: kelionai.app' "http://127.0.0.1:${WEB_PORT}/api/config" | grep -q '"ready":true'; then return 0; fi
    sleep 2
  done
  return 1
}

systemctl restart "$WEB_SERVICE"
if check; then
  echo "$NEW_TREE" > "$STATE_DIR/deployed-tree"
  log "OK: $COMMIT live, /api/config ready:true"
  ls -1dt "$STATE_DIR"/backup-* 2>/dev/null | tail -n +11 | xargs -r rm -rf   # păstrează ultimele 10 copii
else
  log "EȘEC: verificarea a picat după $COMMIT; revin la copia anterioară"
  for f in "${FILES[@]}"; do [[ -f "$BACKUP/$f" ]] && cp -p "$BACKUP/$f" "$WEB_DIR/$f"; done
  systemctl restart "$WEB_SERVICE"
  echo "$NEW_TREE" > "$STATE_DIR/failed-tree"
  if check; then log "revenire reușită"; else log "ATENȚIE: nici versiunea anterioară nu răspunde ready:true"; fi
  exit 1
fi
