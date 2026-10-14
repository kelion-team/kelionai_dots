# Magistrala Kelion

O singură cale pentru fiecare cerere de pe kelionai.app:

```
kelionai.app ─► ingress (awaiting_kelion) ─► magistrala_worker (long-poll, eveniment cerere nouă)
   ─► magistrala.route: suprafață + dificultate + raționament
        chat     = ChatGPT Astra 6.1 (raționament automat low→high)
        codex    = Codex (raționament automat low→xhigh)
        work     = ChatGPT Work / agentul Kelion publicat (conectori, skill-uri)
        magentic = orchestratorul Microsoft Magentic cu cei 22 de DOTS
   ─► execuție ─► rezultat insuficient? escaladare automată:
        1. raționament mai mare pe aceeași suprafață
        2. needs_code → codex, needs_tools → work
        3. suprafața următoare: chat → work → magentic, codex → magentic
   ─► rezultat real scris înapoi (result_received) sau blocked cu motivul exact
```

- **Rutarea** este deterministă (fără apel AI suplimentar): cuvinte-cheie de cod → codex; unelte/conectori → work; mai multe domenii sau pași → magentic; restul → chat. Dificultatea (1..4) crește cu lungimea, cerințele de analiză și numărul de pași, și stabilește nivelul de raționament.
- **Măsurare**: fiecare cerere și fiecare pas sunt înregistrate în `/var/lib/kelion-magistrala/events.jsonl` (`task_taken`, `hop` cu suprafață/efort/durată/rezultat, `task_finished`). Același istoric apare în rezultatul cererii (`receipt.hops`).
- **Fără succes fals**: un răspuns gol nu e succes; un backend căzut sau neconfigurat escaladează; dacă nicio suprafață nu răspunde, cererea devine `blocked` cu motivul.
- **Fără secrete în repo**: comenzile backend sunt în `/etc/kelion-magistrala/config.json`; tokenul worker-ului vine din fișierul de mediu al serviciului.

## Backend-uri

| Suprafață | Adaptor | Stare la instalare |
|---|---|---|
| chat | `magistrala-adapters/codex-exec.sh` cu modelul Astra din config, sandbox read-only | activ — folosește contul ChatGPT deja autentificat în Codex pe server |
| codex | același adaptor, modele Codex, efort până la xhigh | activ — idem |
| work | agentul Kelion publicat (Workspace Agents API, `orchestration/bridge.py`) | dezactivat până la tokenul Workspace Agents din ChatGPT Admin |
| magentic | worker-ul SIWC + Magentic din `site-live/candidate/worker` | dezactivat până la preflight-ul de izolare verde și grantul SIWC |

O suprafață dezactivată nu blochează magistrala: cererea escaladează la următoarea suprafață disponibilă.

Toate suprafețele consumă din creditele/limita contului ChatGPT. Fără credite, backend-urile răspund cu eroare, iar cererile devin `blocked` cu motivul.

## Instalare pe kelion-nou (o singură dată, ca root)

```bash
REL=/opt/kelion-app/ingress-v2/current/service
install -d -m 0700 /etc/kelion-magistrala /var/lib/kelion-magistrala
cp "$REL/magistrala-adapters/config.example.json" /etc/kelion-magistrala/config.json
# Modelele din config trebuie să existe în catalogul contului (verificați cu Codex pe server).
# codex_home = directorul în care Codex e deja autentificat (login-ul e per director/utilizator).
# worker.env: aceeași valoare KELION_WORKER_TOKEN ca serviciul ingress, plus PATH către codex:
#   KELION_WORKER_TOKEN=…   PATH=/opt/kelion-siwc/codex-…/bin:/usr/bin:/bin
install -m 0600 /dev/null /etc/kelion-magistrala/worker.env   # completat de operator, nu în repo
install -m 0644 "$REL/magistrala-adapters/kelion-magistrala.service" /etc/systemd/system/
systemctl daemon-reload && systemctl restart <serviciul ingress> && systemctl enable --now kelion-magistrala
```

Serviciul ingress trebuie repornit o dată pentru noile rute `/v1/worker/magistrala/take` `/progress` (monitorul live) și `/finish`.

## Verificare

- `journalctl -u kelion-magistrala -n 30 --no-pager` și `tail /var/lib/kelion-magistrala/events.jsonl`
- O cerere pe kelionai.app trebuie să ajungă la `result_received` cu răspunsul afișat, sau la `blocked` cu motivul.
- Teste: `cd site-live/ingress/service && python3 -m unittest test_magistrala -v` (17 teste: rutare, escaladare, măsurare, preluare/finalizare atomică în store-ul real, worker cap-coadă cu backend comandă).
