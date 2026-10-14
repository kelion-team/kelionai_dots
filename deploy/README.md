# Deploy kelionai.app (web-v1) pe eveniment real

Deploy-ul pornește **numai** când GitHub trimite evenimentul real `push` pe `main`. Nu există timer sau verificare periodică.

```
merge în main ──► GitHub webhook (push, semnat) ──► https://kelionai.app/hooks/github
                                                   ──► webhook-receiver.mjs (127.0.0.1:8767)
                                                   ──► systemctl start kelion-web-deploy.service
                                                   ──► auto-deploy-web.sh: copie de siguranță → fișiere noi → restart → verificare /api/config → revenire automată la eșec
```

- Receptorul acceptă doar cereri semnate cu secretul webhook-ului (`X-Hub-Signature-256`), doar `push` pe `refs/heads/main` din `kelion-team/kelionai_dots`. Orice altceva primește 401/202 și nu face nimic.
- Push-urile fără schimbări în `site-live/web/` sunt ignorate (și înregistrate).
- Push-urile venite în timpul unui deploy nu se suprapun: se face un singur deploy suplimentar, cu ultima versiune.
- **Fiecare eveniment este măsurat** în `/var/lib/kelion-deploy/events.jsonl` (și în `journalctl -u kelion-deploy-webhook`): `push_received` / `push_ignored` / `deploy_start` / `deploy_end`, cu ora, ID-ul livrării GitHub, commit, cine a făcut push, `duration_ms` și `ok`.
- Atinge doar `index.html`, `app.js`, `auth.mjs`, `server.mjs`, `style.css` din `/opt/kelion-app/web-v1`. Nu atinge `.env`, baza de date, sesiunile sau serviciul ingress. Copiile de siguranță rămân în `/var/lib/kelion-deploy/backup-*`.

## Instalare (o singură dată, ca root pe kelion-nou)

```bash
cd /tmp && rm -rf kd && git clone -q --depth 1 https://github.com/kelion-team/kelionai_dots.git kd
install -m 0755 kd/deploy/auto-deploy-web.sh /usr/local/bin/kelion-auto-deploy-web
install -d -m 0755 /usr/local/lib/kelion-deploy
install -m 0644 kd/deploy/webhook-receiver.mjs /usr/local/lib/kelion-deploy/
install -m 0644 kd/deploy/kelion-web-deploy.service kd/deploy/kelion-deploy-webhook.service /etc/systemd/system/
# Dacă a fost instalat timerul vechi, se oprește și se șterge:
systemctl disable --now kelion-web-deploy.timer 2>/dev/null; rm -f /etc/systemd/system/kelion-web-deploy.timer
# Secretul webhook-ului (rămâne doar pe server și în setările GitHub):
install -d -m 0700 /etc/kelion-deploy
[ -s /etc/kelion-deploy/webhook-secret ] || (umask 077; head -c 48 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 48 > /etc/kelion-deploy/webhook-secret)
systemctl daemon-reload
systemctl enable --now kelion-deploy-webhook.service
systemctl start kelion-web-deploy.service      # primul deploy, cu versiunea curentă din main
```

**Proxy HTTPS:** în configurația existentă care servește kelionai.app (nginx sau Caddy), ruta `POST /hooks/github` se trimite la `http://127.0.0.1:8767/hooks/github`, înaintea rutei către aplicația web. Exemplu nginx:

```nginx
location = /hooks/github { proxy_pass http://127.0.0.1:8767/hooks/github; client_max_body_size 1m; }
```

**Webhook în GitHub** (îl adaugă Adrian, o singură dată): repo `kelionai_dots` → Settings → Webhooks → Add webhook:
- Payload URL: `https://kelionai.app/hooks/github`
- Content type: `application/json`
- Secret: conținutul lui `/etc/kelion-deploy/webhook-secret` (agentul i-l arată lui Adrian o singură dată, în privat; nu se pune în repo sau în chat public)
- Events: **Just the push event** → Add webhook

GitHub trimite imediat un `ping`; în pagina webhook-ului trebuie să apară bifa verde (răspuns 200 „pong”).

## Verificare

- Ultimele evenimente măsurate: `tail -n 20 /var/lib/kelion-deploy/events.jsonl`
- Receptorul: `systemctl status kelion-deploy-webhook --no-pager`
- În GitHub → Settings → Webhooks → Recent Deliveries: fiecare livrare cu codul de răspuns.
- Oprire: `systemctl disable --now kelion-deploy-webhook`
