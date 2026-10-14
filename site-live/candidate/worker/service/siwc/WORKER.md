# Worker SIWC finit și contractul privat

Cod pregătit, activare **PENDING**. Nu există grant SIWC, probă reală de inferență sau deployment produse de această lucrare. `worker.disabled.json` are `enabled:false`; comanda `node service/siwc/worker.mjs --once service/siwc/worker.disabled.json` se oprește înainte de a citi fișiere private ori de a porni un proces AppServer.

## Traseul implementat

Workerul citește configurația sa privată owner-only și validează legarea operator/task/runtime/cont, grantul SIWC, disponibilitatea curentă a cotei incluse și izolarea secretelor. Limita de trei intenții este o limită tehnică a implementării pentru un job nou, nu o cifră cerută expres de utilizator. Autorizarea existentă a scopului nu cere încă o ceremonie de aprobare. Nu există condiție de inferență anterioară reușită înainte de prima cerere.

Rezervă atomic inputul brut prin HTTP loopback, înainte de inferență. Execută exact Kelion selection → assessment canonic cu cinci câmpuri → controllerul original Cost Guardian/native_dispatch → munca aleasă → verificarea evenimentelor și `thread/read` → completare API și citirea jurnalului persistent. `task_input` este legat de inputul original de către adaptor; nu este cerut ca ecou de la model.

`controller_bridge.py` încarcă funcțiile originale prin căile publice existente și verifică SHA256 fix pentru toate cele patru fișiere core. Nu reproduce plannerul și nu schimbă instrucțiunile profilurilor canonice. Approval flag-ul original blochează munca; nu este șters sau rezolvat implicit.

Înainte de fiecare `turn/start`, serverul persistă un intent și crește contorul cumulativ în tranzacția SQLite originală. Se oprește după maximum trei intenții, inclusiv cererile cu acceptare necunoscută. Un task cu jurnal existent nu este rezervat din nou. Workerul nu are endpoint pentru a crea alt task și nu clonează probe istorice.

## API adăugat în server.py / store.py

Toate rutele de mai jos cer tokenul worker distinct, conexiune directă la `127.0.0.1`, Host exact cu port, fără Origin ori antete proxy. Tokenul client/MCP nu este acceptat. Nicio rută nouă nu este publicată pe internet de acest pachet.

| POST worker-only | Câmpuri exacte |
|---|---|
| `/v1/worker/runner/reserve` | `worker_id, task_id, authorization` |
| `/v1/worker/runner/status` | `task_id, runner_key` |
| `/v1/worker/runner/checkpoint` | `task_id, runner_key, phase, data, needs_reconcile, finished` |
| `/v1/worker/runner/turn-intent` | `task_id, runner_key, phase, data` |
| `/v1/worker/runner/prepare` | `task_id, runner_key, role, assessment, logic_validation_required` |
| `/v1/worker/runner/claim` | `task_id, runner_key, worker_id` |

`authorization` este exact `{task_id,input_sha256,runtime_sha256,authorization_sha256,max_turns:3,expires_at}`; expirarea este în secunde Unix. Hash-ul inputului este SHA256 al JSON-ului canonic al cererii brute. `runtime_sha256` leagă întregul runtime al serverului. `runtime.siwc_worker` trebuie să fie activat explicit și să conțină aceeași legătură task/input/autorizare/limită/expirare. Configurarea nouă nu este aplicată runtime-urilor reale existente.

Jurnalul și cheile de rezervare rămân private. Workerul comunică numai prin acest API, fără a deschide baza SQLite a ingressului sau a accesa fișierele altui UID. Endpointul existent `/v1/worker/complete` persistă rezultatul și receipt-ul cu task, runtime, model/efort selectate, thread, turn și hash de output.

## Activare necesară, fără valori inventate

Fișierul public de setări poate indica doar `{"enabled":true,"private_config":"/absolute/private/config.json"}` după îndeplinirea condițiilor. Fișierul de configurare privat trebuie să furnizeze:

- `runtime`: runtime identic cu serverul; scope-ul operațional este hash-ul runtime-ului fără subobiectele `siwc_worker` și `siwc_magentic`, pentru a evita o dependență circulară de hash. Include `workspace`, `permission_profile_sha256`, `protocol_sha256`, `executable_sha256`, `runtime_id`, manifestul original și dovezile de verificare.
- `worker_id`, `api_origin` numai HTTP 127.0.0.1 cu port, `worker_token_file`.
- `vault_root`, `vault_key_file`, `codex_home`, `operator_state_root`: directoare/fișiere private separate. Un marker anterior `once-reservation.json` se blochează; nu este șters automat.
- `python_executable`, `codex_executable`, `protocol_directory`, `protocol_sha256`: căi absolute și hash-uri. Protocoalele trebuie să corespundă `protocol-pins.json`; binarul trebuie să corespundă hash-ului runtime-ului autorizat.
- `authorization_file`, `readiness_file`: documente operaționale locale citite prin verificarea owner-only; vechiul nume `entitlement_file` este acceptat ca alias pentru readiness. `authority_public_key_file` este opțional și necesar numai dacă operatorul a ales deja documente semnate. Nu trebuie creată o autoritate Ed25519 pentru activare.

Documentul jobului este un obiect simplu sau `{payload}`; opțional se acceptă `{payload,signature}` Ed25519, cu verificare obligatorie când semnătura există. `kind:operator_bounded_siwc_job` păstrează task/input exacte, `runtime_scope_sha256`, `grant_fingerprint`, `max_turns:3`, `allowance_authorized:true`, `billing_mode:included`, `read_only:true`, `network_access:false`, `no_new_spend:true`, `new_task_only:true`, `expires_at` viitor cel mult o oră. Hash-ul payload-ului se leagă în runtime-ul serverului. Acestea sunt câmpuri locale ale adaptorului, nu câmpuri pretinse din API-ul OpenAI sau citate ale utilizatorului.

Readiness are `kind:siwc_account_readiness`, aceleași grant/runtime, expirare și `account_allowance:{available:true,billing_mode:included,observed_at,expires_at,source_ref}`. Observația cotei trebuie să fie reală și curentă, pentru contul selectat; `source_ref` indică proba privată existentă, fără tokenuri. Nu se inventează un endpoint de quota și nu se extrapolează din catalog. `credential_isolation_verified:true` și `credential_isolation_evidence_ref` descriu verificarea reală a protecției secretelor. Un fișier sau o semnătură nu transformă o afirmație în probă; datele sintetice sunt acceptate numai de testele marcate explicit.

Lista `completed_model_readbacks` nu mai este o condiție de pornire. Prima încercare limitată folosește grantul cu scope-urile incluse și configurația modelului ales de controller. Abia după evenimentul completed și readback-ul concordant, jurnalul înregistrează `access_evidence:completed_for_this_request_only` împreună cu thread/turn/model/efort configurate. Refuzul de acces sau cotă și acceptarea incertă se opresc fără retry. Acesta este fluxul de primă inferență descris în [Models and inference](https://developers.openai.com/siwc/token-sharing-open-source/models-and-inference) și [SIWC AppServer](https://developers.openai.com/siwc/token-sharing-open-source/codex-app-server).

## Izolarea și protocolul

`initialize` folosește KelionAI și experimentalApi=true, iar `initialized` se trimite numai după acknowledgement. Schema generată de CLI este verificată prin hash înainte de utilizare. `thread/start` și `turn/start` trimit `environments:[]`, workspace explicit, read-only/no-network, approvalPolicy never și approvalsReviewer user. Nu se inventează `readPolicy`: definiția generată `ReadOnlySandboxPolicy` conține doar type și networkAccess.

Providerul transmite ACCESS_TOKEN numai în mediul AppServer. Configurarea verificată a shell-ului folosește inherit core, default secret exclusions active, set gol și filtre pentru ACCESS_TOKEN, KEY/TOKEN/SECRET și KELION_*. Flagurile multi_agent, multi_agent_v2 și multi_agent_v2_dynamic_tools sunt dezactivate. În preflight-ul real `features list` al CLI 0.162.0-alpha.17.2, aceste trei flaguri și shell_tool/apps/plugins/hooks/browser/computer/code_mode_host au fost false. **unified_exec a rămas true în listă chiar cu flagul disable**; acest pachet nu declară izolare completă pe baza acelei configurații. Lipsa dovezii reale că procesele/tools nu pot citi secretul sau vault-ul blochează activarea. Read-only singur nu protejează confidențialitatea fișierelor.

Orice cerere RPC venită de la server care necesită răspuns — inclusiv approval — oprește fluxul. Nu se trimit aprobări automate. Timeoutul, EOF, outputul divergent, efectele neașteptate de tool sau un eșec HTTP conduc la needs_reconcile, fără replay. Readback-ul modelului/efortului este configurația thread-ului, nu telemetrie ascunsă per tură. Costul monetar efectiv rămâne necunoscut.

### Calea concretă Linux pentru confidențialitate

`DynamicUser` și `LoadCredential` protejează serviciul față de alte UID-uri; procesul și copiii săi cu același UID pot însă citi credentialele permise acelui serviciu. `PrivateMounts` separă vederea altor servicii. `WorkingDirectory` separat nu restrânge citirile. Aceste limite rezultă din [systemd Credentials](https://systemd.io/CREDENTIALS/) și [systemd.exec](https://raw.githubusercontent.com/systemd/systemd/main/man/systemd.exec.xml).

Există o alternativă oficială la ReadOnlySandboxPolicy: [profilurile de permisiuni](https://learn.chatgpt.com/docs/permissions). Schema locală pinuită acceptă `thread/start.permissions` și `turn/start.permissions`, care exclud respectiv `sandbox` și `sandboxPolicy`. Un profil dedicat poate refuza `:root`, permite numai `:minimal` și un workspace gol separat în mod read, refuza explicit vault-ul, directoarele de credențiale și CODEX_HOME, și dezactiva rețeaua. Accesul la `/proc` al procesului care poartă ACCESS_TOKEN trebuie de asemenea exclus și verificat; filtrarea env-ului copiilor singură nu ajunge.

Profilul `kelion_siwc_readonly` este implementat în `permissions.mjs`, transmis prin configurarea CLI și în câmpul `permissions` al ThreadStart/TurnStart. Readback-ul trebuie să păstreze `activePermissionProfile.id`; câmpurile legacy sandbox/sandboxPolicy nu sunt trimise. Pentru poll, toate fișierele operative se află sub `private_root`, plus LoadCredential, iar profilul refuză acele rădăcini întregi; hash-ul profilului rămâne stabil între joburi. Workspace-ul separat trebuie să fie gol înainte de execuție.

`linux-preflight.mjs` execută pe binarul Linux real numai `command/exec`, cu OAuth-shaped fixture sintetic, fără thread/turn și fără secret real. Verifică nouă rezultate: workspace read permis, ACCESS_TOKEN absent în shell, trei santinele private refuzate, `/proc/<appserver>/environ` și `/proc/self/environ` refuzate, scrierea și rețeaua loopback refuzate. Numai rezultatul observat permite readiness pentru confidențialitate. Preflight-ul Linux nu a fost executat aici. `DynamicUser`/`LoadCredential` rămân protecție între UID-uri, profilul verificat furnizează restricțiile tools.

## Magentic recuperat

`magentic-source-pins.json` fixează cele șase fișiere recuperate, nemodificate. `verifyMagenticSources` le verifică fără import de framework. `magenticReceipt` convertește numai un output readback legat de hash-ul cererii originale într-un receipt/response `native_host`, `native_surface:codex`. Atenuările sunt explicite: actual_model_attested=false, actual_effort_attested=false, model_execution_attested=false, cost monetar null. Nu declară rularea framework-ului.

`framework-cli.mjs` pornește subprocessul original `python -m orchestration.magentic_candidate.cli` numai când driverul îl cheamă, cu timeout finit, env filtrat și reverificarea celor șase surse înaintea fiecărei operații. `magentic-driver.mjs` execută `init → advance → pending`, leagă request_id/config/task/profil, obține assessment-ul participantului în cinci câmpuri, apelează controllerul original, înregistrează intent înainte de RPC, recuperează outputul actual și execută `dispatched → submit → readback`. Outputul original este păstrat într-un artefact privat cu hash-ul exact al octeților. Finalul se recitește prin `status` înainte de completarea taskului web. Niciun planner nu este reimplementat.

Acest cod este pregătit pentru framework-ul real fixat; aici a fost verificat prin fixture de contract și subprocess Python sintetic. Nu este o dovadă de execuție a framework-ului. Framework-ul general poate necesita mai mult de trei ture. Magentic are o limită tehnică per job configurabilă 1..128, separată de normalrunner=3 și de probele istorice. Limita din exemplul original `max_requests:32` nu este autorizație și nu stabilește bugetul de inferență.

API-ul separat `/v1/worker/magentic/` are operațiile `reserve`, `status`, `request`, `checkpoint`, `turn-intent`, `readback`, `operation`, `fail`, `complete`, `admit`. În afară de reserve/admit, baza exactă este `{task_id,runner_key,worker_id}`; request adaugă `{request}`, checkpoint/turn-intent `{request_id,phase,data}`, readback `{request_id,receipt,response}`, operation `{operation,result_sha256}`, fail `{reason}`, complete `{final,status_readback}`. Fazele sunt `magentic/<request_id>/<manager|assessment|work>` în același jurnal al taskului original. Cumulul include acceptările necunoscute; restartul nu îl resetează.

## Cererile owner din web

`node service/siwc/worker.mjs --poll SETTINGS.json` folosește politica privată `runtime.siwc_magentic.mode=owner_gateway`. Nu cere redeploy sau aprobare manuală pentru fiecare propoziție nouă. Limitele tehnice și activarea sesiunii sunt configurate o dată, în scopul deja autorizat. Serverul atașează un marker privat al bearerului client autentificat exclusiv cererilor `/v1/tasks`, fără a schimba raw inputul cu patru câmpuri sau hashul său. Markerul este ascuns în răspunsurile publice. Nu deduce identitatea Google din `origin`.

Politica conține `enabled`, `mode`, `dedicated_owner_gateway_client:true`, `gateway_client_token_sha256`, `frontend_receipt_client_token_sha256`, `grant_fingerprint`, `activated_at`, `expires_at`, `max_turns`, `max_jobs`, `max_session_turns`, `framework_template`. Cele două hashuri de client trebuie să corespundă efectiv bearerului dedicat gatewayului și receipt-ului de instalare frontend cu OIDC/allowlist verificat. Acest bearer nu poate fi distribuit unui client Chat/Work/MCP; altă integrare necesită altă cheie. Backendul verifică frontiera bearerului, nu pretinde să fi verificat el emailul Google.

`POST /v1/worker/magentic/admit {worker_id,policy_sha256}` selectează și rezervă atomic numai un task nou, autenticat cu acel client, primit după activare. Returnează `{admission:{reservation,authorization,framework_config,runtime_sha256}}` sau admission null cu motiv. Perioada este cel mult o oră; max_jobs 1..100, max_session_turns 1..512 și max_turns 1..128 sunt limite tehnice finite. Fiecare admitere rezervă conservator întregul max_turns în bugetul sesiunii. Jurnalele persistente păstrează acest consum la restart. Nu există recuperare automată a bugetului nefolosit, reset, clonă de task sau replay.

Poll-ul revalidează grantul/readiness înainte de fiecare admitere, persistă admission_intent înainte de HTTP și creează un director nou per task sub `session_jobs_root`. Starea sau lockul incert oprește pornirea următoare. După un job confirmat poate admite următoarea cerere, până la limita sesiunii; max_idle_polls și poll_ms îl fac finit chiar fără cereri. Nu se instalează timer sau restart automat. Structura `framework_template` conține participants canonici și limitele originale, fără task_id/objective/roles/framework_commit; adaptorul le leagă de inputul autentificat.

Instalatoarele și comenzile finite pentru verificare/autentificare sunt în [LINUX.md](LINUX.md).

## Probe

`node --test service/siwc/siwc.test.mjs service/siwc/worker.test.mjs` folosește OIDC/RPC sintetice, semnături de test și serverul Python original cu HTTP real și SQLite temporar. `SIWC_TEST_PYTHON` și `SIWC_TEST_PROTOCOL` pot indica executabilul Python și schema generată pe alt sistem. `python -m unittest discover -s service/siwc -p test_worker_http.py -q` verifică separat concurența, autorizarea exactă și crash/restart. Niciun test nu efectuează inferență, OAuth sau control remote.

Surse: [SIWC AppServer](https://developers.openai.com/siwc/token-sharing-open-source/codex-app-server), [configurarea oficială a mediului shell](https://learn.chatgpt.com/docs/config-file/config-advanced), schemele generate locale și cele patru fișiere originale cu hash fix din PROVENANCE.json.
