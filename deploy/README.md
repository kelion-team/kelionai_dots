# Deploy kelionai.app (web-v1) pe eveniment real

Deploy-ul pornește **numai** când GitHub trimite evenimentul real `push` pe `main`. Nu există timer sau verificare periodică.

```
merge în main ──► GitHub Actions (.github/workflows/deploy-web.yml) ──► POST https://kelionai.app/hooks/github cu token OIDC semnat de GitHub
                                                   ──► webhook-receiver.mjs (127.0.0.1:8767)
                                                   ──► systemctl start kelion-web-deploy.service
                                                   ──► auto-deploy-web.sh: copie de siguranță → fișiere noi → restart → verificare /api/config → revenire automată la eșec
```

- **Fără secret de copiat.** Workflow-ul cere de la GitHub un token OIDC (valabil câteva minute); receptorul îl verifică cu cheile publice GitHub și acceptă doar: emitent GitHub Actions, audiența `https://kelionai.app/hooks/github`, repo `kelion-team/kelionai_dots`, `refs/heads/main`, eveniment `push`. Un token nu poate fi folosit de două ori. Orice altceva primește 401 și este înregistrat ca `rejected`.
- Workflow-ul rulează doar dacă push-ul schimbă `site-live/web/**`. Rezultatul (cod HTTP, durată) apare și în GitHub → Actions.
- Push-urile venite în timpul unui deploy nu se suprapun: se face un singur deploy suplimentar, cu ultima versiune.
- **Fiecare eveniment este măsurat** în `/var/lib/kelion-deploy/events.jsonl` (și în `journalctl -u kelion-deploy-webhook`): `push_received` / `rejected` / `deploy_start` / `deploy_end`, cu ora, ID-ul rulării GitHub Actions, commit, autor, `duration_ms` și `ok`.
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
systemctl daemon-reload
systemctl enable --now kelion-deploy-webhook.service
systemctl start kelion-web-deploy.service      # primul deploy, cu versiunea curentă din main
```

**Proxy HTTPS:** în configurația existentă care servește kelionai.app (nginx sau Caddy), ruta `POST /hooks/github` se trimite la `http://127.0.0.1:8767/hooks/github`, înaintea rutei către aplicația web. Exemplu nginx:

```nginx
location = /hooks/github { proxy_pass http://127.0.0.1:8767/hooks/github; client_max_body_size 1m; }
```

**În GitHub nu e nimic de configurat**: workflow-ul `.github/workflows/deploy-web.yml` este deja în repo. Dacă un webhook a fost adăugat manual în Settings → Webhooks pentru această adresă, se șterge.

**Notă:** adresa `/hooks/github` nu se deschide în browser (răspunde 405); primește doar notificări POST de la GitHub Actions.

## Verificare

- Ultimele evenimente măsurate: `tail -n 20 /var/lib/kelion-deploy/events.jsonl`
- Receptorul: `systemctl status kelion-deploy-webhook --no-pager`
- În GitHub → Actions → „Deploy kelionai.app”: fiecare push cu codul HTTP și durata.
- Oprire: `systemctl disable --now kelion-deploy-webhook`
