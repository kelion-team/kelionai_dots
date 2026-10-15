# Masca kelionai.app peste Codex app-server

Masca afișează în kelionai.app operațiile reale ale `codex app-server` de pe kelion-nou, 1:1 după schema
generată (`orchestration/app-server-schema`, Codex 0.162.0-alpha.17.2). Nimic nu se simulează în pagină.

```
browser ─► kelionai.app (/api/app/*, sesiune Google + CSRF, doar contul permis)
        ─► puntea kelion-mask (127.0.0.1:8775, token KELION_MASK_TOKEN)
        ─► codex app-server (ws://127.0.0.1:18767/, JSON-RPC)
```

## Ce acoperă masca

| În pagină | Operația din schemă |
|---|---|
| Conversație nouă, trimitere | `thread/start`, `turn/start` (input text + `localImage`) |
| Trimitere în timpul rulării / Oprește | `turn/steer` / `turn/interrupt` |
| Istoric, căutare, arhivate, „Mai multe” | `thread/list` (searchTerm, archived, cursor) |
| Deschiderea unei conversații | `thread/resume` (turns + items); „Mesaje mai vechi”: `thread/turns/list` cu `turnsBackwardsCursor`, `sortDirection: desc`; turnuri sumare completate cu `thread/items/list` |
| Redenumește, ramifică, arhivează, dezarhivează, compactează, șterge | `thread/name/set`, `thread/fork`, `thread/archive`, `thread/unarchive`, `thread/compact/start`, `thread/delete` |
| Model și efort | `model/list` (supportedReasoningEfforts), `model` + `effort` în `turn/start` |
| Aprobări și sandbox | `approvalPolicy`, `sandbox` (la `thread/start`), `approvalPolicy` la `turn/start` |
| Răspuns în flux | `item/agentMessage/delta`, `item/reasoning/summaryTextDelta`, `item/commandExecution/outputDelta`, `item/started`, `item/completed`, `turn/started`, `turn/completed`, `turn/plan/updated`, `error` |
| Elemente afișate | userMessage, agentMessage, reasoning, plan, commandExecution, fileChange, mcpToolCall, webSearch, imageView, imageGeneration, contextCompaction, review; restul fidel ca date |
| Cereri ale serverului | `item/commandExecution/requestApproval`, `item/fileChange/requestApproval`, `execCommandApproval`, `applyPatchApproval`, `item/tool/requestUserInput`, `mcpServer/elicitation/request` |
| Imagini | `fs/createDirectory` + `fs/writeFile` (doar în directorul de încărcări), afișare cu `fs/readFile` |

Atașamente: masca trimite **doar imagini** (`localImage`, maximum 8 MB fiecare). `thread/attachment/*` (atașamente
opace cu `attachmentType`/`identityKey`/`payload`) nu este folosit de mască, deci atașamentele generale nu sunt acoperite.

Trimiterea: textul și imaginile rămân în compozitor până la confirmarea app-server. O eroare a app-server înseamnă
„netrimis”; o eroare de rețea sau un timp depășit înseamnă „trimitere incertă”, afișată ca atare, fără retrimitere automată.
| Skills, Pluginuri, Aplicații, Servere MCP | `skills/list`, `plugin/list`, `app/list`, `mcpServerStatus/list` |
| Cont și limite | `account/read`, `account/rateLimits/read`, `account/usage/read` |
| Funcții | lista metodelor permise și a celor blocate, cu motivul |

Blocate implicit (motivul apare în pagină și în `/v1/methods`): autentificarea contului, consumul de credite și
e-mailul de credite, `command/exec*` și `thread/shellCommand`, `fs/remove`, `fs/copy`, scrierile de configurație,
instalarea de pluginuri/marketplace, OAuth MCP nou, `feedback/upload`, Windows. Se activează doar prin
`"enable": [...]` în `/etc/kelion-mask/config.json`, cu decizia lui Adrian.

Vocea nu trece prin mască: vocea este apelul Kelion DOTS din aplicația DOTS.

## Instalare pe kelion-nou

```bash
REPO=<clona kelionai_dots la ramura măștii>
install -d -m 0755 /opt/kelion-app/mask /etc/kelion-mask
cp "$REPO/site-live/ingress/service/app_server_client.py" "$REPO/site-live/ingress/service/app_server_methods.json" /opt/kelion-app/mask/
cp "$REPO/site-live/ingress/service/mask.config.example.json" /etc/kelion-mask/config.json
TOKEN=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')
install -m 0600 /dev/null /etc/kelion-mask/mask.env && echo "KELION_MASK_TOKEN=$TOKEN" > /etc/kelion-mask/mask.env
# același token în mediul serverului web: KELION_MASK_TOKEN=$TOKEN
install -m 0644 "$REPO/site-live/ingress/service/kelion-mask.service" /etc/systemd/system/
systemctl daemon-reload && systemctl enable --now kelion-mask
# serverul web: index.html, app.js, style.css, server.mjs din site-live/web, apoi repornirea serviciului web
```

Directorul de încărcări trebuie să poată fi scris de utilizatorul care rulează app-server-ul.
App-server-ul trebuie să ruleze permanent (serviciu propriu), pe 127.0.0.1:18767.

## Verificare

- `curl -s -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8775/v1/health` → `"connected": true`
- `/api/config` pe kelionai.app → `"mask": true`; punctul din colțul paginii e verde
- istoricul apare din `thread/list`; o conversație deschisă arată turnurile reale
- un mesaj trimis produce răspuns în flux (necesită credite în workspace)
- teste: `python3 -m unittest test_app_server_client -v`
