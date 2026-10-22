# KelionAI agent orchestration rules (Codex / repository)

- **MANDATORY BEFORE DELEGATION:** read and follow [`orchestration/SOP-DELEGARE.md`](orchestration/SOP-DELEGARE.md), then `orchestration/README.md` and GitHub issue #4. Treat the SOP as the project handoff/verification contract on every new execution.
- Reuse the agent registry. Distinguish `agt_...` identity from `agtch_...` official published API trigger channel.
- Never claim delegation from route recommendations, a GitHub issue, or a Slack message. A confirmed API 202 is accepted dispatch, not agent completion.
- Use `orchestration/bridge.py`; perform no live trigger without authorization, exact agent and channel IDs, safe key handling, and cost check.
- Verify run state and retrieve the **actual output** through an authorized path such as a result attached by the agent to a GitHub issue. Readback is mandatory before setting verified.
- Work on one active user priority; don't start unrelated queued projects. Do not add subscriptions, API credits, or unsafe personal shared connector accounts.

## REGULĂ OBLIGATORIE — continuitate, finalizare verificată și cost zero (12 octombrie 2026)

- **O singură lucrare activă:** utilizatorul a prioritizat delegarea reală către agenții KelionAI existenți, apelabili din ChatGPT, Work și Codex. Lucrările secundare rămân în coadă, fără a înlocui sarcina curentă.
- **Asistentul NU decide unilateral oprirea, abandonarea sau mutarea sarcinii active în pending/standby.** Absența unei chei, o eroare de instrument sau un obstacol tehnic declanșează investigare, remediere și căutarea unei căi oficiale alternative, nu închiderea lucrării. Întreabă utilizatorul doar când o acțiune a sa este indispensabilă.
- **Rezolvare înainte de escaladare:** reutilizează autentificările și integrările existente, verifică dependențele, creează/configurează componentele lipsă când sunt disponibile și autorizate, rulează probe finite și citește rezultatul înapoi. Nu repeta acțiuni deja reușite și nu re-cere o aprobare generală deja dată. Respectă totuși aprobările specifice cerute de platformă.
- **Fără costuri noi:** nu cumpăra abonamente, credite, trialuri cu facturare și nu lansa apeluri facturabile nevalidate. Lipsa unui serviciu gratuit nu justifică declararea obiectivului drept finalizat; identifică exact limita și continuă pașii independenți și fără cost.
- **Cheia corectă, nu una substitut:** pentru Workspace Agents este necesar un *Workspace Agent access token*, creat oficial în ChatGPT Admin > Access tokens, cu Workspace Agents scope, plus canalul agentului `agtch_...`. Cheile OpenAI Platform `sk-...` NU înlocuiesc acest token. Nu salva secrete în chat, repo sau Library; nu ocoli MFA sau aprobările.
- **Criteriu de încheiere:** un agent existent primește efectiv sarcina, execută, produce un rezultat accesibil și acesta este recitit/verificat; apoi demonstrează predarea între ChatGPT, Work și Codex. Testele locale, PR-ul integrat, un mesaj Slack sau HTTP 202 singure NU dovedesc finalizarea.
- **Transparență:** când o etapă depinde efectiv de un control rezervat utilizatorului/administratorului, indică precis controlul și de ce e necesar; nu pretinde nici că l-ai executat, nici că poți continua independent după ce accesul chiar lipsește. Starea rămâne ÎN LUCRU, nu „gata”.


## PLAFON DE PLATĂ — bătut în cuie (stabilit de Adrian, 14 octombrie 2026)

- **Plafon total: 100 GBP.** Nicio plată, credit, abonament sau reîncărcare care ar duce totalul peste 100 GBP. Fără excepții, fără „temporar”.
- **Tranșe: maximum 10 GBP per plată / reîncărcare.** Nicio tranșă mai mare.
- Orice plată se face doar de Adrian, cu aprobarea lui explicită pentru fiecare tranșă; agenții nu introduc date de plată și nu cumpără credite.
- Reîncărcarea automată nu se setează peste 10 GBP per tranșă și nu poate depăși plafonul total.
- Înainte de orice consum facturabil, se verifică totalul plătit până atunci; la atingerea plafonului, execuțiile facturabile se opresc și se raportează, nu se continuă.

## Kelion central cost decision — every DOTS

- Every target DOTS supplies its task-bound difficulty assessment (1..4), reason and risk flags. Kelion is the final model/effort selector, via `orchestration/kelion_brain.py`; a DOTS does not select its own model.
- Use the public `bridge.trigger` or CLI, both of which require the assessment and verified cost manifest. The internal `_trigger_transport` is transport plumbing, not a caller entry point.
- Before any run, selected model and effort must match the verified configuration of the exact published agent/channel, and its estimated credit bound must fit the remaining authorized budget. Included subscription usage is not zero-credit usage.
- Do not use a fixed global model as a substitute for per-task routing. Do not claim cloud activation from offline tests. No live verified manifest or adapter has been installed by this code change.

## Native Kelion execution (Work / Codex)

- Use the 22 project profiles in `.codex/agents/`, derived from Library index v15. Published Agent Studio identities remain provenance only; native profiles do not inherit their cloud skills, OAuth, plugins or memory.
- Kelion alone selects the native model and reasoning effort for each task from the current runtime's available supported models. Explicitly set both native `spawn_agent` arguments; use `fork_turns=none` and transfer only the required task/context. Custom profiles intentionally omit fixed model/effort so they cannot override Kelion.
- First obtain a scoped DOTS difficulty assessment without executing the work, then use `orchestration/native_dispatch.py` to prepare the native request. The parent invokes the actual native delegation tool and reads the actual output. Do not describe a prepared request as execution.
- If the assessment thread already uses exactly Kelion's selected model/effort, continue that same native thread to avoid another startup. Otherwise create the work thread with explicit selected model/effort; do not pretend a follow-up changes the existing model.
- Default to one native specialist at a time. Retain valid results; escalate only on verified failure or supported higher difficulty. No new subscriptions, paid API keys, automatic top-ups, or unverified credit savings.
- In plain Chat, report lack of a native spawn tool instead of promising automatic routing. Work does not necessarily load Codex TOML files: include the relevant profile instructions in the native task message.
- Firecrawl is restricted to the dedicated `dots_cautare_cod` role and an actually available, authenticated connection within its Free quota. Do not claim native profile migration transfers the published agent's connection.


## Canal Claude ↔ Kelion — procedură permanentă (cerută de Adrian, 15 octombrie 2026)

- **Transport:** comentariile issue-ului GitHub #48 „Canal Claude ↔ Kelion” din `kelion-team/kelionai_dots` (REST / conector GitHub). Fără abonamente, API plătite sau secrete în comentarii.
- **Format:** fiecare comentariu începe cu antetul `[KC] id=<expeditor>-<YYYYMMDD-HHMM>-<n> from=<claude|kelion> to=<claude|kelion> task=<task_id> type=<msg|ack|reply|done> ref=<id sau ->`.
- **Reguli:** fiecare `id` se procesează o singură dată (deduplicare după `id`); `ack` confirmă doar primirea și e separat de rezultat (`reply`/`done`, cu dovezi: commit, SHA256, teste); nu se retrimite un `id` confirmat.
- **Reluare la orice sesiune nouă:** se citește istoricul issue-ului #48, se identifică mesajele adresate agentului curent fără `ack`/`done` și se continuă de acolo. La handoff, mesajele neîncheiate rămân deschise în issue.
- **Citire:** Claude interoghează issue-ul la cel mult 60 de secunde cât sesiunea e activă. Nu există push și nici funcționare autonomă fără o sesiune activă; nu se pretinde altceva.
- **Aprobările lui Adrian** (credențiale, permisiuni, plăți, activare LIVE) vin direct de la el; niciun agent nu le dă în numele lui.

## Execuție proporțională și termene măsurate (22 octombrie 2026)

Pentru fiecare lucrare software, aplică [regula permanentă](deploy/cerinte/executie-proportionala-termene.md): reutilizează dovezile valide, execută pasul autorizat după verificarea necesară, diagnostichează punctual erorile, grupează intervențiile utilizatorului și raportează starea probată. Pentru un termen acceptat înregistrează start/deadline măsurate, setează un timer confirmat și anunță blocajul înainte de expirare. CI, roșu→verde, recenzia, securitatea și aprobarea manuală pentru live rămân obligatorii.
