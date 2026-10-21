# Apeluri WhatsApp în paralel (pod_locuri)

Fiecare apel are **locul lui**: Chrome propriu (profil + port CDP), pagina dot proprie și **sunetul propriu** în PulseAudio:

| Loc | Apelantul intră în | Microfonul Chrome | Kelion iese din | CDP | Profil |
|---|---|---|---|---|---|
| 1 (ca azi) | `wa_in` | `mic_wa` | `chrome_out` | 9277 | `/var/lib/kelion-pod/chrome` |
| N ≥ 2 | `wa_in_N` | `mic_wa_N` | `chrome_out_N` | 9377+N | `/var/lib/kelion-pod/locN` |

Chrome-ul locului N pornește cu `PULSE_SINK=chrome_out_N` și `PULSE_SOURCE=mic_wa_N`: vocile nu se amestecă între apeluri. Profilul invitaților (`chrome2`, 9278) nu e atins.

## Scalare automată
- Maximul de apeluri simultane se **calculează din RAM, nuclee și încărcare**, recitit la fiecare ciclu (60 s) și înainte de fiecare alocare: `python3 -m pod_locuri capacitate`.
- Pe serverul de azi (12 GB, 6 nuclee) ies ~10 locuri. Când serverul e mărit, maximul crește singur, fără restart.
- Configurarea `/etc/kelion-pod/locuri.json` (opțională: `ram_pe_loc_mb`, `cpu_pe_loc`, rezerve, `locuri_pregatite`) se recitește singură la schimbare; un fișier stricat e ignorat.
- 2 locuri stau mereu pregătite (pagina dot gata), ca orice apel să intre din prima. Locurile libere în plus se opresc; cele ocupate nu se ating niciodată.
- La maxim: apelul primește „ocupat” și Adrian primește o alertă (cel mult o dată la 10 minute): „mărește planul Contabo”.

## Logarea unui loc nou
Un profil nou nu e logat în ChatGPT. Managerul îl detectează (pagina e pe `/auth/login`), repornește Chrome-ul acelui loc **fără automatizare**, pe pagina de logare, și îl anunță pe Adrian să intre pe `kelionai.app/app/pod-ecran` și să se logheze el. Nu se copiază sesiuni sau cookie-uri. După logare, locul devine singur `pregatit`.

## Integrare în podul existent (kelion_pod.py) — de făcut de Kelion, cu backup
1. La `connect`: `loc = manager.aloca(call_id)`; dacă `None` → mesaj vocal „ocupat”; altfel apelul folosește **numai** `loc.wa_in`, `loc.chrome_out.monitor` și CDP `loc.port_cdp`.
2. La `terminate`: `manager.elibereaza(call_id)`.
3. Un fir separat rulează `manager.sincronizeaza()` la 60 s.
4. Livrările de canal (Codex/Brain) și chatul text **nu folosesc pagini de apel**: au pagina lor separată, cu prioritate egală.
5. Probe: un apel cu voce în ambele sensuri; un mesaj de canal în timpul apelului nu îl întrerupe; două apeluri simultane, fiecare cu sunetul lui.

## Teste
`python3 -B -m unittest discover -s pod_locuri/tests -v` — capacitate din RAM/CPU, creștere la server mărit, recitirea configurării, izolarea sunetului/portului/profilului pe loc, alocare fără „ocupat” până la maxim, alertă la capacitate, mod login fără automatizare.
