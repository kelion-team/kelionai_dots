# KelionAI agent orchestration rules (Codex / repository)

- First consult `orchestration/README.md` and GitHub issue #4 when the user asks to delegate to previously published ChatGPT workspace agents.
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

