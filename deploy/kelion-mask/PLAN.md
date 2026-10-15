# Instalare verificabilă pe kelion-nou
Autor implementare: Kelion. Revizor: Claude. Fără editarea fișierelor lui Claude.

Obiectiv: aplicare explicită a fișierelor unui commit verificat, fără pierderea modificărilor LIVE, cu backup și rollback condiționat de hash.

Fișiere proprii: deploy/kelion-mask/deploy_files.py, test_deploy_files.py, kelion-app-server.service, README.md.

Pași:
1. Teste finite pentru hash sursă greșit, drift LIVE, traversare/symlink, aplicare+readback, rollback, rollback refuzat după altă modificare, păstrarea modului.
2. Implementare stdlib Python: manifest exact path/source_sha256/expected_current_sha256; verificare integrală înainte de scriere; backup și jurnal; înlocuire atomică per fișier; rollback verificat. Nu pretinde atomicitate globală între fișiere.
3. Unitate separată app-server pe 127.0.0.1:18767 cu CODEX_HOME existent; fără port public și fără tokenuri în sursă.
4. Claude verifică codul și probele înainte de folosire LIVE. Activarea efectivă se face numai după reconcilierea bazei cu frontendul lui Claude.

Nu creează credențiale, nu reinstalează pachete, nu schimbă celelalte servicii și nu pornește inferență. Regenerarea tokenului autorizat este un pas distinct, fără afișare.
