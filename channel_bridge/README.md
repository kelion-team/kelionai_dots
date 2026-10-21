# Punte de canale Kelion — propunere izolată

Transportul nou autentificat pentru ChatGPT, Work, Kelion, **mediul Claude** și Contabo este în [SHARED-CHANNEL.md](SHARED-CHANNEL.md). Documentul de mai jos descrie ledgerul experimental anterior; registrul său inert nu este registrul clienților noului host. Niciunul nu este declarat instalat live prin existența codului.

Pachet reviewabil, implicit inert. Nu este instalat și nu conectează încă cele trei suprafețe live. Python 3.10+ pe Linux, numai biblioteca standard; fără instalare de dependențe, shell, descoperire de porturi, modele sau credențiale. Singurele fișiere noi sunt în `channel_bridge/`. Nu modifică Jobs, Live, backup, orchestrarea existentă sau workflowuri.

## Rulare locală și teste

Din rădăcina repositoryului sau a arhivei:

```sh
python3 -B -m unittest discover -s channel_bridge/tests -v
python3 -B -m channel_bridge --config channel_bridge/registry.json --state /tmp/kelion-bridge-review.sqlite
```

A doua comandă raportează `liveness=ok`, `readiness=blocked` și exit **2** intenționat. Creează numai ledgerul local și lockul lui; folosiți un director privat pentru orice date reale. `--serve` repetă raportul la 30 secunde și acceptă SIGTERM. Nu deschide socketuri, nu face apeluri către Contabo, nu citește automat jurnalele sale. CLI refuză `enabled=true`: activarea cere implementare și review pentru adaptoarele reale.

## Comportament implementat

- Registru explicit cu exact `keliondots`, `brain`, `cloud`. Pentru trimitere sunt necesare endpoint activ, dovadă verificată, principal și adaptor înregistrat în cod. Numele/URL-urile din mesaje nu creează rute. Registrul livrat nu are endpointuri de transport verificate: toate sunt blocate cu motive concrete.
- `Message`: `id`, `correlation_id`, `source`, `target`, `text`. ID stabil pe retry; ID nou pentru o cerere intenționat nouă. Hashul întregului envelope detectează reutilizarea ID-ului cu alt conținut. Limită text 32 KB.
- `accepted_local` înseamnă persistare locală. `ack` înseamnă primire la destinație și starea `awaiting_result`; numai `result` cu text real și identitate/corelație valide produce `completed`. Aceasta înseamnă rezultat de transport recuperat, **nu verificarea succesului unei lucrări**.
- SQLite WAL + synchronous FULL, primary key pe ID și lock exclusiv al procesului. Deduplicarea și numărul de încercări supraviețuiesc restartului. Un al doilea proces cu același ledger este respins.
- Maximum 3 încercări implicit, maximum configurabil 5; backoff 5, 10 secunde implicit. Retry este permis exclusiv pentru `NotSent`, garanția adaptorului că nu s-a produs efect. Timeoutul sau excepția nespecifică produce `uncertain`, fără retrimitere.
- Persistarea `sending` precedă transportul. Restartul în acea stare produce `uncertain/restart_during_send`; reconcilierea cere un rezultat/ACK autentic. ACK-ul duplicat nu prelungește termenul; lipsa rezultatului după 300 secunde devine incertă, fără resend. Refuzul sau revocarea endpointului blochează mesajul fără retry.
- Health local: liveness distinct de readiness, motive pe endpoint și număr de mesaje pe stare. Excepțiile brute nu sunt persistate, pentru a evita scurgeri de secrete. Nu există endpoint HTTP health fictiv.

## Contract pentru adaptoare viitoare (interfață internă, nu API Kelion inventat)

`send(Message)` întoarce `{kind: ack|result, correlation_id, principal, result?}`. `health()` întoarce un boolean după verificare delimitată. Implementarea adaptorului trebuie să aplice timeout finit, autentificarea existentă și autorizarea exactă înainte de apel. `principal` trebuie derivat din autentificare, niciodată din textul utilizatorului. Obiectele Python ale adaptorului sunt cod de încredere; nu sunt încărcate din căi/module configurabile.

`receive()` acceptă rezultatul ulterior cu identitatea verificată a destinației. Nu expuneți această metodă ca endpoint fără autentificare. Rezultatele întârziate pot reconcilia `uncertain`; nu există comandă de rearmare automată a mesajelor blocate sau eșuate. `NotSent` nu trebuie folosit pentru HTTP timeout/500 cu efect necunoscut. Un refuz de securitate necesită dovezi noi, relevante, înaintea unei reluări manuale autorizate.

## Pornire automată: propunere neinstalată

`systemd/kelion-channel-bridge.service` este exclusiv un fișier de review. Layout propus: `/opt/kelion-channel-bridge/channel_bridge/`, config `/etc/kelion-channel-bridge/registry.json`, stare privată `/var/lib/kelion-channel-bridge/`. User/group dedicate trebuie să existe deja sau să fie aprobate separat; pachetul nu le creează. Cod/config read-only, numai directorul propriu de stare writable; `UMask=0077`, fără capabilități, fără acces rețea IP. Nu folosește userul Brain și nu primește acces la fișierele lui.

Activarea ulterioară ar necesita review separat pentru accesul minim la transportul documentat, identități și endpointuri; nu se elimină automat restricțiile systemd. Nu există script de instalare, `systemctl`, restart de servicii sau grant automat în acest pachet.

## Ruta PR și instalarea

Repository confirmat: `kelion-team/kelionai_dots`, bază propusă `main`. Workflowul existent `.github/workflows/deploy-web.yml`, recitit prin conectorul GitHub, rulează numai la push pe main pentru `site-live/web/**`; notifică `https://kelionai.app/hooks/github` prin OIDC. `deploy/auto-deploy-web.sh` copiază numai `index.html`, `app.js`, `auth.mjs`, `server.mjs`, `style.css` în `/opt/kelion-app/web-v1`.

Acest pachet este separat de acele căi și poate fi livrat prin PR draft fără a schimba pipelineul. Workflowul existent **nu instalează această punte Python/systemd**. Nu se pretinde compatibilitate de instalare automată inexistentă; o etapă de instalare verificată în ruta existentă rămâne de proiectat/aprobat. Lipsa accesului SSH nu împiedică pregătirea PR. Nu se face merge/deploy.

## Riscuri și lipsuri înainte de instalare

1. Confirmarea contractului live de intrare/ieșire KelionDots voce/chat și a API-ului către conversația/executorul cloud exact; încă nedocumentate aici.
2. Adaptor Brain prin acces existent autorizat, fără importarea directă a modulelor care pot porni modele, worker sau notificări. Catalogul unui conector ChatGPT nu este o credențială de serviciu pe Contabo.
3. Validarea izolării workerului rămâne blocaj distinct; puntea nu îl pornește, nu folosește canalul informativ ca execuție și nu moștenește conexiuni cloud.
4. Reviewul identităților și ACL, verificarea bounded timeouts/transport, reconciliere și probe end-to-end autorizate. Acum există numai mockuri locale.
5. SQLite conține text și rezultate în clar. Necesită acces privat, spațiu monitorizat și politică aprobată de retenție. Nu ștergeți cheile de dedup cât există posibilitate de replay. Nu oferă criptare, compactare, backup sau scalare distribuită; nu dublează lucrarea separată de backup.
6. Exact-once la distanță nu poate fi garantat de ledgerul local. Alegerile conservatoare evită reluarea oarbă, cu prețul reconcilierii manuale în caz de cădere. Nu există mesaje de succes presupuse.

Consultați `CONTRACTS.md` pentru sursele și limitele verificării.
