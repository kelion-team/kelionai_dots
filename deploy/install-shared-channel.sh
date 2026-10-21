#!/usr/bin/env bash
# Instalează puntea comună Kelion (channel_bridge.shared_http) pe kelion-nou.
# Rulează ca root, o singură dată; e sigur de rulat din nou (idempotent).
#
#   1. checkout main din repo-ul public în /opt/kelion-shared-channel
#   2. utilizator de serviciu dedicat, fără shell și fără root
#   3. cinci chei distincte (chatgpt, work, kelion, cloud, contabo) generate
#      local în /etc/kelion-shared-channel/channel.env (0600, root) — nu se afișează
#   4. serviciu systemd restricționat, ascultă doar pe 127.0.0.1:8778
#   5. ruta /kelion-channel/ în nginx (cu nginx -t și revenire la eroare)
#   6. verifică fiecare mediu cu cheia lui: local și prin https://kelionai.app
# Nu atinge site-ul web, .env-ul aplicației, Codex, Brain sau alte servicii.
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/kelion-team/kelionai_dots.git}"
BRANCH="${BRANCH:-main}"
ROOT="${ROOT:-/opt/kelion-shared-channel}"
SVC_USER="${SVC_USER:-kelion-channel}"
ENV_DIR=/etc/kelion-shared-channel
ENV_FILE="$ENV_DIR/channel.env"
STATE_DIR=/var/lib/kelion-shared-channel
UNIT=/etc/systemd/system/kelion-shared-channel.service
PORT=8778
PUBLIC=https://kelionai.app
PEERS=(chatgpt work kelion cloud contabo)

log() { echo "[punte] $*"; }
fail() { echo "[punte] EROARE: $*" >&2; exit 1; }
[[ $EUID -eq 0 ]] || fail "rulează ca root"
command -v python3 >/dev/null || fail "lipsește python3"
python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))' || fail "e nevoie de Python 3.10+"

# 1. cod
if [[ -d "$ROOT/.git" ]]; then
  git -C "$ROOT" fetch -q --depth 1 origin "$BRANCH"
  git -C "$ROOT" reset -q --hard FETCH_HEAD
else
  git clone -q --depth 1 --branch "$BRANCH" "$REPO_URL" "$ROOT"
fi
chown -R root:root "$ROOT"; chmod -R go-w "$ROOT"
log "cod: $(git -C "$ROOT" rev-parse --short HEAD)"
( cd "$ROOT" && python3 -B -m unittest discover -s channel_bridge/tests >/tmp/punte-teste.log 2>&1 ) \
  || fail "testele punții au picat pe server (vezi /tmp/punte-teste.log)"
log "teste punte: OK"

# 2. utilizator de serviciu
id "$SVC_USER" >/dev/null 2>&1 || useradd --system --no-create-home --shell /usr/sbin/nologin "$SVC_USER"
install -d -m 0700 -o "$SVC_USER" -g "$SVC_USER" "$STATE_DIR"

# 3. chei (generate o singură dată; nu sunt afișate niciodată)
install -d -m 0700 -o root -g root "$ENV_DIR"
umask 077
touch "$ENV_FILE"
for p in "${PEERS[@]}"; do
  var="KELION_CHANNEL_${p^^}_TOKEN"
  grep -q "^${var}=" "$ENV_FILE" || echo "${var}=$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')" >> "$ENV_FILE"
done
# OAuth pentru ChatGPT: secretul pe care doar Caddy îl adaugă după logarea Google și emailul proprietarului
grep -q '^KELION_CHANNEL_PROXY_SECRET=' "$ENV_FILE" || echo "KELION_CHANNEL_PROXY_SECRET=$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')" >> "$ENV_FILE"
grep -q '^KELION_CHANNEL_OWNER_EMAILS=' "$ENV_FILE" || echo "KELION_CHANNEL_OWNER_EMAILS=${OWNER_EMAILS:-adrianenc11@gmail.com}" >> "$ENV_FILE"
chmod 0600 "$ENV_FILE"; chown root:root "$ENV_FILE"
# Caddy primește doar secretul de proxy, în fișierul lui (0600, citit de systemd ca root)
if [[ -d /etc/caddy ]]; then
  grep '^KELION_CHANNEL_PROXY_SECRET=' "$ENV_FILE" > /etc/caddy/kelion-channel-proxy.env
  chmod 0600 /etc/caddy/kelion-channel-proxy.env; chown root:root /etc/caddy/kelion-channel-proxy.env
fi
log "chei: 5 medii în $ENV_FILE (doar root)"

# 4. serviciu
sed -e "s|@SERVICE_USER@|$SVC_USER|; s|@SERVICE_GROUP@|$SVC_USER|; s|@CHECKOUT_ROOT@|$ROOT|" \
  "$ROOT/channel_bridge/integrations/kelion-shared-channel.service.in" > "$UNIT"
systemctl daemon-reload
systemctl enable -q kelion-shared-channel.service
systemctl restart kelion-shared-channel.service
for i in $(seq 1 10); do curl -s -o /dev/null "http://127.0.0.1:$PORT/v1/health" && break; sleep 1; done
systemctl is-active -q kelion-shared-channel.service || { journalctl -u kelion-shared-channel -n 30 --no-pager; fail "serviciul nu pornește"; }
log "serviciu: activ pe 127.0.0.1:$PORT"

# 5. nginx
SNIP=/etc/nginx/snippets/kelion-channel.conf
CONF="$(grep -rlE 'server_name[^;]*kelionai\.app' /etc/nginx/sites-enabled /etc/nginx/conf.d 2>/dev/null | head -1 || true)"
if [[ -z "$CONF" ]]; then
  log "ATENȚIE: nu găsesc blocul nginx pentru kelionai.app; ruta publică nu e instalată"
else
  CONF="$(readlink -f "$CONF")"
  install -d /etc/nginx/snippets
  grep -v '^#' "$ROOT/channel_bridge/integrations/nginx-location.conf.example" > "$SNIP"
  if ! grep -q 'snippets/kelion-channel.conf' "$CONF"; then
    cp -p "$CONF" "$CONF.bak-punte"
    # inserează include în blocul HTTPS (cel cu listen 443), după linia server_name
    python3 - "$CONF" <<'PY'
import sys
p = sys.argv[1]; lines = open(p).read().split('\n'); out = []; depth = 0; block = []
# un bloc server{} care conține server_name kelionai.app și listen 443 primește include
def flush(b):
    text = '\n'.join(b)
    if 'kelionai.app' in text and '443' in text and 'kelion-channel.conf' not in text:
        for i, l in enumerate(b):
            if 'server_name' in l and 'kelionai.app' in l:
                b.insert(i + 1, '    include snippets/kelion-channel.conf;'); break
    return b
for l in lines:
    if depth == 0 and l.strip().startswith('server') and '{' in l:
        block = [l]; depth = l.count('{') - l.count('}'); continue
    if block:
        block.append(l); depth += l.count('{') - l.count('}')
        if depth <= 0: out += flush(block); block = []
        continue
    out.append(l)
out += block
open(p, 'w').write('\n'.join(out))
PY
  fi
  if nginx -t >/dev/null 2>&1; then
    systemctl reload nginx; log "nginx: ruta /kelion-channel/ publicată ($CONF)"
  else
    [[ -f "$CONF.bak-punte" ]] && cp -p "$CONF.bak-punte" "$CONF"; rm -f "$SNIP"
    nginx -t >/dev/null 2>&1 && systemctl reload nginx
    log "ATENȚIE: nginx -t a picat; am revenit la configurația anterioară"
  fi
fi

# 6. verificare pe fiecare mediu (cheile nu apar în output)
set -a; . "$ENV_FILE"; set +a
ok=0
for p in "${PEERS[@]}"; do
  var="KELION_CHANNEL_${p^^}_TOKEN"
  loc=$(cd "$ROOT" && KELION_CHANNEL_URL="http://127.0.0.1:$PORT" python3 -B -m channel_bridge.shared_client --participant "$p" health >/dev/null 2>&1 && echo "✅" || echo "❌")
  pub=$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer ${!var}" "$PUBLIC/kelion-channel/v1/health" || true)
  [[ "$pub" == 200 ]] && pubm="✅" || pubm="❌ (HTTP $pub)"
  [[ "$loc" == "✅" && "$pubm" == "✅" ]] && ok=$((ok+1))
  printf '[punte] %-8s local %s  public %s\n' "$p" "$loc" "$pubm"
done
log "rezultat: $ok/5 medii autentificate local și public"
[[ $ok -eq 5 ]]
