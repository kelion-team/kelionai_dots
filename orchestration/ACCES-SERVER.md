# Acces la serverul kelion-nou — procedură pentru Kelion și DOTS

Actualizat: 14 octombrie 2026. Acest fișier NU conține și nu trebuie să conțină parole, chei API, chei SSH sau tokenuri.

## Unde rulează aplicația

- Server: VPS Contabo `kelion-nou`, IP public 144.91.64.250, utilizator implicit `root`.
- Site: https://kelionai.app — cod în `/opt/kelion-app/ingress-v2` (pagina, `app.js`, `server.mjs`, rutele `/api/config`, `/api/session`, `/api/tasks`).
- Codul site-ului NU este în GitHub. Primul pas la orice intervenție: copierea lui în acest repository (fără `.env` și fără secrete).

## Stare verificată live (14 oct 2026, 06:15)

| Rută | Răspuns |
|---|---|
| `/api/config` | `ready: false`, `missing: [GOOGLE_CLIENT_ID, KELION_ALLOWED_EMAILS]`, `worker: not_verified` |
| `/api/session` | 503 „Authentication configuration missing” |
| `/api/tasks` | 503 |

Concluzie: login dezactivat, cereri blocate, niciun worker legat între site și agenții din acest repository.

## Căi de acces permise

1. **Calculatorul lui Adrian legat la sesiunea agentului** (Claude Desktop „Link to this computer”, sau Desktop Commander pentru ChatGPT). Agentul folosește accesul SSH deja configurat pe calculator, fără să vadă parole.
2. **Consolă web deschisă de Adrian**: Adrian se loghează în panoul Contabo și pe server, apoi agentul lucrează doar în sesiunea deschisă, cât timp este deschisă.
3. **GitHub**: după ce codul site-ului este copiat în acest repository, reparațiile se fac prin PR; deploy-ul se face de pe server.

Panoul vechi my.contabo.com nu are consolă în browser (doar date pentru un client VNC extern). Verificați dacă new.contabo.com oferă consolă web pentru acest VPS.

## Interdicții

- Niciun agent nu se autentifică cu parolele sau cheile utilizatorului copiate din Drive, chat sau alte documente.
- Niciun agent nu își creează singur acces permanent (chei SSH, utilizatori noi, parole salvate, tuneluri) pe server.
- Secretele nu se salvează în chat, repository, Library sau Drive. Secretele aflate deja în clar în Drive trebuie schimbate și mutate într-un manager de parole.

## Ordinea de lucru după obținerea accesului

1. Copierea codului din `/opt/kelion-app/ingress-v2` în acest repository (fără secrete).
2. Diagnosticul testului `synthetic_secret_isolation_checks_failed` (`/proc/self/environ`) și remedierea fără dezactivarea testului.
3. Activarea candidatului `3ffe04334b78` doar după teste verzi; versiunea activă curentă este `562af2586079`.
4. Worker: legarea `/api/tasks` de `orchestration/bridge.py` / `native_dispatch.py`, cu selecție de model prin `kelion_brain.py` și buget verificat.
5. Login: client OAuth Google nou, creat de Adrian în Google Cloud Console; `GOOGLE_CLIENT_ID` și `KELION_ALLOWED_EMAILS` se pun în configurația serverului, nu în repository.
6. Probă finală ca utilizator real pe kelionai.app: login → cerere → execuție → răspuns afișat.
