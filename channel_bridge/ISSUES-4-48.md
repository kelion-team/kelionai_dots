# Corecții pentru issues #4 și #48 (21 octombrie 2026)

Am citit integral corpurile issues #4/#48 și toate cele 2/9 comentarii prin conectorul GitHub, înainte de modificări. PR #51 era deja merged de alt actor, la `642c37a`; reviewul Codex pe `6325e887` s-a terminat fără constatări la 09:55:33Z. Bugbot nu a rulat din cauza limitei de utilizare. Niciuna dintre aceste observații nu demonstrează execuție live a agenților.

## #48: istoric durabil și corelare, fără schimbarea identității istorice

Canalul GitHub există și comentariile dovedesc citire/scriere istorică în ambele sensuri. Lipsea implementarea de citire structurată pentru reluare. `coordination.py` procesează snapshotul complet al comentariilor (toate paginile), păstrează URL/autor GitHub și separă mesaje, ACK, răspunsuri și afirmații `done`. ID reutilizat cu alt corp este blocat; ACK/răspuns cu task sau direcție greșită nu confirmă mesajul. Nu execută textul și nu trimite nimic.

```sh
python3 -B -m channel_bridge.coordination /cale/privata/issue48-comments.json
```

Snapshotul este o listă de obiecte `{id, body, user: {login}, url}` obținută prin citirea autorizată GitHub. Modulul nu solicită sau creează tokenuri. Istoricul durabil rămâne GitHub; proiecția se reconstruiește determinist la fiecare reluare. Nu oferă polling sau autonomie fără runtime autorizat.

Parserul respectă protocolul permanent existent `claude|kelion`; rolul `openai` este respins ca antet invalid până la actualizarea explicită a acelui contract. Aceasta nu reactivează Claude. `claude` rămâne identitate istorică; **nu este alias implicit pentru OpenAI**. Același cont GitHub a semnat istoric ambele roluri: antetul singur nu autentifică identitatea unui agent. Mesajele vechi nu sunt redistribuite automat și aprobările citate în comentarii nu acordă privilegii.

Citirea celor 9 comentarii reale produce 4 mesaje inițiale și două referințe între taskuri diferite: `kelion-20261015-0723-3` (`mask-deploy` → `canal-proba`) și `kelion-20261015-0725-4` (`canal-proba` → `mask-deploy`). Acestea sunt raportate, nu rescrise. Confirmările în proză rămân istoric lizibil, dar nu sunt transformate automat în ACK-uri structurate. Cele două cereri istorice `mask-deploy` nu sunt dovadă de instalare.

## #4: rezultatul trebuie legat de cererea trimisă

Defect corectat: result_gate verifica hashul intrării față de rezultat/verificator, dar receiptul de dispatch nu lega acea intrare. O intrare substituită împreună cu ambele hashuri putea trece verificarea de integritate. `orchestration/bridge.py` păstrează acum `input_sha256` pentru textul original din envelope; `result_gate.py` îl cere și îl confruntă. Sufixul tehnic `Task ledger` nu face parte din inputul original. Receipturile istorice fără hash nu sunt retroactiv declarate verificate; necesită recuperarea dovezii originale, fără redispatch automat.

Defect corectat și în PR51: `principal=None` ocolea verificarea opțională de identitate din nucleul punții. `submit` și `receive` cer acum un principal explicit, nevid, înainte de folosirea registrului. Nu este adăugată autentificare fictivă: adaptorul real trebuie în continuare să autentifice principalul.

Se reutilizează result_gate existent, fără clonarea executorului sau eliminarea controalelor de cost/izolare. `fully_verified` rămâne false pentru probe offline; un `done` pe canal nu îl schimbă.

## Verificare și limite

- 27 teste `python -B -m unittest discover -s channel_bridge/tests -v`: OK.
- 53 teste `python -B -m unittest discover -s orchestration/tests -v`: OK.
- Proiecția snapshotului real #48 a fost executată local; fără trimitere sau procesare a cererilor istorice.
- Fișiere Jobs/Live/backup și pipelineul de deploy nu sunt modificate. Oglinda Brain a fost citită read-only; accesul direct la firul separat `01a15a09-9054-76bf-ad5d-7e6e1638d04f` nu este disponibil în instrumentele acestui executor. Prin urmare nu pretind verificarea integrală a acelui fir. Scope-ul rămâne puntea și poarta de verificare existente.

## Ce împiedică închiderea issues / publicarea live

#4 cere execuție reală + output recuperat în Chat, Work și Codex și handoff verificat. Ultimele comentarii sunt observații din 14 octombrie, inclusiv eșecuri de execuție; cota din acea zi nu este diagnostic actual. Workerul Brain este declarat blocat până la validarea izolării. Nu îl pornim prin canalul informativ și nu substituim ACK-ul rezultatului.

#48 cere continuarea coordonării cu identitate OpenAI verificată și un runtime autorizat. Protocolul/proiecția nu livrează singure în conversația cloud sau voce. Lipsesc contractele de adresare, autentificare și recuperare a rezultatului pentru acele suprafețe.

Instalarea: pipelineul verificat publică exclusiv cinci fișiere web. Comentariile vechi menționează `deploy/kelion-mask`, dar această cale nu există în checkoutul GitHub verificat; nu este executată sau recreată pe presupuneri. PR-ul de corecții este publicabil în repo, dar nu instalează servicii pe Contabo.

Pentru un pas ulterior de instalare, operatorul trebuie să verifice identitatea existentă a serviciului, receptorul de deploy instalat și destinațiile read-only; apoi un PR separat poate fixa artefactul/hashul și instalarea inertă cu rollback. Dacă necesită user/group nou, token WebSocket sau acces la CODEX_HOME, schimbarea concretă trebuie aprobată separat: identitate, căi, drepturi minime și revocare. Nu aplicați propunerile istorice de `chmod -R`, nu copiați autentificări, nu modificați pipelineul pentru a evita această condiție. Această etapă nu este implementată sau activată aici.

Issues rămân deschise până la dovezile end-to-end, chiar după merge-ul corecțiilor.

## Corecții după reviewul Codex pe 38c0530

Sunt păstrate integral corpul, URL-ul, autorul GitHub și SHA256 pentru fiecare înregistrare în proiecția returnată (`records`). Confirmările trebuie să aibă un ID numeric GitHub mai mare decât mesajul referit; ordinea paginilor nu influențează corelarea. Metadata de ordine absentă/invalidă este respinsă. Fișierul de intrare pentru CLI prepare este citit ca octeți UTF-8, fără conversia CRLF la LF, astfel încât hashul receiptului corespunde artefactului original. Nu se relaxează poarta de integritate pentru receipturile istorice.
