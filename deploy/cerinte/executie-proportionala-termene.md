# Execuție proporțională și termene măsurate

Regulă permanentă cerută de Adrian la 22 octombrie 2026. Se aplică lucrărilor software și comunicării progresului. Se păstrează aprobările, CI-ul, testele de regresie roșu→verde, recenzia, poarta manuală pentru live și verificările de securitate.

## Pașii unei lucrări

1. Reutilizează dovezile actuale: aprobarea exactă, sursa și versiunea/commitul, rezultatele testelor, starea PR-ului și receiptul. Separă faptele probate de presupuneri. Nu repeta o citire sau o probă reușită fără o schimbare relevantă ori o incertitudine explicită.
2. Fă numai verificarea preliminară necesară pasului următor: identitatea țintei, versiunea așteptată, limitele autorizării și backupul/revenirea când urmează o modificare live. Grupează verificările independente; păstrează ordinea operațiilor dependente.
3. Execută pasul autorizat și concret. Nu înlocui execuția posibilă cu încă un raport care recomandă aceeași verificare. La contract incomplet, implementează numai partea independentă și confirmată; nu inventa schema, cheia, endpointul sau drepturile.
4. La o eroare nouă, diagnostichează punctual cauza. Verifică întâi rezultatul unei operații cu rezultat incert. După refuz nu schimba ruta ca ocolire; reîncearcă numai cu dovezi noi relevante și autorizare aplicabilă.
5. Rulează testele relevante și toate verificările obligatorii. Pentru o reparație demonstrează regresia pe codul anterior și trecerea după corecție. Nu repeta teste neschimbate după succes decât dacă există modificări, eșecuri ori incertitudini noi. Nu reduce CI-ul sau controalele de securitate pentru a economisi pași.
6. Raportează artefactul și starea reală: fișiere, commit/SHA, PR, CI, recenzie, rezultat de instalare și proba funcțională, după caz. Distinge pregătit, salvat în repository, integrat, instalat și verificat live. Nici commitul, nici exit 0, nici pornirea procesului nu dovedesc singure finalizarea.
7. Grupează intervențiile indispensabile ale utilizatorului într-un singur pas pregătit și verificat, cu ținte și efecte exacte. Nu cere din nou aprobarea deja acordată. Nu transforma aprobarea unui fișier sau a unei lucrări în acces general.

## Termene și progres

- Când accepți un termen, citește ceasul și înregistrează pentru cerere: startul măsurat, deadline-ul cu fus orar, obiectivul livrabil și mecanismul timerului.
- Setează timerul/alerta printr-un mecanism disponibil și autorizat; verifică confirmarea setării. Nu pretinde că există un timer dacă ai notat doar o oră. Dacă mecanismul nu poate respecta intervalul sau sesiunea nu poate livra alerta, spune limita înainte să promiți termenul.
- Programează verificarea progresului suficient înainte de deadline pentru a putea comunica un blocaj. Dacă apare un blocaj, raportează-l înainte de expirare, cu ce s-a executat, dovada și dependența exactă rămasă.
- Nu inventa minute, procente, ore de start, progres ori estimări. Nu muta deadline-ul în tăcere. Dacă termenul a fost depășit, spune explicit și păstrează evidența inițială.
- Un timer nu autorizează execuția, deployul, un retry sau extinderea drepturilor. Nu promite continuare autonomă în afara mecanismelor efectiv active.

## Persistență și activare

Acest fișier este o regulă versionată în repository și este referit de AGENTS.md. Publicarea lui nu dovedește încărcarea în Brain live. Activarea pe server și integrarea cu schedulerul/jurnalul real se raportează separat, numai după aplicare autorizată și readback. Regula nu instalează un scheduler și nu activează drepturi.
