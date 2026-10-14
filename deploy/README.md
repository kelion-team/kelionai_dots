# Auto-deploy kelionai.app (web-v1)

După instalare, orice merge în `main` care schimbă `site-live/web/` ajunge singur pe kelionai.app în cel mult 5 minute. Dacă versiunea nouă nu pornește (`/api/config` nu răspunde `ready:true`), se revine automat la versiunea anterioară.

- Citește repo-ul public; nu folosește chei, parole sau tokenuri.
- Atinge doar `index.html`, `app.js`, `auth.mjs`, `server.mjs`, `style.css` din `/opt/kelion-app/web-v1`. Nu atinge `.env`, baza de date, sesiunile sau serviciul ingress.
- Copiile de siguranță: `/var/lib/kelion-deploy/backup-*` (ultimele 10).

## Instalare (o singură dată, ca root pe kelion-nou)

```bash
cd /tmp && rm -rf kd && git clone -q --depth 1 https://github.com/kelion-team/kelionai_dots.git kd
install -m 0755 kd/deploy/auto-deploy-web.sh /usr/local/bin/kelion-auto-deploy-web
install -m 0644 kd/deploy/kelion-web-deploy.service kd/deploy/kelion-web-deploy.timer /etc/systemd/system/
systemctl daemon-reload
systemctl start kelion-web-deploy.service      # primul deploy, imediat
journalctl -u kelion-web-deploy.service -n 20 --no-pager
systemctl enable --now kelion-web-deploy.timer
```

Dacă scriptul nu găsește singur serviciul web, adăugați în `kelion-web-deploy.service`, la `[Service]`: `Environment=WEB_SERVICE=<numele-unității>.service`, apoi `systemctl daemon-reload`.

## Verificare

- Jurnal: `journalctl -u kelion-web-deploy.service --no-pager | tail`
- Următoarea rulare: `systemctl list-timers kelion-web-deploy.timer`
- Oprire: `systemctl disable --now kelion-web-deploy.timer`
