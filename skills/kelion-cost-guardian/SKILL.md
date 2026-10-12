---
name: kelion-cost-guardian
description: Optimize KelionAI agent, ChatGPT Work, Codex and connector task costs without losing Premium, DOTS, available models, permissions or features. Invoke for every KelionAI task needing economical model/effort selection, budget-aware orchestration, escalation after verified failure, plugin calls, or spend audit. Choose only from verified entitlements and actual connector controls; never claim automatic platform changes without proof.
---

# Kelion Cost Guardian — regulator pe cerință

Optimizează **munca efectuată**, nu abonamentul. Păstrează Business Premium, DOTS, Work, Codex, istoricul, pluginurile și modelele accesibile. **Nu dezactiva niciun model sau conector.** Nu cumpăra credite, nu adăuga locuri, nu activa reîncărcări automate și nu modifica permisiuni fără fluxul de aprobare aplicabil.

## Procedură obligatorie pentru fiecare cerință

1. Identifică suprafața reală: `chat`, `work`, `codex` sau `agent`; notează agentul și instrumentele necesare. Dacă nu e nevoie de execuție agentică, folosește conversația obișnuită, fără să lansezi Work/Codex inutil.
2. Verifică **din interfața/conectorii disponibili efectiv** modelele, nivelurile de raționament, permisiunile și accesul abonamentului. Consultă `references/capabilities.md`. Necunoscut ≠ disponibil. Nu folosi numele unei variante ca dovadă de acces. Pentru conector, separă modelul gazdă de modelul intern: majoritatea pluginurilor nu oferă schimbarea modelului intern.
3. Evaluează cerința pe patru niveluri: **1 Economic** (extracții/formatări simple), **2 Standard** (cod și fluxuri obișnuite), **3 Avansat** (arhitectură, integrare dificilă), **4 Critic** (securitate, producție, date sensibile sau risc ridicat). Aplică un nivel minim corespunzător riscului; nu sacrifica testele ori revizia de securitate.
4. Folosește `scripts/route.py` cu manifestul de modele/conectori **verificat pentru sesiunea țintă** și cerința JSON. Scriptul oferă doar recomandări, exclude modelele cu tarif suplimentar și refuză eligibilități neverificate. Manifestul din `references/manifest-template.json` este intenționat neverificat; nu-l transforma în date reale fără control direct.
5. Selectează modelul/raționamentul prin selectorul *oficial* al Work/Codex sau al agentului, **numai dacă acel control există**. Dacă conectorul are un selector intern documentat și confirmat, folosește-l; altfel reglează modelul gazdă, apelurile și cantitatea de date. Un skill nu poate forța arbitrar modelul intern al unui serviciu terț.
6. Execută o singură delegare necesară la un moment dat; refolosește context, rezultate intermediare, hashuri și verificările deja trecute. Evită apelurile repetate, răspunsurile supradimensionate și procesarea acelorași fișiere. Nu elimina verificări critice pentru economie.
7. Dacă o încercare eșuează **verificat**, escaladează cu un nivel, păstrând rezultatele valide; la nivelul 4 cere diagnostic, nu repeta automat aceeași operație. Nicio escaladare doar din impresie, fără probă de eșec.
8. Raportează pentru cerință: nivel, model și raționament **selectate efectiv sau doar recomandate**, conector folosit și control disponibil, motivul escaladării, cost observat dacă există telemetrie oficială. Economiile în % se raportează **numai din două măsurători comparabile**; cost_rank este doar o ordine euristică, nu tarif.

## Script de planificare (offline)

```bash
python scripts/route.py --manifest references/manifest-template.json <<'JSON'
{"task":"Rezumă documentul de test","surface":"work"}
JSON
```

Manifestul implicit nu activează niciun model: planul va fi `blocked_no_verified_included_model`. Acesta este comportament corect până la confirmarea modelelor în workspace. Exemplu de manifest pentru teste în `tests/test_route.py`; este **simulare**, nu dovadă de model activ sau de consum real.

## Semnale de protecție

- `dispatch_performed=false` și `settings_changed=false` din script sunt adevăruri despre **script**, nu despre alte acțiuni executate separat.
- Pentru plăți, schimbări de abonament, ștergeri, deploy-uri și permisiuni, respectă aprobările platformei; un rezultat `plan_only` nu autorizează execuția.
- Nu actualiza un registru de agenți ca `published=true` în lipsa unei probe efective de publicare și utilizare cloud.
- Dacă accesul ChatGPT lipsește, livrează skillul validat și raportează clar că instalarea în workspace și setările administrative nu au fost confirmate.
- Înregistrează distinct: simulare locală, test de rutare, alegere efectivă a modelului, apel real al conectorului, alocare/consum observate și economii măsurate.
