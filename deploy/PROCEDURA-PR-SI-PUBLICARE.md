# Procedura: PR și publicare pe Contabo (Kelion, Claude, Codex)

Scrisă de Claude la cererea lui Adrian, 21.10.2026, din ce a funcționat efectiv azi (PR #62, #63; reparațiile live
aplicate la 20:08 cu probă, backup și revenire). O schimbare e **gata** doar când merge pe serverul live, cu dovadă recitită.

## A. PR (orice schimbare de cod)

1. **Ramură nouă** din `main`: `fix/<subiect>-<AAAAMMZZ>` sau `feat/...`. Niciodată commit direct în `main`.
2. **Unde:**
   - `kelion-team/kelionai_dots` (PUBLIC) — componente comune, scripturi de publicare, teste. **Fără** secrete, date
     personale, analize interne ale serverului sau copii ale codului live care nu au trecut prin `deploy/safe-export`.
   - `kelion-team/kelion-brain` (PRIVAT) — codul care rulează pe Contabo (după copia verificată din `deploy/safe-export`).
     Atenție: un merge în `main` aici redeployează conectorul Kelion-Brain pe Render.
3. **Teste în același PR**, care pică pe codul vechi și trec pe cel nou. Adaugă suita în `.github/workflows/tests.yml`
   (jobul `teste`). Pentru scripturi: `bash -n` și `python3 -m py_compile` în același job.
4. **Descrierea PR-ului:** ce repară, dovada din producție (linie din `pod.jsonl`, oră, cod), cum se aplică, ce NU face.
5. **Revizuire:** așteaptă jobul `teste` verde și revizuirea Codex. Fiecare observație: fie repari și răspunzi pe fir cu
   commitul, fie explici de ce nu se aplică. Rezolvă firele.
6. **Merge:** doar cu `teste` verde, fără conflicte și fără fire deschise. Un merge NU înseamnă că rulează pe server.

## B. Publicare pe Contabo (schimbare live)

Codul live NU e identic cu GitHub (ex.: `pod_locuri` modificat direct pe server). De aceea nu se copiază fișiere peste
cele live; se aplică **reparații exacte** peste textul live.

1. **Citește întâi fișierul live** (conectorul de citire). Scrie reparația ca script `deploy/repara_<subiect>.py`:
   fiecare înlocuire trebuie găsită EXACT o dată, altfel nimic nu se scrie; marcaj «DEJA APLICAT» pentru a doua rulare;
   compilare (`py_compile`) și o **probă de comportament** pe copia reparată. Model: `deploy/repara_pod.py`,
   `deploy/repara_logare_locuri.py`, `deploy/repara_necunoscuti.py`.
2. **Scriptul de aplicare** `deploy/repara-<subiect>.sh`, rulat de Adrian ca root, cu o singură comandă:
   1. **oprire dacă e un apel în curs** (`curl http://127.0.0.1:8095/sanatate` -> `"apel_in_curs": false`), pentru orice
      repornire a `kelion-pod` sau `kelion-whatsapp`; verificarea se **repetă imediat înainte de instalare și repornire**
      (un apel început în timpul pregătirii oprește totul, nimic instalat). Fereastra rămasă e de sub o secundă; o oprire
      completă a apelurilor noi ar cere o poartă de admitere în pod, care nu există încă;
   2. descărcare de la un **commit fix**: scriptul cere `KELION_REF=<commit complet, 40 hex>` (același commit ca în URL)
      și refuză să ruleze fără el; toate fișierele ajutătoare se descarcă de la acel commit, nu de la o ramură;
   3. probă pe copie (`python3 repara_x.py /opt/... /tmp/...`) — dacă pică: «Nimic schimbat»;
   4. **backup** (`/opt/<serviciu>/backup-<data>`);
   5. instalare, repornirea DOAR a serviciului atins;
   6. **verificare de sănătate**; la eșec, **revenire automată** la backup;
   7. **dovezi**: liniile relevante din jurnal după repornire (ex.: 0 `canal_dot_esuat` în 60 s);
   8. **cod de ieșire adevărat**: 0 doar dacă totul s-a aplicat; un script care rulează mai mulți pași iese cu cod diferit
      de 0 dacă oricare pas nu s-a aplicat complet.
   Model: `deploy/repara-apel-whatsapp.sh`, `deploy/repara-pas2.sh`, `deploy/repara-pas3.sh`, `deploy/repara-tot.sh`.
3. **Comanda pentru Adrian** — `<COMMIT>` = commitul complet (40 hex), de două ori:
   - PowerShell pe laptop:
     `ssh -i $env:USERPROFILE\.ssh\kelion_contabo root@144.91.64.250 "curl -fsSL https://raw.githubusercontent.com/kelion-team/kelionai_dots/<COMMIT>/deploy/repara-<subiect>.sh | KELION_REF=<COMMIT> bash"`
   - terminalul serverului (deja root pe Contabo, fără ssh):
     `curl -fsSL https://raw.githubusercontent.com/kelion-team/kelionai_dots/<COMMIT>/deploy/repara-<subiect>.sh | KELION_REF=<COMMIT> bash`
4. **Verificare după aplicare (obligatorie, doar citire):** marcajul reparației în fișierul live, serviciul activ,
   `/sanatate` ok, evenimentele din `pod.jsonl` care dovedesc efectul (ex. apel real: `adrian_vorbit_s` > 0 și
   `kelion_vorbit_s` > 0, fără `dot_watch_failure`). Abia apoi «gata», cu ora și dovada.
5. **GitHub = server:** după o publicare reușită, copia codului live se actualizează în `kelion-brain` prin
   `deploy/safe-export` (pregătire locală, verificarea conținutului de către Adrian, apoi publish pe ramură + PR).
   Sincronizarea se poate repeta: la fiecare publish, `server/` din ramura nouă e înlocuit integral cu copia aprobată
   (fișierele dispărute de pe server dispar și din PR).

## B2. Cine face deploy

Kelion are acces la server **doar pentru citire** (decizia lui Adrian). Kelion pregătește tot până la comandă (ramură,
PR cu teste, scriptul de reparație cu probă/backup/revenire, commitul fix); **comanda o rulează Adrian**, apoi Kelion și
Claude verifică doar citind. Un deploy făcut direct de Kelion ar cere acces de scriere pe server, pe care numai Adrian îl
poate acorda și configura.

## C. Niciodată

- tokenuri, parole, chei sau date personale în chat, PR, issue, jurnal sau depozit public;
- repornire în timpul unui apel; schimbări live fără backup și fără revenire automată;
- «merge» fără dovadă live; un PR unit, un test local, un HTTP 202 sau un ACK NU sunt dovadă de funcționare;
- acces nou persistent (chei SSH, servicii care execută automat ce vine din GitHub) fără decizia explicită a lui Adrian.

## D. Unde se coordonează

Issue #48 «Canal Claude ↔ Kelion», format `[KC] id=... from=... to=... task=... type=msg|ack|reply|done ref=...`
(vezi `AGENTS.md`). Rezultatele cu dovezi (commit, SHA-256, teste, linii de jurnal) merg în `reply`/`done`.
