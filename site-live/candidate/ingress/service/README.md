# Kelion — adaptor local native-parent

Acest bundle pregătește serviciul comun pentru KelionAI.app. Rulează local, cu Python standard library (fără pachete noi). Nu a fost publicat și nu interceptează conversațiile. Adaptorul `native-parent` folosește un **părinte nativ explicit** cu unealta collaboration. Este implementat separat runnerul local finit `codex-app-server`, limitat la un job read-only; probele lui de agent sunt încă sintetice, iar descoperirea autentică și manifestul scoped preced execuția reală. Serverul HTTP, MCP și `local.py` nu lansează modele.

Include acum cele două conexiuni MCP necesare: stdio pentru un client Codex local și Streamable HTTP pentru un client remote Chat/Work care suportă o conexiune custom autentificată. Ambele expun numai intrarea brută și readback către aceeași bază Store; instalarea reală în produse rămâne separată.

În `core/` sunt copiate exact 4 fișiere din tree Git `6c5067a1f8c8819361b7c2de0cb4d7f3beb7d12c`: controllerul `native_dispatch.py`, `kelion_brain.py`, ruta Cost Guardian și registrul celor 22 de profiluri. `PROVENANCE.json` păstrează hashurile Git blob și SHA256. Constructorul verifică integritatea bundle-ului. `native_roles.json` furnizează instrucțiunile și limitele fiecărui profil; TOML-uri globale, OAuth, auth, pluginuri și skilluri cloud nu se copiază. Nu există dependență de `.runtime/` sau cale Windows fixată în cod.

## Intrare comună și selecție Kelion

Clientul trimite doar cererea brută; utilizatorul nu alege profilul, modelul sau dificultatea:

```json
{"task_id":"kelion-request-0001","origin":"codex","input_mode":"text","task":"Cererea concretă a utilizatorului"}
```

`origin` este `chat`, `work` sau `codex`; `input_mode` este `text` sau `voice_transcript`. Transcriptul trebuie furnizat deja ca text de suprafața care îl produce. Audio brut, STT/TTS și conectarea vocii nu sunt implementate.

Cererea devine `awaiting_kelion`. Părintele real Kelion citește intrarea, alege rolul și obține evaluarea reală task-bound a DOTS: `task_id`, `source_agent_id`, `task_input` identic, `difficulty` 1..4, `reason`, `risk_flags`. Apoi trimite intern:

```json
{"task_id":"kelion-request-0001","role":"lansare","assessment":{"task_id":"kelion-request-0001","source_agent_id":"agt_6acb4c0843d08191b4b4c0ffed5ec786","task_input":"Cererea concretă a utilizatorului","difficulty":1,"reason":"Evaluare reală a DOTS, obligatorie înainte de pregătire","risk_flags":[]}}
```

Exemplul arată schema; nu constituie o evaluare reală. Serverul HTTP nu automatizează selecția sau evaluarea: pentru `native-parent` ele aparțin părintelui Kelion. Runnerul local AppServer implementează cele două etape prin turns reale numai după gate-ul descris mai jos; fixtures nu dovedesc execuția lor autentică. Controllerul original selectează apoi model/efort din manifestul verificat **pentru acel runtime**. Un manifest al collaboration în aplicație nu verifică CLI-ul sau alt host. Configurile implicite neconfirmate nu inventează modele disponibile; pregătirea fără model verificat este blocată.

## Contract HTTP local

Serverul se leagă numai la `127.0.0.1`. Secretele `KELION_CLIENT_TOKEN` și `KELION_WORKER_TOKEN` trebuie furnizate prin mediu, distincte și de minimum 32 caractere; nu se scriu în repo sau exemple. Toate apelurile folosesc `Authorization: Bearer <token>` și POST `Content-Type: application/json`. Tokenul worker este rezervat părintelui Kelion.

| Metodă/rută | Principal | Date/rezultat |
| --- | --- | --- |
| POST `/v1/tasks` | client | Cerere brută; `awaiting_kelion`; idempotency prin `task_id` și hash intrare |
| GET `/v1/tasks/<task_id>` | client | Stare, output recuperat, hash și receipt; lease secret nu este returnat |
| GET `/v1/health` | client | Adaptor și scope; indică explicit necesitatea părintelui extern |
| GET `/v1/worker/awaiting` | worker | Următoarea intrare pentru selecția Kelion; citirea nu lansează lucru |
| POST `/v1/worker/prepare` | worker | `task_id`, `role`, `assessment`, opțional boolean `logic_validation_required` |
| POST `/v1/worker/prepared-tasks` | worker | Numai intern: `{request,assessment}` deja pregătite de Kelion |
| POST `/v1/worker/claim` | worker | `{worker_id}`; un singur lease global + `decision.spawn_request` |
| POST `/v1/worker/complete` | worker | Output efectiv + receipt exact de execuție + lease secret |
| POST `/v1/worker/fail` | worker | `task_id`, `lease_token`, `reason` după reconcilierea unei execuții eșuate |

`claim` nu execută nimic. Părintele execută o singură dată `spawn_request` cu modelul/efortul exact ales și `fork_turns=none`. Poate refolosi threadul assessment numai dacă modelul și efortul existente sunt exact aceleași. Citește apoi outputul real prin unealta nativă. Predarea internă este:

```json
{"task_id":"kelion-request-0001","lease_token":"LEASE_RETURNAT_PRIVAT","output":"OUTPUTUL_REAL_RECITIT","receipt":{"adapter":"native-parent","runtime_id":"SCOPE_EXACT_CONFIGURAT","native_agent_id":"IDENTITATEA_REALĂ_RETURNATĂ_DE_UNEALTĂ","model":"MODELUL_EXACT_ALES_DE_KELION","reasoning_effort":"EFORTUL_EXACT_ALES","status":"completed"}}
```

`result_received` înseamnă output păstrat și SHA256 calculat. `verified` rămâne false: serverul are încredere în atestarea părintelui autorizat, nu poate certifica independent unealta sau adevărul outputului. Receipt-ul nu este semnătură criptografică a platformei. Proba live trebuie păstrată separat. Modelele native consumă quota existentă; nu reprezintă utilizare zero-credit.

`task_id` leagă intrarea și rezultatul; schimbarea intrării la același ID dă 409. Predarea între suprafețe folosește GET cu același ID, fără resubmit modificat. SQLite serializează claimurile prin tranzacție `BEGIN IMMEDIATE`; un singur specialist poate fi leased sau în reconciliere. Expirarea lease-ului produce `interrupted_requires_reconcile`, fără relansare automată. După restart, lease-ul existent și outputul rămân durabile; parentul recitește execuția originală și completează cu același secret. Dacă secretul s-a pierdut, este necesară recuperarea lui din păstrarea privată a părintelui; serverul nu emite unul nou și nu presupune că runul poate fi repetat.

## Rulare și probe finite

Din rădăcina repo, folosește executabilul Python existent:

```text
python service/server.py --database results/repair-2026-10-13/service-state.sqlite3 --runtime results/repair-2026-10-13/service-parent-runtime.json --port 8765
python -m unittest discover -s service/tests -v
python service/probe_runtime.py --out results/repair-2026-10-13/service-cli-probe.json
```

`service-parent-runtime.json` din rezultate este scoped la părintele nativ al sesiunii actuale, cu numai modelele declarate de collaboration. Nu îl instala pe un host nou ca dovadă de acces. Manifestul gol implicit permite pregătirea fail-closed. Testele exercită funcțiile reale de controller, SQLite, concurența, HTTP loopback autentificat și procesul nou; evaluările/recepțiile din teste sunt **SYNTHETIC fixtures**, fără apeluri de model sau dovadă hosted.

### Verificarea reparată a CLI-ului

`probe_runtime.py` rezolvă directorul de stare **deja existent** folosind variabila oficială `CODEX_HOME` numai în mediul copilului. Folosește valoarea existentă dacă este furnizată, altfel directorul `.codex` din `USERPROFILE`, sau argumentul wrapperului `--existing-codex-dir`. Nu creează acel director, nu copiază autentificarea, nu citește tokenurile și nu schimbă mediul/global config. CLI-ul oficial face singur citirea autorizată a autentificării.

```text
python service/probe_runtime.py --catalog --out results/repair-2026-10-13/service-cli-probe-repaired.json
```

În contextul restricționat, `login status` a confirmat ChatGPT, exit 0. Proba AppServer programează `account/read`, `model/list` și `account/rateLimits/read` numai după initialize; startupul s-a oprit înainte de initialize, deci aceste trei apeluri nu au fost trimise în acea probă. Override-ul oficial `sqlite_home` a creat toate bazele SQLite în workspace; `Access is denied` apare ulterior, iar cauza finală exactă nu este stabilită. Nu atribuim acest ultim refuz SQLite-ului. Nu schimbăm ACL-uri, sandboxul sau configurația globală ca să îl ocolim.

Separat, coordonatorul a demonstrat în contextul său permis că același CLI 0.162 initializează AppServer și returnează un catalog real de 7 modele, fără stderr/refuz. Aceasta este o probă pozitivă scoped acelui context, nu acces universal. [Receipt catalog coordonator](../results/repair-2026-10-13/coordinator-appserver-catalog-receipt.json). Account type, permisiunea backend `ordinaryUsageAllowed` și execuția runnerului rămân distincte și trebuie verificate prin discover înaintea turns. Lista collaboration nu este folosită ca manifest CLI. Model strings din receipt sunt `gpt-6.1-sol`, `gpt-6-astra`, `gpt-6-sol`, `gpt-6-luna`, `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna`; politica controllerului existent folosește numai `low`, `medium`, `high` dintre nivelurile declarate, fără aliasuri inventate pentru cele superioare.

Referințe oficiale: [`CODEX_HOME`](https://learn.chatgpt.com/docs/config-file/environment-variables), [`sqlite_home` și `log_dir`](https://learn.chatgpt.com/docs/config-file/config-reference).

### Runner local finit: discover → un job

`local_runner.py` și `appserver_transport.py` folosesc schema generată de **executabilul oficial existent** înaintea metodelor. Schema operațională rămâne în `service/private/appserver-protocol`; pe o instalare nouă trebuie regenerată cu `codex app-server generate-json-schema --out <DIRECTOR_PRIVAT>`, fără inference. Schema/core/config globale nu sunt rescrise. Procesul stdio are stdin deschis pe toată sesiunea și reader threads pentru JSON-RPC/notifications; `communicate(input=...)` nu închide prematur conexiunea. Flagurile CLI oficiale `--disable multi_agent`, `--disable multi_agent_v2` și `--disable multi_agent_v2_dynamic_tools` sunt numai per-proces; `agents.enabled=false` nu este tratat ca dovadă de dezactivare. Nu se pornește daemon sau listener public.

Coordonatorul a verificat cu același CLI că aceste trei flaguri fac `features list` să raporteze toate cele trei valori false, exit 0, numai în procesul copil: [proba limitei de features](../results/repair-2026-10-13/appserver-feature-boundary-probe.json). Aceasta verifică setările, fără a măsura numărul total de inferențe interne.

```text
python service/local_runner.py discover --runtime-id <ID_EXACT_RUNTIME_LOCAL> --discovery service/private/appserver-discovery.json
```

Discover face numai initialize, account/read fără refresh forțat, model/list cu paginare finită și account/rateLimits/read. Persistă metadata sanitizată în `service/private`, cu hashul executabilului, al schemelor, catalogul efectiv și fingerprint SHA256 al identității contului. Nu salvează emailul/ID-ul brut, tokenuri sau balanțe de credit. Nu creează thread/turn și nu face inference. Rezumatul afișat conține hashul canonic `discovery_sha256`; o listă de modele nu certifică singură entitlementul.

Ownerul/părintele autorizat construiește apoi manifestul local pornind din `runtime.appserver.unverified.json`, numai din discovery reală. Sunt obligatorii: același runtime_id/execution_surface `codex`, workspace absolut existent autorizat, verification_evidence explicită, `discovery_sha256` canonic exact afișat de discover, `usage_authorization` cu `included_usage_authorized=true`, `billing_mode=included`, expirare finită și `max_turns=3`. Modelele manifestului trebuie să fie exact model strings și efforts existente în catalog, cu capacitate/cost_rank operaționale declarate; acestea sunt proxy-uri ordinale, nu preț măsurat. `native_spawn_supported` descrie aici bindingul de thread local prin adaptor, nu disponibilitatea collaboration sau execuția agentului cloud publicat. Nu copia manifestul collaboration în acest fișier și nu seta verified pe date fictive. Template-ul livrat este gol/blocat.

```text
python service/local_runner.py run-once --runtime-id <ID_EXACT_RUNTIME_LOCAL> --database <DB_COMUN> --runtime <MANIFEST_LOCAL_AUTORIZAT> --discovery service/private/appserver-discovery.json --turn-timeout 120
```

Gate-ul cere account type ChatGPT, identitate/catalog/executable/protocol neschimbate și **`ordinaryUsageAllowed=true`** din backend pentru consumul inclus, recitit înaintea fiecărei etape. Null/absent/false este blocaj; procentele, credit balance, autentificarea desktop sau catalogul nu inventează acest drept. Nu există fallback metered, cumpărare, key provisioning ori API paid. Workerul consumă quota existentă și nu este zero-credit. CLI-ul nu primește rol/model de la client; opționalul `--task-id` limitează alegerea la intrarea brută cu acel ID.

Un job are cel mult trei **turn/start cerute de client**, serializate: Kelion alege rolul din cele 22 de profiluri; DOTS ales furnizează assessment real task-bound; `native_dispatch.plan` original selectează model/effort de work, apoi adaptorul execută exact bindingul ales. Nu pretindem trei inferențe totale în backend: un turn poate avea mai multe cicluri de model/tool, iar telemetry internă nu este măsurată de acest client. Bootstrapul primelor două etape folosește ruta originală Cost Guardian pe sarcina de clasificare, fără un model global fix. JSON-urile sunt colectate din output efectiv și validate; instrucțiunile profilului original rămân intacte ca prefix pentru assessment și work, completate cu limita explicită locală read-only/fără rețea/fără subdelegare. Ambele hashuri sunt păstrate, fără cloud impersonation sau migrare presupusă a skills/OAuth.

Prima implementare execută **numai joburi locale read-only**: per-thread `approvalPolicy=never`, `sandbox=read-only`, `networkAccess=false`, cu binding efectiv verificat înainte de turn și recitit prin thread/resume după turn. Nu se schimbă politica globală. Politica never refuză operațiile care ar necesita aprobare; nu acordă permisiuni și nu permite scrieri/deploy. Orice server request de aprobare/user input/elicitation apărut totuși devine Attention: este păstrat privat, se cere interrupt când există turn_id, iar starea devine `interrupted_requires_reconcile`, fără răspuns de aprobare automat. Risk flags care cer aprobare sunt blocate de controllerul original; acesta nu are o intrare pentru a consuma un receipt de aprobare scoped, astfel încât runnerul nu inventează rezoluția. Pentru acele acțiuni este necesară o extindere autorizată și verificată a contractului controllerului, păstrând assessmentul real.

Fiecare intenție remote este înregistrată în SQLite **înainte** de apel, apoi sunt păstrate thread_id/turn_id, decizia controllerului și hashurile. Rezervarea acoperă și bootstrapul, astfel încât nu poate porni alt worker manual/local simultan. Oprirea procesului, timeoutul ori o aprobare pending nu provoacă replay; un proces nou găsește rezervarea și cere reconcilierea execuției originale. Secretele rezervării și lease-ului de work rămân în `service/private/runner`. Reconcilierea nu este un retry automat sau un daemon demonstrat.

Un turn completed fără output nu este succes. Runnerul compară outputul final primit prin evenimente cu outputul turnului exact recitit din thread/read, verifică model/effort/provider configurate și politica locală, apoi salvează receipt-ul AppServer și SHA256 prin Store.complete. Model/effort din Thread sunt **binding configurat**, nu telemetry de inference per-turn ascunsă; nu afirmăm mai mult. `result_received`/`verified=false` rămân distincte de verificarea funcțională independentă. Probele offline de runner și pipe IO sunt etichetate **SYNTHETIC**; nu substituie proba reală ce urmează în contextul coordonatorului.

### Conexiuni MCP pregătite

`mcp_stdio.py` citește și scrie JSON-RPC UTF-8 pe linii. stdout conține exclusiv mesaje de protocol. Launcherul necesită `KELION_CLIENT_TOKEN` securizat în mediul său; stdio folosește autoritatea procesului local, fără token în argumentele uneltelor. HTTP `/mcp` cere bearer client la fiecare apel. Secretul worker nu oferă ocolire prin MCP și uneltele worker nu sunt expuse.

```text
python service/mcp_stdio.py --database <SAME_DB_AS_SERVER_AND_KELION_PARENT>
```

Transportul HTTP se găsește în `server.py`, la `/mcp`. POST acceptă `initialize`, `ping`, `tools/list` și `tools/call`. Răspunsurile sunt JSON; notifications acceptate dau 202 fără body, iar GET/DELETE dau 405 deoarece nu sunt oferite SSE sau sesiuni. Clientul trebuie să trimită `Accept: application/json, text/event-stream`; versiunile acceptate sunt `2025-03-26` și `2025-06-18`. Headerul absent folosește fallback `2025-03-26`, cel necunoscut este refuzat. Host și Origin prezente sunt validate strict: default numai endpointul loopback; `--public-origin` poate adăuga o singură origine HTTPS explicită, fără wildcard. O notificare tools/call nu execută mutații.

Pentru deploymentul autorizat pe domeniu se poate configura `--public-origin https://KelionAI.app`. Originea trebuie să fie HTTPS, cu hostname DNS exact și port valid opțional; fără cale, slash final, userinfo, query, fragment, IP sau wildcard. Portul HTTPS implicit 443 este normalizat. Sunt admise numai Host-ul acelui domeniu și Origin-ul HTTPS exact, pe lângă loopback; subdomeniile și domeniile străine rămân refuzate. Bindul rămâne `127.0.0.1`, iar bearer-ul client rămâne obligatoriu. `X-Forwarded-Host` și `X-Forwarded-Origin` sunt ignorate ca autoritate, chiar dacă un proxy le trimite.

```text
python service/server.py --database <DB> --runtime <RUNTIME> --port 8765 --public-origin https://KelionAI.app
```

Aceasta este configurarea whitelistului, nu activarea TLS sau dovada publicării. Ownerul deploymentului trebuie să configureze un reverse proxy HTTPS controlat care transmite către listenerul loopback și păstrează Host/Origin reale corespunzătoare whitelistului. Fără opțiunea explicită, cererile care păstrează Host-ul domeniului sunt refuzate. Endpointul `http://127.0.0.1:8765/mcp` este exemplul/defaultul configurat; testele folosesc porturi efemere și nu dovedesc existența unui listener persistent la 8765.

Unelte: `kelion_submit` primește numai cererea brută descrisă mai sus; `kelion_get` primește numai `task_id`. Returnează starea/outputul din același Store. `awaiting_kelion` este acceptarea în coadă, nu execuție. Alegerea rolului, assessmentul și execuția rămân la părintele autorizat.

`integrations/codex-mcp.example.toml` este un template de revizuit, fără scriere în `.codex` global. `integrations/connection-review.json` este metadata reviewabilă pentru clientul remote, nu format de import al ChatGPT și nici confirmarea endpointului public. URL-ul public propus nu este verificat live. Autentificarea custom MCP trebuie configurată prin mecanismul suportat efectiv de fiecare produs.

Probele locale includ initialize/tools/list/tools/call/get în proces stdio autentic și server HTTP loopback autentic, pe aceeași DB, plus auth, Origin/Host, protocol, Accept și refuzul uneltelor worker. Aceste probe nu fac apeluri de model și nu certifică conectarea produselor sau interceptarea globală.

Referințe: [MCP transporturi](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports), [server MCP în pluginuri OpenAI](https://developers.openai.com/plugins/build/mcp-server).

`local.py` folosește exact același Store și elimină necesitatea listenerului pentru o probă nativă în sesiunea actuală. Operatorul local are autoritatea accesului la fișiere; acest CLI nu este endpoint client public.

```text
python service/local.py intake --database <DB> --runtime <RUNTIME> --input <RAW_JSON> --out <INTAKE_JSON>
python service/local.py prepare --database <DB> --runtime <RUNTIME> --input <SELECTION_JSON> --out <PLAN_JSON>
python service/local.py claim --database <DB> --runtime <RUNTIME> --input <WORKER_JSON> --out <PRIVATE_CLAIM_JSON>
python service/local.py complete --database <DB> --runtime <RUNTIME> --input <PRIVATE_RESULT_JSON> --out <RESULT_JSON>
python service/local.py get --database <DB> --runtime <RUNTIME> --task-id <TASK_ID> --out <READBACK_JSON>
```

`WORKER_JSON` este `{ "worker_id": "kelion-parent-0001" }`. Nu tipări conținutul fișierului privat claim sau secretul lease în chat ori probe publice. Ultimul GET trebuie rulat într-un proces nou și comparat cu hashul octeților outputului efectiv. Niciun CLI de mai sus nu lansează agenți.

Păstrează claimul și inputul completion în `service/private/` (gitignored), cu acces numai pentru operator. DB-ul păstrează doar SHA256-ul secretului lease. JSON-urile publice de rezultat/readback nu returnează secretul. Nu publica DB-ul complet: acesta conține intrarea și outputul sarcinii.

## Control extern indispensabil pentru activare

Gazda existentă a fost identificată cu acces real Remote Desktop Commander: **kelion-nou**, Linux, cu sursa repo staged la `/opt/kelion/staging/kelionai_dots-6d10a90`, manifest `source-staged-not-activated` și 81 fișiere. Stagingul nu este activare și nu dovedește că noul bundle/runner a fost instalat. Nginx/Caddy/cloudflared nu au fost găsite în căile probate; nu deducem absența lor de pe întregul host. Execuția shell remote a fost refuzată automat în contextul root curent, iar acel refuz nu este ocolit. Controlul indispensabil este executarea autorizată a activării pe **această gazdă existentă**, cu ruta HTTPS, volum durabil și runtime eligibil; nu mai este cerut un link generic pentru o găzduire necunoscută. Nu a fost demonstrat un daemon hosted autonom.

Installerul reversibil `deploy/install_ingress.py` pregătește activarea **numai ingressului** pe kelion-nou: loopback, SQLite persistent, user system fără login, systemd și `--public-origin https://KelionAI.app`. Generează pe host tokenuri distincte client/worker root-only, fără afișare; nu copiază auth desktop și nu instalează worker hosted. Contractul exact, pachetul verificat și rollbackul sunt în `results/repair-2026-10-13/deploy/EXECUTE.md` din workspace. Probele locale includ integritate ZIP, refuz paths private, rollback cu date păstrate și metadata MCP pe loopback autentic; systemd/host sunt fixtures declarate, fără activare remote. Ownerul trebuie să activeze prin controlul autorizat al gazdei, să configureze/verifice TLS/reverse proxy cu Host/Origin reale păstrate și să expună numai `/mcp`, păstrând endpointurile worker private. Nu este necesară cumpărarea unui API nou în adaptorul livrat. Pentru fiecare Chat/Work/Codex este necesară instalarea/conectarea explicită a unei căi suportate care poate apela intrarea comună și reciti taskul; conversațiile existente nu sunt interceptate automat. Pentru voce trebuie verificată și calea reală care livrează transcriptul și consumă rezultatul. Aceste conectări și deployul rămân în lucru, fără probe live fabricate.

Prima încercare reală de runner a fost respinsă la `thread/start`, înainte de `turn/start`. Diagnosticul separat al coordonatorului, cu zero turnuri, a demonstrat exact mesajul `thread/start.historyMode requires experimentalApi capability`; negocierea `capabilities.experimentalApi=true` este acum aplicată în initialize. Error message/data backend sunt păstrate numai în artifacts private; ieșirea publică include doar metoda/codul. `diagnose_thread_start.py` este un diagnostic finit fără turn/start sau replay al jobului și nu trebuie rulat încă o dată după dovada obținută. Fixul protocolului nu substituie dovada completării unei execuții; reconcilierea jobului inițial și proba reală aparțin coordonatorului. Un output cu SHA corect nu este singur dovadă de execuție terminal: itemurile efective commandExecution din thread/read trebuie verificate separat dacă această dovadă este cerută.

După fixul initialize, execuția reală a coordonatorului a produs două turnuri (selecție și assessment, gpt-6-luna/low), apoi s-a oprit: ecoul task_input al assessmentului a fost trunchiat (454 din 727 caractere); work nu a început. Jobul rămâne `needs_reconcile`, iar acel output nu este editat sau promovat. Pentru **joburi viitoare**, schema assessment are exact cele cinci câmpuri cerute de profil (task_id, source_agent_id, difficulty, reason, risk_flags). IDs, tipurile și valorile sunt validate din outputul real recitit; părintele adaugă task_input exact din Store la envelope-ul de șase câmpuri cerut de core-ul original. Jurnalul păstrează SHA inputului/promptului/outputului raw și thread/turn efective. Aceasta este proveniență de input imuabil, nu dovadă că modelul a evaluat fiecare caracter și nu reparare a assessmentului vechi.

`manual_resume.py` implementează acum recuperarea locală separată, **neautorizată implicit**. `prepare` creează numai un artifact privat cu `authorized=false`, expirare zero și ref human absent; `check`/`resume` refuză înainte de orice RPC cât acestea lipsesc. Autorizarea strictă, separată de manifestul normal max3, trebuie să lege task/runtime/account/discovery, inputSHA, journalSHA și hashurile manifestelor vechi/noi, exact două turnuri existente + două noi = maximum patru client turn/start cumulativ, included/read-only/no-network, expirare și referința aprobării umane. Referința este atestarea operatorului local de încredere, nu un grant backend sau dovadă criptografică a aprobării; codul nu o generează și nu setează true automat.

Recuperarea permite numai cazul exact de assessment cu prefix trunchiat, două turnuri completate cu IDs/readback reale, fără work/lease/intent necunoscut. Folosește DB-ul original `.runtime/appserver-native-live/tasks.sqlite3` sau un DB operator existent în `service/private`, fără clone. Runtime/discovery/authorization/reservation rămân private. Recitește **ambele** thread/turn originale, verifică outputSHA/config binding și proveniența promptului, apoi o tranzacție arhivează jurnalul și manifestul/hashul vechi înainte de eventuala reînnoire a expirării runtime-ului. Nu schimbă manifestul de modele, workspace-ul sau politica max3 normală. Assessmentul eșuat și selecția originală rămân nemodificate; faza nouă este `dots_assessment_recovery`, urmată de work prin controllerul original. Contorul cumulativ este persistat înainte de turn/start (index3, index4), iar orice timeout/Attention blochează replay-ul inclusiv după proces nou. `run-once` normal rămâne max3 și are și el contor durabil înainte de RPC. Contractul cu comenzi exacte este `results/repair-2026-10-13/deploy/RECOVERY-NOT-AUTHORIZED.md`. Recuperarea este testată numai cu fixtures **SYNTHETIC**, nu executată pe jobul real; nu există autorizare pentru încă două turnuri în această livrare.

**Eligibilitatea inferenței hosted este un control separat de provider/domeniu:** documentația AppServer precizează că autentificarea sa locală/open-source nu a fost permisă pentru servicii hosted/comerciale. Pentru KelionAI.app este necesară o cale oficială eligibilă, de exemplu **Sign in with ChatGPT** cu client înregistrat/aprobat și scope/consum confirmate, sau un alt canal oficial deja autorizat. Loginul desktop reușit nu acordă acest drept; nu exportăm tokenurile lui. Înrolarea/clientul eligibil și autentificarea prin fluxul suportat sunt controlul rezervat ownerului/administratorului, fără granturi presupuse ori API metered lansat automat. [Autentificarea AppServer](https://learn.chatgpt.com/docs/app-server#authentication), [integrarea oficială SIWC și AppServer](https://developers.openai.com/siwc/token-sharing-open-source/codex-app-server).

Referință de runtime: [documentația oficială Codex App Server](https://learn.chatgpt.com/docs/app-server). [Documentația oficială despre catalog vs acces la model](https://developers.openai.com/siwc/token-sharing-open-source/codex-app-server) precizează că o listă de modele nu substituie o execuție completată. Acest bundle implementează numai adaptorul explicit native-parent și nu exportă autentificarea din documentație.
