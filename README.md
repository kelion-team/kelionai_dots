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

## Execuție AI reală

Configurați în setările securizate ale mediului `OPENROUTER_API_KEY` și modelul `KELION_MODEL`. Nu puneți chei în Git sau în chat. Un abonament ChatGPT nu este o cheie OpenRouter.

```bash
../agent-runtime/mini-swe-venv/bin/python scripts/run_mini.py \
  --task 'Execute printf 5, then submit the answer 5.' \
  --cwd /tmp/kelion-smoke --output /tmp/kelion-smoke-result.json
```

Până la validarea acestei execuții, agentul nu este declarat pregătit pentru import. Codul din acest repository nu creează automat o intrare în interfața ChatGPT; importul ulterior depinde de funcția și formatul oferite de acea interfață.
