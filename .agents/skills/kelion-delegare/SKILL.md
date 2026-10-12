---
name: kelion-delegare
description: "Folosește automat această procedură pentru orchestrarea, delegarea, verificarea, recuperarea rezultatelor și predarea sarcinilor agenților KelionAI între ChatGPT, Work și Codex. Se aplică oricărei solicitări despre KelionAI, DOTS, agent, subagent, rulare, handoff, coordonare sau continuitatea lucrului la kelion-team/kelionai_dots."
---

# KelionAI — delegare și continuitate, autodescoperire Codex

**Sursă canonică, persistentă:** `AGENTS.md` din rădăcina acestui repository și `orchestration/SOP-DELEGARE.md`. Citește și respectă ambele fișiere existente înainte să delegi o sarcină. Nu cere utilizatorului să lipească sau să încarce aceste fișiere la fiecare sesiune.

## Reguli de lucru

1. **Continuă lucrarea activă.** Consultați issue [#4](https://github.com/kelion-team/kelionai_dots/issues/4), registrul actual și rezultatele deja verificate. Nu reporni pași finalizați și nu înlocui unilateral lucrarea activă cu alte subiecte.
2. **Reutilizează agenții deja publicați.** Verifică ID-urile `agt_...`, publicarea, accesul și capabilitățile; `agtch_...` este identificator distinct pentru declanșarea prin API.
3. **Delegă numai real.** Un agent trebuie să primească efectiv sarcina prin canal autorizat; un plan, mesaj Slack, fișier local sau HTTP 202 nu dovedește rezultat.
4. **Recuperează și verifică.** Păstrează task_id, origine, dovadă dispatch, conversație/run, result_ref, integritate SHA256 și test independent; nu marca `verified` fără output real recitit.
5. **Zero cost nou.** Nu cumpăra credite, abonamente sau trialuri facturabile. Nu crea sau publica secrete; pentru Workspace Agents folosește doar canal/token oficial deja autorizat sau configurează-l prin fluxul oficial.
6. **Nu abandona la blocaje.** Investigă și execută pașii independenți; dacă e nevoie de aprobarea explicită sau autentificarea utilizatorului, spune exact ce lipsește și nu pretinde că a fost efectuat.
7. **Predă contextul între suprafețe.** Datele comune rămân în repository/issue; verifică efectiv accesul și readback-ul în ChatGPT, Work și Codex înainte de a declara integrarea completă.

## Persistență și limitări

Codex descoperă skillurile locale din `.agents/skills/` și regulile `AGENTS.md` când proiectul este deschis. Fișierele persistă prin Git și sunt disponibile automat în noile sesiuni Codex ale acestui repository; nu există garanție pentru sesiuni Codex deschise în alte repository-uri.

**ChatGPT/Work:** o copie în GitHub nu configurează singură Project instructions sau instalarea skillului personal în cont. Folosește skillul ChatGPT existent `dots-orchestrare-echipa-ro` când este disponibil și contextul proiectului ChatGPT/Work când este configurat; nu declara autoinstalare sau sincronizare între suprafețe fără probă.

SOP: `orchestration/SOP-DELEGARE.md`. Teste/implementare: `orchestration/tests/test_bridge.py` și `orchestration/bridge.py`.
