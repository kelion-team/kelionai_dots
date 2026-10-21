# Export local revizuit, apoi publicare explicită

**Nu a fost rulat pe Contabo. Nu s-au folosit tokenuri reale, rețeaua sau GitHub în teste.**
Fișiere necesare alăturate: `copie-server-in-github.sh` și `export_safe.py`.
Dependențe: Python 3.9+; `git` numai la publicare. Nu instalează pachete.

## A. Pregătire pe server (fără rețea și fără token)

```bash
bash copie-server-in-github.sh prepare --output /root
```

Creează un director unic, privat, `copie-contabo-*`, afișează calea și SHA-256 pentru `inventar.json`. Salvează digestul afișat **acum**, nu îl recalcula pentru a accepta modificări ulterioare.

Revizuiește local:
- `inventar.json`: fiecare cale, mărime, SHA-256;
- `excluse.json`: căile excluse și motivul, fără valorile secretelor;
- **conținutul fiecărui fișier** din `server/`, nu doar lista sau unitățile systemd.

Nu partaja inventarul sau fișierele neexaminate dacă pot conține informații private. O listă de nume/hash-uri nu dovedește absența datelor/secrețelor. Scannerul are tipare limitate; codul și configurările pot conține date pe care nu le recunoaște. Dacă găsești date sau secrete, NU publica; remediază selecția/redactarea și generează o pregătire nouă.

Rădăcini: exclusiv `/opt/kelion-pod`, `/opt/kelion-brain`, `/opt/kelion-control`, plus unitățile `kelion-*` și drop-in-urile din `/etc/systemd/system`. Cod: py/sh/js/mjs/css/html. Configurări: lista explicită din `CONFIGS`. Fișierele sunt limitate la 2 MiB. Fișiere necitibile/UTF-8 invalid și suspecte sunt excluse; erorile de parcurgere, unitățile necitibile și formele systemd ambigue opresc pregătirea.

Conservator: legăturile simbolice, hardlink-urile și fișierele speciale din căile neexcluse opresc operația. Directoarele excluse (de exemplu venv și node_modules) nu sunt parcurse; staging-ul este verificat integral, fără excluderi. Escape-urile din directivele sensibile systemd sunt refuzate în loc de a ghici decodarea. Orice duplicare a unei valori redactate în alt loc al unității, chiar nevinovată, poate opri pregătirea.

## B. Publicare numai după revizuirea de mai sus

Înlocuiește cele două valori cu directorul și digestul afișate la A:

```bash
bash copie-server-in-github.sh publish /root/copie-contabo-EXEMPLU \
  --approved-manifest-sha256 DIGESTUL_SALVAT_LA_PASUL_A
```

1. Verifică digestul inventarului și lista exactă cale/mărime/hash.
2. Cere `DA`, explicit pentru inventarul afișat. Orice alt răspuns oprește.
3. Reverifică înainte de token. Cere tokenul ascuns numai într-un terminal interactiv.
4. Verifică prin API că ținta fixă `kelion-team/kelion-brain` este privată și tokenul are push.
5. Clonează într-un director temporar unic. Refuză dacă `server` există deja.
6. Copiază numai fișiere regulate și reverifică sursa, copia și conținutul efectiv din indexul git (inclusiv tipul fișierelor). Nu adaugă alte rapoarte neexaminate.
7. Creează o ramură nouă aleatoare `copie/contabo-*`. Verifică din nou caracterul privat și face push numai pe acea ramură; **nu modifică main**.
8. Afișează commitul și linkul pentru **crearea** PR-ului. Nu pretinde că a creat PR automat.

Token: fine-grained, exclusiv depozitul țintă, Contents read/write, expirare scurtă. Nu îl trimite în chat. Scriptul nu îl pune în argumentele proceselor, URL sau configurația Git; git îl primește prin mediul procesului. Root sau procese cu aceleași privilegii pot accesa memoria/mediul: nu rula pe un server compromis. Revocă tokenul după utilizare. O eroare de push poate fi ambiguă (serverul poate primi commitul înaintea pierderii răspunsului); verifică ramurile înainte de o reîncercare.

## Dovezi locale

```bash
python3 -m unittest -v test_export_safe.py
```

22 teste sintetice: selecție, redactare systemd și continuări cu comentarii, UTF-8/permisiuni, symlink/FIFO, erori de parcurgere, manifest/fișiere schimbate, înlocuire de cale cu același număr de fișiere, repetări unice, confirmare anulată și mutație după DA, repo neprivat/neautorizat. Un test cap-coadă folosește **git local real cu un depozit bare fictiv**; API-ul și transportul sunt înlocuite local. Verifică o ramură nouă, main neschimbat, conținut exact și token fictiv absent din argv. Nu probează accesul real, API-ul real sau serverul live.

Manifestul nu este semnat și nu protejează împotriva unui atacator cu root sau același UID care poate modifica simultan scriptul și memoria. Directorul privat și revalidările protejează fluxul de revizuire împotriva modificărilor accidentale și a substituțiilor testate, nu garantează un sistem compromis.
