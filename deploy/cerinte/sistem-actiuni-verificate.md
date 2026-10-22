# Sistemul care transformă raționamentul în acțiuni verificate (Adrian, 22.10.2026)

Nu încă un chatbot: modelul dă raționamentul, iar componentele de mai jos îl aplică consecvent. Regula: întâi se identifică și se leagă ce există deja, apoi se construiește DOAR ce lipsește. Starea de mai jos e citită pe server pe 22.10.2026 (doar citire); în registru: S1–S6.

| # | Componentă | Ce există deja (fișier/funcție) | Ce lipsește |
|---|---|---|---|
| S1 | Inventar real: ce unelte, cod și conexiuni există și ce poate face fiecare | `catalog_unelte` (brain.py): index versionat al uneltelor, cu ce e NOU; starea la pornire (proiecte, GPS, poze, sănătatea serverului); lista cerințelor salvate | proba de funcționare a fiecărei unelte/conexiuni la pornire (lista nu dovedește că merge) |
| S2 | Planificare: descompune obiectivul, găsește lipsurile, compară soluțiile înainte să aleagă | `cerinte/mod-gandire.md`, `cerinte/procedura-nou.md`, `cerinte/roluri.md` + rolul ales automat (`roluri_delegare`, `CLASIFICA_ROL_CERERE`) | planul salvat pe cerere (pași, lipsuri, variante comparate, alegerea și motivul), folosit de executor și de verificator |
| S3 | Constructor de unelte: adaptoarele/scripturile lipsă create și testate izolat | `lucreaza_in_proiect` → coadă → `lucrare.py`: lucrare într-un proiect git separat (`/srv/kelion-proiecte/<proiect>`), commit + receipt; `kelion-pregateste-livrare` pentru livrare cu probă | testarea în mediu izolat (sandbox), oprită de activarea „new-only” din 21.10 |
| S4 | Execuție cu feedback: urmărește fiecare pas, schimbă abordarea la eșec, detectează buclele | `coada-lucru.py`: supraveghetor la 2 min, FARA_PROGRES, receipt, jurnalul pașilor; din 22.10: preluarea proiectului murdar și redistribuirea cu motivul blocării (max 3, apoi escaladare) | schimbarea abordării e doar cerută în instrucțiuni (motiv + „nu repeta”), nu impusă (alt rol sau alt model) |
| S5 | Verificare independentă: rezultatul comparat cu cerința, nu cu mesajul „succes” | validarea veche (`verificare`, test.sh obligatoriu, verdict VERIFICAT), poarta de livrare (`reguli_obligatorii.inainte_de_livrare`), `verifica-site` (registru + site la 10 min), `tester-ui` (pagini la 10 min) | pentru lucrări e OPRITĂ: în modul „new-only” orice lucrare terminată se oprește la „Executie confirmata fizic… verificarea independenta in sandbox lipseste” (16 lucrări în 5 zile); lipsește etapa de verificare în sandbox (test.sh pe copie izolată + comparația cu cerința), apoi livrarea cu aprobare |
| S6 | Memorie de lucru persistentă: plan, dovezi, soluții validate | `jurnal-cereri.sqlite3` (cereri, pași, stadii, versiuni de reguli), `work/coada/*.json` cu istoric, proiectele git + `JURNAL.md`, `brain_memorie` (memorie cu identitate), `noutati.jsonl`, `apeluri.jsonl` | planul persistent (S2) și o bibliotecă de soluții validate (problemă → soluție → commit → test) consultată la sarcinile noi |

## Ordinea de construit (doar ce lipsește)

1. **S5, etapa de verificare în sandbox** pentru lucrările terminate: deblochează lucrările oprite la „Executie confirmata fizic” și tot ce urmează. Livrarea pe live rămâne cu aprobare.
2. **S2 + S6**: planul salvat pe cerere și biblioteca de soluții validate.
3. **S1**: proba de funcționare a uneltelor și conexiunilor la pornire.
4. **S4**: la redistribuire, alt rol sau altă abordare impusă, nu doar cerută.

## Ce face Kelion acum cu ele

- Folosește ce există (tabelul de mai sus) și nu reconstruiește ce există deja.
- Nu declară nimic îndeplinit fără verificarea independentă (S5); „executat” nu înseamnă „rezolvat”.
- Raportează lipsurile de mai sus ca lipsuri, cu fișierul și dovada, nu ca funcții existente.
