# Canal comun cu confirmări separate

Transport implementat pentru clienți autentificați: ChatGPT, Work, Kelion, mediul cloud/Codex și Contabo. Reutilizează `orchestration.report_outbox.ReportOutbox`; nu înlocuiește workerul, canalul Brain, Jobs, Live, backup sau orchestrarea modelelor. Codul nu a fost încă instalat pe Contabo și nu conectează singur conversațiile produselor.

## Contract

Ținta este **mediul cloud/Codex din această aplicație**, identificat prin participantul `cloud`. Nu există alias între identitatea veche `claude` și `cloud`; credențialele și mesajele istorice nu se transferă automat.

**Claude de la Anthropic este o a șasea identitate, opțională: `claude`** (cerută de Adrian pe 24.10.2026: Claude, Codex, Kelion și cei doi DOTS folosesc același context ordonat, cu identități separate). Ea există numai dacă hostul are propria credențială `KELION_CHANNEL_CLAUDE_TOKEN`, distinctă de toate celelalte; fără ea, puntea pornește exact cu cele cinci identități de mai jos și `claude` nu apare în `participants`. `claude` nu este alias pentru `cloud` (Codex) și invers: aceeași valoare pentru ambele e refuzată la pornire, iar un client care cere `--participant claude` cu credențiala `cloud` e refuzat. `claude` nu se obține prin OAuth (ca `cloud` și `contabo`), ci doar prin credențiala de serviciu.

- Un singur istoric SQLite privat, cu identitate de proprietar și identități distincte pentru cele cinci medii. Expeditorul este derivat din autentificare; câmpuri precum `sender` din JSON sunt refuzate.
- Fiecare mesaj are `id` stabil, `correlation_id`, text, destinatari și opțional `reply_to`. Implicit ajunge în inboxul fiecărui alt participant. Un răspuns păstrează audiența mesajului inițial și nu poate extinde accesul unui mesaj privat.
- Retrimiterea aceluiași ID/conținut este idempotentă. Același ID cu alt conținut, expeditor, corelație ori destinatari este refuzat.
- Citirea nu marchează mesajul primit. Fiecare destinatar confirmă explicit hashul primit; confirmarea Work nu confirmă și ChatGPT, mediul cloud/Codex sau Contabo.
- Confirmarea este numai `read_acknowledged`. Rezolvarea unei sarcini necesită în continuare execuția reală, output recuperat, verificare și răspuns în canalul de origine. Niciun ACK nu produce automat o stare „rezolvat”.
- Nu sunt invocate modele, nu sunt create abonamente și nu se face replay automat după timeout. După un rezultat de transport incert, se recitește ID-ul inițial.
- Folosiți un fișier de stare dedicat acestui canal, separat de alte outboxuri. Nu ștergeți istoricul ori cheile de deduplicare cât timp există clienți care pot retrimite. Cursorii reprezintă ordinea în baza păstrată; o recreare/exportare a bazei cere resynchronizare, nu reutilizarea oarbă a cursorilor.

## Host pe Contabo

Cerințe: Python 3.10+, checkoutul revizuit, un director de stare privat și cinci credențiale de serviciu distincte în mediul procesului. Configurați valorile prin mecanismul privat existent pe server, niciodată în Git/chat/loguri:

```text
KELION_CHANNEL_CHATGPT_TOKEN
KELION_CHANNEL_WORK_TOKEN
KELION_CHANNEL_KELION_TOKEN
KELION_CHANNEL_CLOUD_TOKEN
KELION_CHANNEL_CONTABO_TOKEN
```

Din rădăcina checkoutului:

```bash
python3 -B -m channel_bridge.shared_http \
  --state /var/lib/kelion-shared-channel/channel.sqlite \
  --owner kelion --port 8778 --public-origin https://kelionai.app
```

Hostul ascultă numai pe loopback. Directoarele/fișierele runtime sunt private, `umask 0077`. Instalați numai după inventarierea serviciilor și a rutelor reale; sursa de adevăr este Contabo. Exemplul systemd este un șablon care trebuie legat de utilizatorul de serviciu existent, fără modificarea altor servicii.

Publicați ruta prin proxy-ul HTTPS existent, păstrând Host/Origin autentice. Exemplul nginx este separat de configurația live și nu se aplică automat. Verificați configurația proxy înainte de reload. Nu expuneți portul 8778 direct pe Internet.

## Activarea identității `claude` (decizia lui Adrian)

1. În `channel.env` de pe Contabo (privat, `0600`, root), adaugă o singură dată o valoare nouă, distinctă: `KELION_CHANNEL_CLAUDE_TOKEN=<secrets.token_urlsafe(48)>`. Valoarea nu se pune în Git, chat sau loguri.
2. Repornește numai `kelion-shared-channel`; `health` pentru oricare identitate trebuie să listeze 6 participanți.
3. Credențiala se dă **numai** mediului Claude (Anthropic), prin mecanismul lui privat; Claude o folosește cu `--participant claude`. Fără pasul 1, nimic nu se schimbă.
4. Proba de acceptare: Claude citește inboxul, confirmă hashul fiecărui mesaj citit efectiv și trimite un răspuns corelat; ceilalți participanți îl recitesc cu `sender = claude`.

## Oglinda (`kelionai.app/app/oglinda.html`) — specificație, nu implementare

Oglinda trebuie să afișeze mesajele punții în același fir ordonat, cu semnătura derivată din autentificare: `Claude (Anthropic)` pentru `claude`, `OpenAI Codex (cloud)` pentru `cloud`, apoi `kelion`, `work`, `chatgpt`, `contabo`. Eticheta istorică `canal_claude_code` din Brain rămâne alias Codex și nu se afișează ca Claude. Implementarea aparține sursei oglinzii de pe Contabo (în afara acestui repo) și se face separat, cu aprobare.

## Interfețe

| Interfață | Operație |
| --- | --- |
| `POST /v1/messages` | Trimite `{id, correlation_id, text, recipients?, reply_to?}`; HTTP 201 înseamnă stocat |
| `GET /v1/inbox?after=0&limit=50&unread_only=true` | Recitește inboxul identității autentificate, maximum 100 mesaje/pagină și aproximativ 1 MiB de date structurate |
| `GET /v1/message/<id>` | Mesaj vizibil și lista exactă a confirmărilor |
| `POST /v1/ack` | `{id, sha256}`; confirmare numai pentru identitatea autentificată |
| `GET /v1/health` | Identitatea autentificată și capabilitățile; nu certifică conectarea aplicațiilor |
| `POST /mcp` | Streamable HTTP MCP, initialize/list/call; doar instrumente de mesaje |

Inboxul întoarce și `next_after`/`has_more`. Continuați de la `next_after` până la `has_more=false`; limita de octeți poate scurta o pagină înaintea limitei de mesaje.

MCP expune `kelion_channel_send`, `kelion_channel_read`, `kelion_channel_ack`, `kelion_channel_get`. Nu are shell, worker sau API de rulare a modelelor. Notificările MCP nu declanșează mutații.

## Clienți cloud/Codex și Contabo

Fiecare client primește numai propria credențială prin mediul său privat. `KELION_CHANNEL_URL` este rădăcina HTTPS reală publicată de proxy, de exemplu `https://kelionai.app/kelion-channel` **numai după instalarea acelei rute**.

```bash
python3 -B -m channel_bridge.shared_client --participant cloud health
python3 -B -m channel_bridge.shared_client --participant cloud read --unread-only
python3 -B -m channel_bridge.shared_client --participant cloud send \
  --id ID_STABIL --correlation-id TASK_ID --text 'mesajul efectiv'
python3 -B -m channel_bridge.shared_client --participant cloud ack ID_STABIL SHA256_PRIMIT
python3 -B -m channel_bridge.shared_client --participant cloud send \
  --id ID_RASPUNS --correlation-id TASK_ID --reply-to ID_STABIL --text 'rezultatul efectiv'
```

Pentru Contabo selectați `--participant contabo`; clientul folosește `KELION_CHANNEL_CONTABO_TOKEN`. CLI cere explicit `--participant` și selectează implicit variabila privată corespunzătoare identității: de exemplu `cloud` folosește `KELION_CHANNEL_CLOUD_TOKEN`. `--token-env` poate selecta altă variabilă, dar identitatea autentificată trebuie să coincidă. CLI nu acceptă valori de token în argumente. HTTPS păstrează proxy-ul și verificarea TLS; redirecturile sunt refuzate pentru a evita transmiterea credențialelor către alt host. Nu există retry automat al mutațiilor.

MCP stdio, pentru un client care poate lansa procese locale:

```bash
python3 -B -m channel_bridge.shared_client --participant cloud stdio
```

Clientul trebuie să păstreze variabilele injectate în memorie, fără dump de mediu. Exemplul Codex este în `integrations/codex-cloud.mcp.toml.example`; nu este instalat automat. Selectați endpointul HTTPS publicat efectiv și injectați privat propria credențială. Existența configurației nu dovedește că procesul curent a încărcat conexiunea.

## ChatGPT / Work / Kelion / cloud și WhatsApp

Aplicațiile ChatGPT/Work/Kelion/cloud necesită instalarea unei conexiuni MCP/connector **suportate efectiv de fiecare produs**, cu autentificarea compatibilă configurată oficial. Suportul bearer al acestui host nu presupune că orice interfață ChatGPT acceptă un antet arbitrar; dacă produsul cere OAuth, se integrează identitatea/fluxul OAuth existent după verificarea contractului real. Acest pachet nu înregistrează aplicații și nu acordă granturi de cont.

La începutul fiecărei sesiuni conectate: citește inboxul, recitește textul real, confirmă hashul și păstrează ID-ul la răspuns. Un listener de serviciu poate folosi aceeași interfață, dar trebuie instalat în runtime-ul real și verificat. MCP nu injectează automat mesaje în conversații arbitrare sau sesiuni închise.

WhatsApp Kelion nu este identificat în sursa disponibilă. Înaintea integrării se identifică pe Contabo providerul/serviciul, webhookul, identitatea contului, accesul existent, deduplicarea ID-urilor providerului și ruta de răspuns. Nu creați conturi, abonamente, tokenuri substitut sau integrare fictivă. După identificare, adaptorul existent Kelion publică mesajul cu ID stabil și returnează outputul în conversația WhatsApp originală; callbackul de livrare provider și recitirea răspunsului trebuie păstrate ca dovezi distincte. Nu există un adaptor WhatsApp implementat sau testat în acest pachet.

## Dovezi de acceptare

Testele locale exercită HTTP real și clienți în subprocessuri, nu serviciile reale ChatGPT/Work/Kelion/cloud/Contabo/WhatsApp:

```bash
python3 -B -m unittest discover -s channel_bridge/tests -v
python3 -B -m unittest discover -s orchestration/tests -v
```

Pentru închiderea cererii utilizatorului, păstrați pentru **fiecare mediu real**: identitate verificată, ID mesaj, SHA256 intrare, cerere recitită acolo, confirmare proprie, ID execuție, output efectiv, dovadă de verificare, răspunsul recitit în origine. WhatsApp necesită și ID-ul mesajului inbound/outbound și starea providerului. Repetați proba după restart/reconectare fără dublarea lucrării. Un test local, port deschis, health, mesaj stocat, ACK sau PR nu închide această acceptare.

În acest runtime, `codex mcp add --help` confirmă configurarea unui endpoint HTTP cu `--bearer-token-env-var`. Configurarea se face numai după ce endpointul și credențiala sunt disponibile. Exemplul de client stdio este verificat ca subprocess local din alt director; probele locale nu certifică instalarea în aplicațiile reale.

## OAuth pentru ChatGPT / Work / Kelion

ChatGPT conectează serverul MCP doar prin OAuth 2.1 (authorization code + PKCE S256), nu prin cheie introdusă manual. Puntea implementează acum (`channel_bridge/oauth.py`):

- descoperire: `/.well-known/oauth-protected-resource` și `/.well-known/oauth-authorization-server` (și variantele cu `/kelion-channel` la rădăcina domeniului); răspunsurile 401 trimit `WWW-Authenticate: Bearer resource_metadata=...`;
- înregistrare dinamică de client (`/oauth/register`), acceptată numai pentru callback-uri `https://chatgpt.com/connector/oauth/...`;
- `/oauth/authorize`: complet automat, fără pagină de ales. Merge doar după logarea Google a proprietarului prin oauth2-proxy (automată când e deja logat pe kelionai.app); Caddy adaugă un marker secret (`X-Kelion-Proxy-Auth`) pe care un proces local nu îl cunoaște. Identitatea vine din adresa conectorului: `.../mcp/chatgpt`, `.../mcp/work`, `.../mcp/kelion` (`.../mcp` simplu = chatgpt); `cloud`/`contabo` nu se pot obține prin OAuth, iar un token nu poate folosi adresa altei identități;
- `/oauth/token`: cod de unică folosință (120 s), token de acces 1 h, refresh 30 de zile cu rotație; tokenurile se păstrează doar ca hash SHA-256;
- cheile statice existente funcționează în continuare.

Configurare: `KELION_CHANNEL_PROXY_SECRET` și `KELION_CHANNEL_OWNER_EMAILS` în `channel.env` (scriptul de instalare le generează), rutele Caddy din `integrations/caddy-oauth.caddy.example`. Fără ele, OAuth rămâne închis (`/oauth/authorize` răspunde 403).

În ChatGPT: conector nou → Server URL după identitate (`https://kelionai.app/kelion-channel/mcp/chatgpt`, `.../mcp/work` sau `.../mcp/kelion`) → Authentication: OAuth (fără client ID/secret; se înregistrează singur) → Connect. Dacă proprietarul e logat pe kelionai.app, conectarea se termină singură.
