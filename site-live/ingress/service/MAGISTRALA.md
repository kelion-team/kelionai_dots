# Magistrala Kelion

O singură cale pentru fiecare cerere de pe kelionai.app:

```
kelionai.app ─► ingress (awaiting_kelion) ─► magistrala_worker (long-poll, eveniment cerere nouă)
   ─► magistrala.route: suprafață + dificultate + raționament
        chat     = Codex CLI pe server cu model de chat (cota Codex/Work, NU cota ChatGPT)
        codex    = Codex CLI pe server (cota Codex/Work; raționament low→xhigh)
        work     = ChatGPT Work / agentul Kelion publicat (conectori, skill-uri)
        magentic = orchestratorul Microsoft Magentic cu cei 22 de DOTS
   ─► execuție ─► rezultat insuficient? escaladare automată, cel mai economic canal întâi:
        1. raționament mai mare pe aceeași suprafață (doar la răspuns insuficient; un eșec tehnic — cotă, login, model — nu se repetă mai scump)
        2. needs_code → codex, needs_tools → work
        3. suprafața următoare: chat → work → magentic, codex → magentic
   ─► rezultat real scris înapoi (result_received) sau blocked cu motivul exact
```

- **Rutarea** este deterministă (fără apel AI suplimentar): cuvinte-cheie de cod → codex; unelte/conectori → work; mai multe domenii sau pași → magentic; restul → chat. Dificultatea (1..4) crește cu lungimea, cerințele de analiză și numărul de pași, și stabilește nivelul de raționament.
- **Măsurare**: fiecare cerere și fiecare pas sunt înregistrate în `/var/lib/kelion-magistrala/events.jsonl` (`task_taken`, `hop` cu suprafață/efort/durată/rezultat, `task_finished`). Același istoric apare în rezultatul cererii (`receipt.hops`).
- **Fără succes fals**: un răspuns gol nu e succes; un backend căzut sau neconfigurat escaladează; dacă nicio suprafață nu răspunde, cererea devine `blocked` cu motivul.
- **Fără secrete în repo**: comenzile backend sunt în `/etc/kelion-magistrala/config.json`; tokenul worker-ului vine din fișierul de mediu al serviciului.

## Viteză pentru conversație

- `"reasoning": "minimal"` pe suprafața `chat` din config trimite la Codex raționament minim, indiferent de nivelul magistralei: răspuns mai rapid și mai ieftin pentru conversație. Lucrul (`codex`) rămâne pe nivelul ales de Kelion.
- În pagină, după fiecare frază rostită, Kelion confirmă imediat („Mă gândesc.”), apoi vine răspunsul; vorbitul îl întrerupe.
## Profilurile DOTS (22) pe magistrală

- Kelion alege profilul potrivit după cerere (ex. reparație → `dots_reparator`, loguri → `dots_loguri`, interfață → `dots_ux`, cerințe/documente → `dots_cerinte`); conversația simplă nu primește profil.
- Oricare profil se poate chema explicit: `@reparator …`, `@ux …`, `@dots_cerinte …` (numele, rolul sau numele fără `dots_`).
- Cererea pleacă spre backend cu instrucțiunile profilului (faza `work`); profilurile de cod merg pe suprafața `codex`.
- Monitorul și istoricul (`receipt.hops[].profile`) arată profilul care a lucrat.
- Registrul: `orchestration/native_roles.json`, copiat pe server în `/etc/kelion-magistrala/native_roles.json` (`profiles_path` în config). La pornire, worker-ul scrie `"dots_profiles": 22` în jurnal.

## Rute clare: ce consumă fiecare cerere

| Cerere | Ruta | Cota / plata |
|---|---|---|
| Text simplu | magistrala → `chat` = Codex CLI, model de chat | cota **Codex/Work** a contului ChatGPT |
| Cod / server / GitHub | magistrala → `codex` = Codex CLI | cota **Codex/Work** |
| Conectori (Gmail, Drive, Calendar…) | magistrala → `work` = agentul Kelion publicat (Workspace Agents) | cota **Codex/Work** + token Workspace Agents |
| Mai mulți pași / domenii | magistrala → `magentic` (DOTS) → Codex/Work | cota **Codex/Work** |
| Voce live / traducere T | browser → text → aceeași magistrală | cota **Codex/Work** |
| Chat/voce din aplicația ChatGPT | doar în ChatGPT, nu poate fi chemată din kelionai.app | cota **ChatGPT** (separată) |
| (opțional) OpenAI API / Realtime | server → API OpenAI | credite **API**, separate, în plafonul de 100 GBP |

### Ruta vocii

- microfonul deschide doar ruta audio, în kelionai.app; nu trimite utilizatorul în altă aplicație
- fiecare frază devine o cerere pe magistrală; Kelion alege canalul (chat / codex / work / magentic) și escaladează economic
- un blocaj se raportează pe monitor și apelul continuă să asculte

Cota Codex/Work la 0% (ChatGPT → Setări → Utilizare) înseamnă că toate rutele din kelionai.app se blochează, chiar dacă chat-ul și vocea din aplicația ChatGPT merg.

## Backend-uri

| Suprafață | Adaptor | Stare la instalare |
|---|---|---|
| chat | `magistrala-adapters/codex-exec.sh` (Codex CLI) cu un model de chat din config, sandbox read-only | activ — folosește contul ChatGPT deja autentificat în Codex pe server |
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
cp <clona repo>/orchestration/native_roles.json /etc/kelion-magistrala/native_roles.json   # cele 22 de profiluri DOTS
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
- Teste: `cd site-live/ingress/service && python3 -m unittest test_magistrala -v` (24 teste: rutare, escaladare, măsurare, preluare/finalizare atomică în store-ul real, worker cap-coadă cu backend comandă).
