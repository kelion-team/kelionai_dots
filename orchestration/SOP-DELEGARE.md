# KelionAI — Procedură operațională obligatorie: delegare, recuperare și verificare

**Versiune:** 1.0 · **Data:** 2026-10-12 · **Stare a integrării:** ÎN LUCRU (nu există încă probă end-to-end a unui agent real)
**Aplicabilitate:** ChatGPT Chat, ChatGPT Work și Codex, atunci când au acces explicit la proiectul `kelion-team/kelionai_dots`.
**Document de intrare:** [AGENTS.md](../AGENTS.md). **Registru comun:** [GitHub issue #4](https://github.com/kelion-team/kelionai_dots/issues/4).
**Scop:** folosirea agenților KelionAI **deja publicați**, cu delegare, rezultate verificate și predare de context între cele trei suprafețe; fără costuri noi.

> **Normă:** O singură lucrare activă. Nu întrerupe, nu abandona și nu muta unilateral lucrarea în „pending” pentru că lipsește o cheie, un instrument sau o conexiune. Caută mai întâi soluția oficială, repară pașii accesibili, nu reface munca deja validată. Dacă o acțiune rezervată utilizatorului sau o restricție reală face continuarea imposibilă, explică precis dependența și păstrează `IN PROGRESS`; nu pretinde că sistemul continuă să lucreze nesupravegheat. Respectă limitele de securitate și aprobările cerute de platformă.

## 1. Condiții obligatorii înainte de delegare

1. **Înțelege lucrarea activă.** Identifică obiectivul, artefactele existente, criteriile de acceptare, dependențele, lucrările din coadă și ce este deja testat. Nu întreba utilizatorul pentru informații deja disponibile.
2. **Recuperează registrul canonic al agenților**, verifică identitatea agentului `agt_...`, publicarea, funcția, accesul real, instrumentele atașate și testele relevante. Numărul din registru NU este dovadă că agentul poate fi executat în sesiunea actuală.
3. **Selectează specialistul potrivit** după rol și eligibilitate, nu după simpla potrivire a numelui. Pentru cod: autor → tester independent → salvarea rezultatului; un singur autor per fișier.
4. **Alege calea oficială efectiv disponibilă**:
   - **UI ChatGPT/Agents:** deschide agentul publicat sau invocă-l unde interfața permite `@`. Verifică agentul țintă și conversația reală.
   - **API Workspace Agents:** numai dacă agentul are canalul API publicat `agtch_...`, există un **Workspace Agent access token** autorizat cu permisiunea necesară și costul utilizării este acoperit de drepturile existente. `agt_...` nu este `agtch_...`. O cheie OpenAI Platform `sk-...` nu este substitut.
   - **Work/Codex:** folosește doar instrumente realmente expuse în suprafața curentă sau aceeași cale API validată. Pluginul Codex „Workspace Agents” este pentru administrare, **nu dovedește execuția**. Accesul la GitHub nu este acces implicit la runtime-ul agentului.
5. **Zero cost nou, zero escaladare de privilegii:** nu cumpăra credite, planuri, trialuri facturabile sau servicii; nu crea chei nepotrivite; nu publica tokenuri în GitHub, Library, Slack, conversații ori loguri. Nu dezactiva MFA. Confirmați separat orice acțiune financiară sau grant cerut de sistem. Dacă drepturile/cota efectivă sunt necunoscute, nu presupune gratuitate.

## 2. Contractul unic de lucru („task envelope”)

Păstrează pentru fiecare delegare un identificator unic și un jurnal în spațiul comun cu:
- `task_id`, `origin` = `chat | work | codex`, `objective`, `owner`, `agent_id`, opțional `api_trigger_id`;
- `input_ref`, `input_sha256` (calculat din octeții real recuperați), `acceptance_criteria`, `cost_policy=no_new_cost`, `repo_issue_url`;
- `dispatch_mechanism`, `dispatch_receipt`, `conversation_url`, opțional `run_id`, timpii și starea;
- `result_ref`, `result_sha256`, `verification_command_or_method`, `verification_receipt` și `verifier`.

Nu inventa ID-uri, URL-uri, hashuri sau rezultate. Dacă un câmp nu există încă, păstrează-l `unknown`/absent, nu `success`. Nu salva date sensibile în jurnalul partajat.

## 3. Fluxul standard de execuție

1. **PREPARE:** preia intrările reale și criteriile; salvează intrarea cu sursă identificabilă; verifică lipsa secretelor; alege agentul publicat; creează legătura către issue-ul comun și identificatorul idempotent.
2. **DISPATCH:** transmite *efectiv* cererea prin UI/API oficial. Notează exact destinatarul și dovada trimiterii. Un mesaj pregătit, un fișier, o recomandare DOTS ori o issue GitHub **nu sunt delegare**.
3. **RUN:** urmărește cu instrumentul disponibil și fără polling agresiv. HTTP 202 este doar `accepted`; `completed` la statusul API arată doar starea execuției, **nu textul rezultatului**.
4. **RESULT:** obține outputul efectiv:
   - citește conversația agentului, dacă UI/conectorul autorizat permite;
   - **sau** agentul, dacă are deja permisiunea necesară, publică rezultatul într-un artefact partajat legat de `task_id` (de exemplu issue GitHub / fișier accesibil) și furnizează `result_ref`.
   Nu presupune că agentul poate scrie pe GitHub doar pentru că orchestratorul poate.
5. **READBACK:** recitește rezultatul din sursa reală; confruntă `task_id`, agentul autor, obiectivul, versiunea intrării și SHA256-ul calculat pe octeții primiți. Un URL neaccesat sau un titlu de fișier nu sunt probă.
6. **VERIFY:** tester independent sau metodă de acceptare explicită. Pentru cod: comandă exactă, director, exit code și logurile originale. Pentru activare: probă live; testele locale nu substituie cloud. Marchează `verified` numai dacă toate criteriile sunt îndeplinite.
7. **HANDOFF:** păstrează în registrul comun doar referințele, probele și starea actuală, astfel încât o altă suprafață (Chat/Work/Codex) să poată continua fără repetarea pașilor finalizați; confirmă printr-o citire reală din acea suprafață.

**Stări permise:** `prepared` → `dispatched` → `running` → `result_received` → `verified`, respectiv `blocked_external_action`, `failed`. Pentru blocaje explică exact cauza și reia pașii independenți. Nu transforma `blocked_external_action` în `verified` și nu declara produsul complet în urma unei simulări.

## 4. Exemplu de cerere de transmis agentului

```text
TASK_ID: <ID_unic>
Rol agent: <agent_id si functie verificata>
Obiectiv: <cerinta concreta>
Context si intrari: <linkuri reale si hashuri>
Permisiuni: numai actiunile deja autorizate; fara costuri/abonamente/credite noi
Livrabil: <fisier, raspuns, test ori raport precis>
Acceptare: <verificari masurabile>
Publicare rezultat: <cale partajata accesibila, DOAR daca agentul are permisiune>
Format predare: task_id, status, result_ref, source_sha256, test_log_ref, limitari
```

## 5. Limitările reale ale adaptorului curent

`orchestration/bridge.py` suportă pregătire, declanșare explicit autorizată și citire status când există canalul/tokenul corect. **Nu recuperează singur textul rezultatului și nu execută singur agenți din Codex/Work.** Pentru output este obligatorie etapa RESULT + READBACK prin conversația accesibilă sau un artefact partajat, cu permisiuni verificate separat.

Nu sunt încă probate: un `agtch_...` real disponibil în sesiunea curentă, un token Workspace Agents autorizat în acest runtime, o execuție reală cu răspuns recuperat ori funcționarea cross-surface. Până la acele probe, **starea lucrării principale rămâne ÎN LUCRU**.

## 6. Acceptare repetabilă pentru fiecare schimbare

- Agent publicat cu identitate verificată, selectat după rol, fără creare inutilă.
- Trimitere REALĂ cu dovadă, fără costuri noi sau privilegii presupuse.
- Output REAL recuperat, cu identitate de sarcină + integritate verificate.
- Verificare independentă a rezultatului.
- Transfer Chat → Work → Codex (și invers când e cerut) testat din fiecare suprafață, nu dedus din existența fișierelor.
- Nicio altă lucrare nu a fost pornită în paralel; stările, dependențele și probele sunt păstrate.

**Referințe:** [bridge.py](bridge.py) · [README](README.md) · [issue de acceptare](https://github.com/kelion-team/kelionai_dots/issues/4) · [documentația oficială API](https://developers.openai.com/workspace-agents/trigger-runs).

**Regulă de guvernanță:** acest SOP este un document de proiect ce trebuie citit în sesiunile care lucrează la KelionAI. Existența lui în GitHub **nu îl încarcă automat** în fiecare chat sau în fiecare agent; inițiatorul sarcinii trebuie să îl furnizeze ori să confirme accesul la depozit.
