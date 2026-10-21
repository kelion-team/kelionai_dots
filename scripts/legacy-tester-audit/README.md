# Diagnostic corect pentru testerul legacy Kelion

**Stare: patch pregătit, neinstalat. Nu este o reparație LIVE și nu demonstrează acceptanța portalului.**

## Constatare măsurată — 21 octombrie 2026

Citirea read-only a `/var/lib/kelion-senzori/tester-ui.json`, rularea
`22:03:10 Europe/London` (`21:03:10 UTC`), arată:

| Măsurare locală legacy | Rezultat |
| --- | --- |
| 7 pagini × 2 lățimi (1280/390 px) | 14/14 marcate eșuate |
| HTML principal | 200 pentru toate 14 |
| Singura resursă HTTP eșuată în fiecare caz | `404 /app/control-api/state` |
| Date afișate | 0,98–2,24 s |
| Reîmprospătare | 3–4 s |
| Eveniment → ecran, oglindă | 3,90 s / 4,27 s, sub pragul 5 s |

Acestea sunt **măsurători ale adaptorului local**, nu ale întregului traseu LIVE.

### De ce 404 nu dovedește o pagină LIVE defectă

- `/opt/kelion-brain/tester-ui.py` servește `/app/` din fișierul legacy
  `/var/www/kelion/app/index.html`. Proxy-ul său acoperă `/app/api/` și
  `/aparat/api/` către serviciul 4190, nu `/app/control-api/state`.
- Configurația activă `/etc/caddy/Caddyfile`, citită separat, rutează `/app/`,
  `/app/cont`, `/app/control-api/*` și `/app/control-assets/*` către portalul
  `127.0.0.1:8094`, după autentificarea OAuth. Fișierul legacy nu este pagina
  portalului servită la `/app/` de Caddy.
- `OAuthVerifier` din `/opt/kelion-control/portal_service.py` ignoră antetele
  de identitate ale clientului și verifică sesiunea prin serviciul OAuth.
  Nu am copiat credențiale, introdus o identitate falsă sau modificat autentificarea.
- `site-live/web/**` și workflow-ul web din acest repository nu sunt sursa
  testerului ori a paginilor legacy. O modificare web aici nu repară acel adaptor.

## Modificare pregătită

- Păstrează toate erorile brute, toate măsurătorile și pragul de 5 s.
- Afișează URL-ul și statusul HTTP, anterior omise din sumar.
- Declară `surface=legacy-static-local`, `live_acceptance=false`,
  `coverage_gaps`; rezultatul local separat este `legacy_ok`.
- Vechiul câmp global `ok` rămâne fals pentru a nu permite consumatorilor vechi
  să transforme testul local în acceptanță LIVE. Câmpurile `pagini[].ok` rămân
  neschimbate. Consumatorii trebuie actualizați ulterior să prezinte explicit
  „acoperire LIVE neverificată”, nu să ascundă starea.
- Nu pune în coada proprie o reparație de aplicație dacă singura problemă este
  ruta locală absentă `control-api/state` și toate celelalte verificări trec.
  Păstrează diagnosticarea și coada pentru alte erori sau erori mixte.
- Mesajele către coadă identifică corect suprafața locală; nu mai cer modificări
  LIVE pe baza unui test local.
- Nu schimbă transportul, permisiunile, autentificarea, orarul monitorizării,
  serviciile, fișierele utilizatorului sau coada generală `kelion-remediere`.

## Pregătire cu protecție contra modificării sursei

Sursa canonicală rămâne pe Contabo. Nu este publicată integral aici.
`prepare.py` citește o copie autorizată, refuză orice alt hash și produce numai
un fișier `.patch` nou. Nu are comandă de instalare și nu suprascrie fișiere.

```sh
python3 scripts/legacy-tester-audit/prepare.py \
  --source /cale/copie-autorizata/tester-ui.py \
  --output ./tester-diagnostic.patch
```

Sursa examinată are 13.280 octeți; SHA256 al conținutului citit:
`b5bc8440d0afd91571c457f35deb7f288acccc39a34ab21128e9ece508d263f4`.

Candidat generat din această sursă:
`8262c5d2b9e1b9719733b157405cb7a9d386558e161d7b74083fb25ad294695e`.

Patch contextual pregătit:
`db24fc55ae6ca692594640a2034763996a191eaaaae811a3c26cfdd8eff188ba`.

Un hash diferit este un blocaj pentru revizuire, nu motiv să dezactivezi verificarea.
Fișierul `.patch` este un artefact pentru revizuire, nu o autorizație de aplicare.

## Verificare offline

```sh
python3 -B -m unittest discover -s scripts/legacy-tester-audit -p 'test_*.py' -v
```

18 teste; fixture sintetic, fără secrete/date de client. Testele blochează socketuri
și `urlopen`, simulează Chromium și coada și verifică citirea rezultatului scris.
Acoperă 14 eșecuri de rută fără reparație eronată, erori reale/mixte păstrate,
pragul 5 s, lipsa falsului verde LIVE, sumarul exact și refuzul sursei modificate.
Testele nu reprezintă o rulare reală de browser sau o verificare LIVE.

## Ce rămâne deschis

Aplicarea cere o etapă autorizată separată pe sursa Contabo, fără atingerea
modificărilor preexistente. Acceptanța portalului cere un test pe rutele reale
Caddy cu un context autentificat aprobat, fără extragerea secretelor și fără
ocolirea autentificării. Repetarea lucrărilor din coada generală și starea murdară
a proiectului sunt probleme separate; acest patch nu pretinde că le rezolvă.

Nu există modificări în `site-live/web/**`, deci acest PR nu declanșează
workflow-ul de publicare web. Nu s-a executat nicio instalare sau repornire.
