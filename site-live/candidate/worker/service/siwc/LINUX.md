# Pregătire Linux finită, fără activare implicită

Aceste comenzi sunt livrate pentru controller; nu au fost executate remote. Instalatoarele scriu numai într-o destinație nouă, păstrează instalările anterioare și nu pornesc servicii, OAuth sau modele. Nu folosesc sudo, useradd, abonamente sau chei API.

## 1. Dependențe publice

Din rădăcina sursei publice verificate, alegeți directoare noi sub prefixul de instalare deja autorizat. Exemplele de mai jos folosesc `/opt/kelion-siwc`; prefixul părinte trebuie să existe și să nu permită înlocuirea de către utilizatori neautorizați.

```sh
python3 service/siwc/install_codex.py --destination /opt/kelion-siwc/codex-0.162.0-alpha.17.2
python3 service/siwc/install_magentic.py --recovered-source .runtime/magentic-recovered --destination /opt/kelion-siwc/framework-2d58876 --install-dependencies
```

Primul descarcă exclusiv asseturile Codex și bwrap din [release-ul oficial fixat](https://github.com/openai/codex/releases/tag/rust-v0.162.0-alpha.17.2), verifică SHA256 publicate în [lista oficială de asseturi](https://github.com/openai/codex/releases/expanded_assets/rust-v0.162.0-alpha.17.2), respinge arhive cu traversal/linkuri, verifică versiunea și generează schemele pentru toate cele nouă hash-uri revizuite. Păstrează arhivele și `installation.json`; nu declară că sandboxul funcționează. Divergența protocolului oprește instalatorul în starea staged, fără activare.

Al doilea copiază byte-for-byte cele șase fișiere recuperate în `source/orchestration/magentic_candidate` și registrul original în `source/orchestration/native_roles.json`. Instalează într-un venv numai pachetele directe fixate `agent-framework-core==1.21.0`, `agent-framework-orchestrations==1.3.1`, din `https://pypi.org/simple`, cu metadatele/licențele distribuțiilor păstrate. Rulează `runtime.verify_versions()`: verifică versiunile și cele șase hash-uri upstream din sursa originală, fără init/advance/model. Nu schimbă sursele ca să facă o dependență incompatibilă să treacă.

Node 24 existent și Python 3.12 existent sunt suficiente pentru adaptor. Framework-ul se folosește cu `framework_python=/opt/kelion-siwc/framework-2d58876/venv/bin/python` și `framework_source_root=/opt/kelion-siwc/framework-2d58876/source`. PATH-ul procesului trebuie să includă directorul `codex-…/bin` pentru bwrap; nu se modifică PATH global.

## 2. Verificarea Linux fără grant

Pregătiți un director privat nou, owned de UID-ul efectiv, apoi fișierul public preflight-settings.json cu căi absolute:

```json
{
  "codex_executable":"/opt/kelion-siwc/codex-0.162.0-alpha.17.2/bin/codex",
  "python_executable":"/usr/bin/python3",
  "protocol_directory":"/opt/kelion-siwc/codex-0.162.0-alpha.17.2/protocol",
  "preflight_root":"/var/lib/kelion-siwc-preflight"
}
```

```sh
node service/siwc/linux-preflight.mjs preflight-settings.json
SIWC_TEST_PYTHON=/usr/bin/python3 SIWC_TEST_PROTOCOL=/opt/kelion-siwc/codex-0.162.0-alpha.17.2/protocol node --test service/siwc/siwc.test.mjs service/siwc/worker.test.mjs
python3 -m unittest discover -s service/siwc -p 'test_*.py' -q
```

În Linux testul POSIX vault rulează efectiv. Framework-driver testul este explicit fixture de contract; subprocessul sintetic verifică argv/env/surse, nu pretinde progres Magentic real. Preflight-ul cere funcționarea reală a sandboxului cu profilul numit și toate santinelele refuzate. Un eșec se investighează; nu se dezactivează izolarea. Nu creați `credential_isolation_verified:true` înaintea rezultatului real.

## 3. Grant SIWC nou

Recipientul se generează pe VM sub UID-ul care va importa/citi vault-ul, într-un director nou 0700. Metadatele publice se transferă pe laptop; cheia privată nu părăsește VM-ul. Comenzile sunt finite:

```sh
node service/siwc/cli.mjs prepare-recipient /absolute/private/vault /absolute/public/recipient.json
```

Pe laptop, amprenta recipientului trebuie verificată prin canalul autentificat al controllerului. Browserul cere acțiunea umană Continue with ChatGPT; nicio autentificare desktop nu se reutilizează:

```sh
node service/siwc/cli.mjs login-export recipient.json VERIFIED_RECIPIENT_FINGERPRINT local-host.json transfer-envelope.json selected-registration.json
```

Ultimul argument selectează înregistrarea; dacă există, se reutilizează client_id/host fără înregistrare dinamică repetată, cu state/nonce/PKCE noi. Metadatele nu conțin token, dar sunt private față de pachetul public. Plicul criptat și SHA256 se transportă prin canalul autentificat. Pe VM:

```sh
node service/siwc/cli.mjs import /absolute/private/vault transfer-envelope.json AUTHENTICATED_ENVELOPE_SHA256
```

Importul verifică din nou ID token/scopes. Nu dovedește accesul efectiv la fiecare model. Prima tură inclusă, aleasă de controller, este încercarea limitată; numai finalul confirmat stabilește accesul pentru acea cerere. Cota observată trebuie să fie reală, curentă și legată de cont; nu există endpoint inventat account/read.

## 4. Configurare și pornire finită

`WORKER.md` definește documentele locale și politica owner-gateway. `private_root` conține toate căile private ale workerului (config, readiness, vault, joburi, codex-home), cu excepția LoadCredential verificat. Workspace-ul este un director separat gol. Calculele canonical JSON/SHA se fac cu funcțiile exportate, nu prin hasharea JSON cu spații arbitrare. `runtime.permission_profile_sha256` este hash-ul rezultatului `permissionConfiguration({workspace,protectedPaths:[private_root,...credentialDirectoryIfUsed]})`. Același runtime exact se transmite serviciului API.

Pentru poll, config are în plus `session_state_root`, `session_jobs_root`, `private_root`, `framework_python`, `framework_source_root`, `readiness_file`; directoarele sunt pregătite 0700. `max_idle_polls` este implicit 30 și `poll_ms` 2000. Configurațiile/framework/jurnalele individuale se creează automat după admiterea taskului; nu se editează runtime-ul pentru fiecare cerere nouă din web.

```sh
node service/siwc/worker.mjs --poll /absolute/public/worker-settings.json
```

Settings conține `{"enabled":true,"private_config":"/absolute/private/config.json"}` numai după grant, allowance/readiness și izolarea reală. `--once` rămâne disponibil pentru un job exact. Ambele sunt inactive implicit. Nicio unitate de timer sau buclă nelimitată nu este instalată.

`kelion-siwc.service.in` este alternativa DynamicUser: înlocuiți toate placeholder-ele cu căi revizuite, fără shell sau secrete inline. `systemd-entry.mjs` verifică că private_root este exact STATE_DIRECTORY, iar config/token/key sunt cele din LoadCredential. Configurația și fișierele persistente trebuie provizionate pentru UID-ul efectiv/StateDirectory prin systemd; nu presupuneți că un vault root-only creat anterior poate fi citit de DynamicUser. Rulați santinelele în contextul efectiv înainte de activare. Template-ul nu este instalat și nu schimbă permisiuni globale.

Rollbackul este oprirea explicită a workerului și selectarea versiunii publice anterioare după verificarea stării. Păstrați vault-ul, marker-ele, toate jurnalele și bugetele; nu ștergeți lockul incert, nu reimportați tokenuri vechi și nu creați taskuri clone. O versiune veche nu trebuie pornită pe un jurnal necunoscut fără reconciliere. Directoarele noi staged pot rămâne pentru audit; instalatorul nu suprascrie niciun release.
