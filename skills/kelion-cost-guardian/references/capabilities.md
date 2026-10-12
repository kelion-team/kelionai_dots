# Contract pentru setările verificabile

## Unde poate decide regulatorul

| Suprafață | Control permis când există acces | Fără control verificat |
| --- | --- | --- |
| ChatGPT Chat | Selectează model/efort disponibile din Chat; evită agentul când răspunsul simplu ajunge | Nu inventa GPT-6 Luna în selectorul Chat |
| Work/Codex | Model/efort din selectorul oficial; preferă nivelul economic justificat | Recomandare, nu modificare |
| Workspace > Models | Doar owner/admin și doar starting defaults; păstrează modelele disponibile și permisiunile | Nu pretinde schimbarea globală |
| Agent Studio/DOTS | Reguli de rutare și controale prezente efectiv în editor | Nu pretinde că skillul a schimbat intern motorul DOTS |
| Conector fără model intern | Reglează hostul, frecvența, paginarea și volumul apelurilor | Nu inventa un buton intern pentru model |
| Conector cu model intern | Schimbă doar dacă există selector/API documentat, drepturi și o probă actuală | `model_switch_verified=false` și nicio schimbare |

## Semnificația câmpurilor din manifest

- `surface`: `chat`, `work`, `codex`, `agent` sau `connector:ID` pentru un model intern demonstrabil.
- `enabled`, `verified`: **boolean explicit**; false/necunoscut blochează selecția modelului.
- `billing_mode`: `included`, `metered`, `unknown`. Scriptul exclude `metered` și `unknown` pentru a nu produce costuri suplimentare.
- `cost_rank`: rang comparativ ordinal configurat de administrator, nicidecum tarif, credit ori echivalență între limite de abonament.
- `capability_tier`: estimare operațională 1–4; nu reprezintă benchmark oficial.
- `reasoning_levels`: niveluri confirmate din selector pentru model și suprafața respectivă.
- `connectors[].attached_to_agent`: conectarea generală nu dovedește accesul agentului țintă.
- `connectors[].model_control`: `host` / `internal` / `none` / `unknown`.
- `connectors[].model_switch_verified`: doar true explicit permite selecție internă.

Orice schimbare a drepturilor sau o apariție nouă de modele cere reconfirmare a manifestului. Nu păstra tokenuri, cookie-uri sau date sensibile în manifest.

## Acceptare

1. Rulează `python -m unittest discover -s tests -v`, păstrează ieșirea și exit code.
2. Verifică nivelurile 1–4, fallback-ul conservator, escaladarea controlată, blocarea permisiunilor necunoscute, excluderea modelelor plătite și absența efectelor externe.
3. Pentru a declara operațional în ChatGPT: skillul trebuie instalat și atașat în Agent Studio, model picker confirmat, apoi o cerință reală transmisă și răspunsul verificat. Testele offline nu certifică acest lucru.
