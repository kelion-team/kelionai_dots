# SIWC separat pentru KelionAI

Stare: cod pregătit; fără autentificare reală, grant real, instalare remote sau tură de model. Node.js 24, numai module standard. Modulele nu citesc autentificarea desktop Codex și nu schimbă nucleul, runnerul, baza de date ori probele existente.

Acest pachet este destinat aplicației OSS rulate pe VM-ul deținut de utilizator. Folosește un grant SIWC nou, autorizat de persoană. Suportul acestui flux nu conferă permisiunea de a utiliza autentificarea administrată de Codex într-un serviciu comercial găzduit.

## Fișiere și contract

- `oauth.mjs`: tranzacție OAuth în memorie, PKCE S256/state/nonce, callback exact, client din callback `client_id`, validare OIDC RS256 și permisiuni din scope. Alte algoritme se refuză; compatibilitatea cu semnarea grantului real rămâne de verificat.
- `crypto-store.mjs`: X25519/HKDF-SHA256/AES-256-GCM pentru transfer; se verifică amprenta cheii VM printr-un canal autentificat independent. Plicul are termen de zece minute. Criptarea autentifică integritatea, nu identitatea expeditorului; transferul SSH autentificat și hash-ul verificat furnizează aceasta.
- `cli.mjs`: numai comenzile finite de pregătire, login/export și import. Loginul local ține grantul în memorie și scrie numai plicul criptat. Fișierul local de host conține doar UUID-ul persistent. Selectorul explicit de înregistrare este un fișier separat fără tokenuri sau email: issuer/sub/client_id/local_host_id. Acesta se salvează după validarea OIDC și este reutilizat la următorul login. Pentru alt cont se selectează explicit alt fișier; o înregistrare existentă nu se înlocuiește automat.
- `provider.mjs`: providerul oficial, mediu copil separat și sesiune protejată prin lock. Folosește adaptorul controllerului pentru transport și reconciliere; nu decide modelul/efortul.
- `worker.mjs`, `private-rpc.mjs`, `controller_bridge.py`: adaptor finit `--once`, transport JSON-RPC privat și apelarea controllerului original cu verificarea celor patru hash-uri core. Contractul, gate-urile de activare și limitele reale sunt descrise în [WORKER.md](WORKER.md).
- `protocol-pins.json`, `magentic-source-pins.json`, `magentic-receipt.mjs`: fixarea surselor și conversia request-bound a readback-ului.
- `permissions.mjs`, `linux-preflight.mjs`: profil numit root-deny/minimal-read și verificare Linux cu santinele sintetice, fără inferență.
- `framework-cli.mjs`, `magentic-driver.mjs`, `magentic_store.py`, `owner-poll.mjs`: CLI original pinuit, buget atomic cumulativ și consum finit al cererilor noi owner-gateway; fără planner copiat. Framework-ul real nu a fost rulat aici.
- `install_codex.py`, `install_magentic.py`, `linux-release-pins.json`, `systemd-entry.mjs`, `kelion-siwc.service.in`: pachet finit de instalare/configurare descris în [LINUX.md](LINUX.md), fără activare automată.
- `worker.test.mjs`, `test_worker_http.py`, `http-fixture.py`: RPC sintetic cu HTTP real și SQLite temporar, fără inferență sau OAuth.
- `siwc.test.mjs`: numai date și chei sintetice, fără apeluri externe.

Într-o înregistrare, identitatea este perechea issuer/sub împreună cu client_id. Emailul nu identifică workspace-ul. Un director vault este rezervat unei singure înregistrări selectate explicit. Importul unei alte perechi client/sub în același director se refuză. Host ID-ul VM se păstrează la import.

## Stocare

Pe Linux, operatorul pregătește un director privat 0700, deținut de utilizatorul procesului. Fișierele au 0600; symlinkurile, hardlinkurile și părinții care permit înlocuirea directorului sunt refuzate. Se scrie atomic și se execută fsync. Sesiunea este criptată cu o cheie separată de 32 octeți. Cheia de recipient, cheia vault și datele nu intră în pachetul public.

CLI-ul de pregătire poate fi rulat ca root pe VM-ul existent fără sudo și fără administrare de conturi. Este inclus un template finit DynamicUser/StateDirectory/LoadCredential; căile și UID-ul efectiv se verifică înainte de activare. Binarul Linux și izolarea credențialelor nu sunt încă verificate. Nu se modifică permisiuni globale.

Pe Windows, stocarea privată a secretelor se oprește cu `windows_private_storage_requires_verified_dpapi_and_acl`; DPAPI nu a fost implementat și nu este pretins ca disponibil. Login/export nu scrie secret în clar pe laptop. Cheile și tokenurile nu sunt trimise în argv, stdout sau loguri. Mediu `ACCESS_TOKEN` există doar în obiectul transmis copilului; nu se schimbă `process.env`.

Fișierele de host/recipient și plicurile nu trebuie comise. Publicarea se face numai din lista explicită din raport; niciun glob recursiv care include directoare private. `.gitignore` este protecție suplimentară, nu control de acces.

## Provider și reconciliere

`withProviderSession({vault, adapter, executable, codexHome})` cere director Codex propriu privat, executabil absolut și grant valid. Env-ul nu moștenește chei API, configurația desktop sau NODE_OPTIONS. Nu există fallback de facturare.

Adaptorul trebuie să implementeze:

1. `reconcileBeforeResume()`: citește jurnalul controllerului, păstrează contabilitatea inițială și aruncă eroare pentru orice acceptare necunoscută a unei ture. Modulul nu schimbă acel jurnal.
2. `usePrivateTransport(child, initialize)`: consumă stdin/stdout JSON-RPC în memorie, fără forward în log; așteaptă confirmarea initialize, emite initialized, apoi poate relua thread-ul salvat numai după reconciliere. Mesajul initialize include `capabilities.experimentalApi=true`, cerut de `thread/start.historyMode` pentru versiunea fixată 0.162.0-alpha.17.2 verificată de controller. Negocierea nu acordă singură drept de inferență. Returnează `{initializeAcknowledged:true, initializedSent:true, reconciled:true, activeTurn:false}` doar după readback verificat. `turn/start` necesită autorizarea separată a controllerului; această funcție nu o acordă.

Restartul găsit în fazele running, child_start_intent, refresh_pending, reconciling sau needs_reconcile se blochează. Lockul rămas după crash nu este eliminat automat. Operatorul/adaptorul trebuie să stabilească dacă procesul anterior a murit și ce s-a întâmplat cu operația înainte de a reface starea; nu se repetă orb cererile.

Reînnoirea se serializează sub același lock și se înregistrează înaintea cererii. Credencialele rotite se salvează împreună. La invalid_grant/revocare se șterg tokenurile inutilizabile din vault, dar se păstrează identitatea înregistrării. Eșecul sau rezultatul incert blochează reluarea. Copilul este oprit înainte de expirare; reluarea ulterioară cere reconciliere și inițializare nouă.

Reînnoirea urmează regula documentată în Accounts and sessions: aproape de expirarea access tokenului. În acest adaptor, cererile sunt acceptate numai în ultimele 60 de secunde sau după expirare; o încercare prematură se oprește înainte de rețea cu `refresh_too_early`. Documentația enumeră `earliest_refresh_at`, fără format/unitate: valoarea din răspuns se păstrează ca metadată opacă și nu se interpretează drept timestamp sau interval. Refuzul backendului și rezultatul incert rămân blocante; nu se repetă automat cererea.

`responseContract` permite numai input de mesaje text în array, `store:false`, `stream:true`. Nu adaugă audio sau transcription. Configurarea app-server folosește `wire_api=responses`, `requires_openai_auth=false`, `supports_websockets=false`. Respectarea exactă a request body de binarul app-server rămâne de verificat la integrarea autorizată. `model/list` nu dovedește eligibilitatea; numai o tură reală încheiată cu status completed o poate demonstra pentru cererea respectivă.

## Comenzi pregătite, neexecutate

În aceste exemple `$PRIVATE`/`$PUBLIC`/`$INCOMING` sunt căi alese și verificate de operator, în afara surselor publice. Păstrați cheile pe VM. Nu înlocuiți fingerprintul sau hash-ul cu valori primite prin canal neautentificat.

Pe VM Linux, după verificarea versiunii Node, din checkout:

```sh
umask 077
mkdir -m 700 "$PRIVATE"
node service/siwc/cli.mjs prepare-recipient "$PRIVATE" "$PUBLIC/recipient.json"
```

Transferați numai recipient.json la laptop prin SSH verificat. Verificați separat fingerprintul anunțat pe VM. Pe laptop, după autorizarea persoanei pentru login:

```text
node service/siwc/cli.mjs login-export recipient.json VERIFIED_SHA256 local-host.json grant.envelope.json selected-registration.json
```

Comanda afișează doar un URL loopback; deschideți-l și selectați Continue with ChatGPT. Nu se deschide automat browserul. La prima utilizare se creează selectorul fără tokenuri; ulterior se refolosește exact client_id, identitatea și host-ul, cu state/nonce/PKCE proaspete, fără agent_name_hint. Hinturile opționale de ID token sunt omise. Fără ultimul argument, selectorul implicit este `local-host.json.registration.json`. Selectorul conține un identificator pseudonim de cont: deși nu este un secret de autentificare, păstrați-l în afara pachetului public. După validarea OIDC, grantul se criptează pentru VM. Transferați plicul prin SSH și comparați SHA256 al fișierului prin același canal autentificat, apoi pe VM:

```text
node service/siwc/cli.mjs import PRIVATE_DIRECTORY INCOMING_ENVELOPE VERIFIED_ENVELOPE_SHA256
```

Importul verifică din nou ID tokenul prin JWKS oficial, păstrează ID-ul VM și refuză replay-ul. Nu pornește modelul. VM-ul devine deținătorul reînnoirilor; laptopul nu păstrează grantul. Nu rulați alt proprietar de refresh cu aceeași sesiune.

Test offline:

```text
node --test service/siwc/siwc.test.mjs service/siwc/worker.test.mjs
```

Testul real de filesystem POSIX este omis pe Windows; trebuie executat pe Linux înaintea folosirii vault-ului. Testele Windows verifică refuzul stocării nesecurizate. Nu există probă OAuth, entitlement sau app-server live în aceste rezultate.

Workerul rămâne dezactivat implicit. Extinderea autorizată a `service/server.py` și `service/store.py` furnizează contractul privat atomic și markerul clientului autentificat, fără schimbarea schemei DB, runnerului vechi ori probelor reale. Configurarea CLI verificată fără inferență nu dovedește izolarea secretelor: `unified_exec` rămâne true în `features list` chiar cu disable. Activarea cere grantul real, politica operațională, cotă inclusă disponibilă și dovada izolării. Trei intenții este limita tehnică a fluxului normal; Magentic are limite finite separate per job și sesiune. Nicio cifră nu este atribuită utilizatorului ca aprobare explicită. Nu se cere istoric completed înainte de prima inferență și nici o autoritate de semnare separată. Profilurile numite sunt implementate; verificarea Linux rămâne necesară. Detalii în WORKER.md și LINUX.md.

## Surse oficiale consultate la 2026-10-13

- [Registration and sign-in](https://developers.openai.com/siwc/token-sharing-open-source/sign-in)
- [Self-hosted VMs](https://developers.openai.com/siwc/token-sharing-open-source/self-hosted-vms)
- [Codex app-server](https://developers.openai.com/siwc/token-sharing-open-source/codex-app-server)
- [Discovery și validare OIDC](https://developers.openai.com/siwc/website)
- [Accounts and sessions](https://developers.openai.com/siwc/token-sharing-open-source/profiles-and-sessions)
- [Token reference](https://developers.openai.com/siwc/token-sharing-open-source/token-reference)
- [Errors and recovery](https://developers.openai.com/siwc/token-sharing-open-source/errors-and-recovery)
- [App Server și limite de utilizare a autentificării Codex](https://learn.chatgpt.com/docs/app-server)

Implementare originală a contractului documentat, fără copiere de client terț, fără biblioteci externe și fără schimbarea licențelor proiectului. Publicarea și instalarea rămân acțiuni distincte de pregătirea acestui cod.
