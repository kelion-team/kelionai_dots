# Contracte identificate înainte de implementare

Observații din 2026-10-21. Autoritatea stării live: **Contabo**, nu checkoutul cloud. Aparatul activ al utilizatorului: necunoscut. Nu s-au apelat workerul, coada de execuție, operații admin sau trimiteri pe canal.

| Sursă citită | Ce dovedește / reutilizare | Limită |
| --- | --- | --- |
| Brain `catalog_unelte`, versiunea `3ed69346` | `server_vedere` listeaza/citeste; `canal_openai` trimite/citeste; `jurnal_chatgpt`; worker blocat până la validarea izolării | Catalogul nu dovedește acces de serviciu, execuție sau livrare în cloud |
| Contabo `/opt/kelion-brain/work/sursa-unica/manifest.json`, primele 110 linii | Manifest canonic există; catalogul declară versiunea activă `contabo-kelion-jobs-20261021-r7` | Citire parțială, nu verificare completă a hashurilor/funcționării; fișierul se schimbă în timpul lucrării separate |
| Contabo `/opt/kelion-brain/canal_openai.py`, primele 220/656 linii | JSONL `{id,t,de,text,citit_de}`; referințe `cerere`/`raspuns_server`; max 8000 caractere; dedup/redelivery; fail-closed la reguli lipsă | `claude-server`/`claude-code` sunt etichete istorice; nu identifică threadul cloud. `necitite()` marchează citit și emite ACK, deci nu este citire fără efecte |
| Contabo `/opt/kelion-brain/canal_ack.py`, primele 220/259 linii | `ACK-{mesaj_id}-{cine}`; `mesaj_id`, `cine`, `t_ack`; `PROCESAT-{mesaj_id}-{cine}`, `para_mesaj`, `raspuns_id`; ACK distinct de rezultat | `procesat` este referință de răspuns, nu dovadă că sarcina este rezolvată; modulul poate emite notificări |
| Repo `AGENTS.md`, `.agents/skills/kelion-delegare/SKILL.md`, `orchestration/SOP-DELEGARE.md`, `orchestration/README.md`, issue GitHub #4 | ID de task, receipt separat, output real + readback; identitate `agt_` diferită de `agtch_`; reutilizarea contractului de verificare | `orchestration/bridge.py` vizează agenți publicați Workspace, nu trimitere arbitrară către conversația cloud; nu este adaptor activ pentru această punte |
| GitHub `.github/workflows/deploy-web.yml`, blob `c489a0c2bfae282fee6edb61b83ca94df03c64c6` | Push main, filtru `site-live/web/**`, OIDC către `/hooks/github` | Fără instalare generică de servicii |
| GitHub `deploy/auto-deploy-web.sh`, blob `be2c897287b5dc79e95439bfcfdbd219942ffe95` | Lista fixă de cinci fișiere web, destinația `/opt/kelion-app/web-v1` | Nu dovedește configurația efectiv instalată pe Contabo; comentariul vechi despre timer diferă de workflowul pe eveniment |

Reutilizare aleasă: semantica ID/corelație, separarea primit/procesat/rezultat și readback-ul, fără importarea sau duplicarea workerului, a canalului cu efecte ori a UI Jobs/Live. Puntea are numai ledger propriu de transport. O integrare viitoare trebuie să păstreze maparea ID local ↔ ID Brain, autentificarea și referința către rezultatul real. Nu se scrie direct în JSONL-ul Brain.

KelionDots și conversația cloud nu au primit URL-uri inventate. Registrul separă existența documentației de verificarea unui endpoint efectiv. Configurația livrată are **zero endpointuri de transport verificate**, astfel încât activarea prin simpla editare a JSON-ului nu pornește transport real.

Lucrarea separată `01a15a09-9054-76bf-ad5d-7e6e1638d04f` nu a fost modificată sau reimplementată. Scope-ul acestui pachet este exclusiv noul director `channel_bridge/`. Nicio modificare de memorie locală.
