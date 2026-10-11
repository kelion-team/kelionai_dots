# KelionAI Dots — agenți din GitHub

Repository pentru scanare secvențială, surse cu versiuni exacte, teste și dovezi înaintea importului în secțiunea Agenți din ChatGPT.

## Regula de acceptare

Un rezultat de căutare sau un procent din README nu este o verificare funcțională. Catalogul de import rămâne gol pentru orice agent cu teste eșuate, erori, verificări obligatorii neexecutate sau execuție AI reală neverificată. Nu reparăm codul proiectelor respinse și nu dezactivăm teste ca să treacă.

- `catalog/scan.json`: proiecte inspectate individual, pagini parcurse, surse, versiuni și posibile dovezi de măsurare. Mențiunile automate necesită verificare; pot desemna un benchmark, un tutorial, o simulare sau un proiect fără agent executabil.
- `catalog/agents.json`: verificările locale și limitele lor.
- `catalog/import-ready.json`: numai agenți validați pentru import; este separat de candidați.
- `results/`: rezultate reale ale testelor, inclusiv ale proiectelor respinse.
- `vendor/`: submodule cu sursele care au trecut testele locale selectate. Licențele autorilor sunt păstrate.
- `locks/`: versiuni ale dependențelor instalate și testate.

## Instalare și verificare

Necesită Python 3.12, Git și `uv`. Folosim checkout-ul existent; nu creăm worktree-uri pentru mediul cloud.

```bash
bash scripts/install.sh
python scripts/validate.py
python scripts/scan_github_api.py
python scripts/check_upstream_tests.py
python scripts/report_scan.py
```

Scanarea prin API necesită GitHub CLI și autentificarea injectată în mediu. Este secvențială și reluabilă. `api_coverage` păstrează paginarea și completitudinea fiecărei căutări. Nu declară că a acoperit toate repository-urile GitHub. Rezultatele inaccesibile, limita de 1.000 de rezultate pe căutare și HTTP 429 sunt înregistrate, nu interpretate ca absență a agenților. GitHub poate omite proiecte private, neindexate sau fără termenii căutați. `scan_github.py` oferă o variantă de rezervă prin paginile publice.

Testele offline folosesc și modele deterministe/mocks ale autorilor. Ele verifică implementarea și execuția instrumentelor, nu reproduc scorurile publicate pentru LLM-uri. Verificările CI eșuate, inclusiv controalele documentației, sunt păstrate în raport și împiedică aprobarea pentru import.

## Costuri și execuție AI reală

Scanarea GitHub, pregătirea repository-ului și testele locale nu necesită un abonament AI suplimentar. Nu solicitați o cheie OpenRouter pentru configurarea acestui mediu. Utilizatorul nu a autorizat cumpărarea unor servicii sau apeluri AI plătite.

Pentru verificări AI reale, prioritizați agenți care pot rula cu modele locale și înregistrați configurația modelului, rezultatele sarcinilor și măsurătorile efective. Disponibilitatea unui model local nu dovedește că agentul a trecut verificările. Candidații care depind de servicii indisponibile rămân neaprobați, fără a cere utilizatorului un abonament nou.

`scripts/run_mini.py` este un adaptor de diagnostic OpenRouter păstrat din verificările anterioare; nu este necesar pentru instalare, scanare sau testele locale și nu trebuie executat fără autorizarea explicită a costurilor. Sursele mini-swe-agent sunt respinse pentru verificări CI eșuate.

Codul din acest repository nu creează automat o intrare în interfața ChatGPT; importul ulterior depinde de funcția și formatul oferite de acea interfață.
