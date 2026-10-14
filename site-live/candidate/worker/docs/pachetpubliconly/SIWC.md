# Conținutul public SIWC

Pachetul este pregătit local, fără publicare sau deployment. Include exclusiv:

```text
service/siwc/.gitignore
service/siwc/README.md
service/siwc/oauth.mjs
service/siwc/crypto-store.mjs
service/siwc/provider.mjs
service/siwc/cli.mjs
service/siwc/siwc.test.mjs
service/siwc/WORKER.md
service/siwc/worker.mjs
service/siwc/private-rpc.mjs
service/siwc/controller_bridge.py
service/siwc/protocol-pins.json
service/siwc/worker.disabled.json
service/siwc/worker.test.mjs
service/siwc/http-fixture.py
service/siwc/test_worker_http.py
service/siwc/magentic-receipt.mjs
service/siwc/magentic-source-pins.json
service/siwc/magentic_store.py
service/siwc/magentic-driver.mjs
service/siwc/framework-cli.mjs
service/siwc/owner-poll.mjs
service/siwc/permissions.mjs
service/siwc/linux-preflight.mjs
service/siwc/install_codex.py
service/siwc/install_magentic.py
service/siwc/linux-release-pins.json
service/siwc/kelion-siwc.service.in
service/siwc/systemd-entry.mjs
service/siwc/LINUX.md
service/siwc/test_magentic_http.py
service/siwc/test_installers.py
docs/pachetpubliconly/SIWC.md
```

Lista și SHA256 pentru fiecare fișier se găsesc în `results/repair-2026-10-13/siwc-owner-worker-report.json`. Raportul descrie probe sintetice și limitele rămase, nu o autentificare reușită.

Nu includeți: directorul private, autentificare Codex desktop, chei de recipient/vault, sesiuni criptate, granturi, plicuri de transfer, metadate ale contului, jurnale operative sau fișiere locale de host. Transferul public se construiește după lista de mai sus, fără copiere recursivă a directorului service.

Modificările autorizate de integrare sunt `service/server.py` și `service/store.py`; hash-urile lor sunt în raport. Ele trebuie integrate în versiunea serviciului de către controller, nu suprascrise separat peste o instanță activă. Nu se reconstruiește aici pachetul ingress/web și nu se include baza de date.

Adaptorul finit, driverul CLI Magentic și API-ul privat sunt implementate și testate sintetic. Poll-ul finit admite taskuri noi din gatewayul owner pe politică privată, fără redeploy per mesaj; proveniența verificată este bearerul dedicat, nu un email Google inventat. Pașii OAuth, transferul autentificat, importul, instalarea Linux, dovada izolării și o verificare reală de acces rămân pendinte în `service/siwc/LINUX.md`. Framework-ul real nu a fost executat aici. Niciun abonament nou, API key, tură reală de model sau schimbare a bugetului probei native nu este inclusă.

Closure-ul workerului include cele patru surse core originale și `service/PROVENANCE.json` la căile lor existente, plus cele șase fișiere originale din `.runtime/magentic-recovered/` cu hashurile fixate. Pachetul separat de surse worker le include byte-for-byte. Schemele AppServer se generează pe executabilul fixat și se verifică față de protocol-pins.json; nu se împachetează directorul private. API-ul existent are separat dependențele `server.py`, `store.py`, `mcp_protocol.py`, `siwc/magentic_store.py`, core și PROVENANCE; controllerul deține pachetul de serviciu/web complet. Arhiva workerului nu reîmpachetează ingressul sau frontendul.
