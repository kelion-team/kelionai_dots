# Cerințe obligatorii: coordonare reală, integrare directă și verificare (Adrian, 21.10.2026)

Sursa: recapitularea de după apelul din 21.10, 20:42 (Londra), plus completările A (interfață, cameră, spațiu de lucru) și B (20:48, apeluri paralele). Mențiunile despre starea tehnică sunt cele de atunci. Fiecare punct rămâne DESCHIS până la proba reală și întoarcerea rezultatului verificabil. În registru: K1–K10, P1–P7, I1–I4, M1–M6.

## Cele 10 puncte

1. **Circuit direct voce–execuție–rezultat (K1).** Kelion trebuie să poată primi o cerință vocală, consulta starea reală, lansa o lucrare autorizată, verifica rezultatul și comunica rezultatul în aceeași conversație. Fiecare cerere are un ID comun între voce, punte, executor și jurnale.
2. **Coordonare persistentă (K2).** Cerințele, aprobările, planul și dovezile se păstrează între apeluri; lucrările continuă după închiderea apelului. Aceeași cerere retransmisă nu produce execuții sau restarturi duplicate.
3. **Feedback automat (K3).** Stări explicite: primită, în lucru, blocată, terminată. Progresul și rezultatul revin automat în conversație. Lipsa răspunsului, timeoutul și erorile se raportează explicit. Nu se declară succes numai pentru că mesajul a fost livrat.
4. **Acces direct (K4).** Inventarierea și reutilizarea punții/conectorilor existenți, cu verificarea accesului la pornire. Accesul direct prin Desktop Commander la serverul vmi3583512 și citirea codului /opt/kelion-pod/kelion_pod.py au funcționat; asta nu demonstrează încă integrarea completă între toate AI-urile.
5. **Componente software (K5).** Serviciu de coordonare, stocare persistentă a stării și aprobărilor, coadă persistentă cu reluare, conectori cu răspunsuri corelate și teste de comportament. Se stabilește ce există deja și ce lipsește, fără instalări redundante. Se verifică modelul efectiv de raționament, contextul și limitele sale; o bibliotecă nu garantează judecată mai bună.
6. **Limite clare (K6).** Pentru fiecare funcție se precizează ce controlează serverul și ce necesită suportul platformei vocale. Instalarea unui serviciu nu îl face automat accesibil modelului ca instrument.
7. **Protejarea apelurilor și a datelor (K7).** Starea reală a apelurilor se verifică înainte de restart. Datele, drepturile și autoritatea lui Adrian rămân separate de cele ale invitaților.
8. **Cerere permanentă (K8):** orice număr WhatsApp primește răspuns, numerele necunoscute fiind dirijate pe ruta izolată de invitați. La ultima citire directă (21.10), codul încă respingea necunoscuții neînregistrați; activarea schimbării NU este confirmată. Dacă necesită restart, se pregătește și testează înainte, apoi se coordonează încheierea apelului activ.
9. **Reparații existente (K9).** A–D au primit aprobare explicită: recuperarea apelului, canalul de mesaje, pornirea audio idempotentă și dovezi de funcționare. Propunerea A a fost ulterior corectată: nu mai este demonstrat că supraveghetorul a provocat închiderea apelului; noua recuperare propusă și punctul E (așteptarea unui loc în pornire) se păstrează distinct de aprobările anterioare și de ce este efectiv aplicat.
10. **Experiența vocală (K10).** Kelion se oprește când utilizatorul începe să vorbească; actualizările așteaptă terminarea intervenției. Fără întrebări repetate despre cerințe deja aprobate și fără afirmații că se lucrează dacă nu există acțiune reală.

## Probe de acceptare

1. **P1** Cerință vocală → operație read-only pe server → rezultat verificat în aceeași conversație, fără intervenție manuală între pași.
2. **P2** O modificare reversibilă autorizată, executată și verificată.
3. **P3** Reluarea aceleiași lucrări după întrerupere, cu aprobările păstrate.
4. **P4** Teste pentru conexiune căzută, executor fără răspuns și retransmiterea aceleiași cereri.
5. **P5** Apel real de la un număr necunoscut, pe ruta izolată.
6. **P6** Apeluri paralele WhatsApp/aplicație și mesaj de canal în timpul apelului; capacitatea simultană se raportează numai după măsurare. Cifra de 1.000 de apeluri NU este verificată.
7. **P7** Backup, diferențe de cod, teste trecute, servicii active și jurnalul cerut pentru fiecare reparație.

## A. Interfață, cameră și spațiu de lucru

- **I1** Companionul: robot sus, kelionDots mai mic sub el, Microfon în stânga și Camera în dreapta dedesubt.
- **I2** Camera: conectare video către server/modelul de vedere; verificarea suportului camerei virtuale sau, alternativ, cadre periodice cu cost comunicat înainte. Probă reală: obiect arătat și identificat.
- **I3** Spațiul de lucru: browser live pe server în zona principală, cu profil separat de apeluri și canal; Word, Excel, PDF și site-uri; robot mic cu trei butoane, revenire la oprire și fără scroll la 1280/390 px. Probă: scriere vizibilă în Word și Excel.
- **I4** Pentru fiecare: backup, teste, probă reală și raport.

## B. Apeluri paralele (completarea de la 20:48)

- **M1** Un singur număr WhatsApp și aceeași identitate Kelion, dar sesiune independentă pentru fiecare apel.
- **M2** Fiecare sesiune: call ID, audio, conversație, memorie de lucru și sarcini separate; drepturi potrivite apelantului, fără amestec de date sau instrucțiuni.
- **M3** Browser și instrumente alocate separat; acces coordonat la resursele comune.
- **M4** Manager pentru alocare, pornire și eliberarea resurselor.
- **M5** Verificare separată a limitelor WhatsApp, serviciului vocal și serverului; întâi două apeluri izolate, apoi capacitate măsurată. Nu există dovadă pentru 1.000 de apeluri.
- **M6** Fiecare cerință rămâne deschisă până la proba reală și întoarcerea rezultatului verificabil aici.

## Cum le ține Kelion

- Sunt în registrul `cerinte/registru-zi.json` și apar în fiecare răspuns `catalog_unelte` și în instrucțiunile fiecărei lucrări, până la proba reală.
- Nicio cerință nu se declară îndeplinită fără proba ei; „cod existent” nu e probă.
- Ce nu se poate face fără Adrian (un apel real, o aprobare) i se cere o singură dată, scurt, cu motivul exact.
