"""Coada care preia, analizează și redistribuie până la rezolvare + cerințele de coordonare din 21.10 (22.10.2026).

  python3 repara_coordonare.py SURSA DESTINATIE CERINTA_MD     (SURSA = /opt/kelion-brain)

Scrie în DESTINATIE: coada-lucru.py, verifica-site.py, cerinte/registru-zi.json, cerinte/reguli.json, cerinte/coordonare-21-10.md.
Fiecare înlocuire trebuie să se potrivească exact o dată; altfel «OPRIT» și nu se scrie nimic. Re-rulabil: ce are deja marcajul rămâne.

- coada-lucru.py: (1) înainte de o lucrare, fișierele necomise din proiect se salvează într-un commit (altfel lucrare.py refuză:
  «dirty project», cauza celor 57 de sarcini blocate din 21.10 15:16); (2) o sarcină blocată (execuție oprită sau NEVERIFICATA) se
  redistribuie ca sarcină nouă cu motivul blocării, de cel mult 3 ori, apoi se escaladează către Adrian cu motivul exact.
- verifica-site.py: când un defect dispare, cheia lui se șterge, ca o reapariție să fie preluată din nou (altfel era o singură dată, pentru totdeauna).
- registru + reguli: cele 10 puncte, 7 probe și completările A/B din 21.10 intră în registrul pe care Kelion îl primește la fiecare apel;
  fișierul de cerințe devine obligatoriu (dacă lipsește, operațiunile protejate se blochează, ca la celelalte reguli obligatorii).
"""
import json
import os
import py_compile
import shutil
import sys

MD = "coordonare-21-10.md"
MARCAJ_COADA = "(22.10) fisiere necomise"
MARCAJ_VERIF = "(22.10) defect disparut"

COADA = [
    ("_redistribuie lângă _normal",
     'def _normal(t):\n    return " ".join(str(t).lower().split())\n',
     'def _normal(t):\n    return " ".join(str(t).lower().split())\n\n\n'
     'def _redistribuie(s, motiv, ora):\n'
     '    """(22.10) O sarcina blocata nu ramane moarta: sarcina noua (prima ei executie) cu motivul blocarii, max 3 ori, apoi escaladare."""\n'
     '    try:\n'
     '        import preluare_redistribuire as PR\n'
     '        return PR.redistribuie(s, motiv, adauga, noutate, lambda n: scrie(os.path.join(COADA, n["id"] + ".json"), n), ora)\n'
     '    except Exception as e:\n'
     '        s.setdefault("istoric", []).append(f"{ora} redistribuire esuata: {type(e).__name__}: {str(e)[:160]}")\n'
     '        return None\n'),
    ("preluarea fișierelor necomise în porneste",
     '    lucrari = os.path.join(d, ".kelion", "lucrari")\n    os.makedirs(lucrari, exist_ok=True)\n'
     '    lid = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]\n',
     '    lucrari = os.path.join(d, ".kelion", "lucrari")\n    os.makedirs(lucrari, exist_ok=True)\n'
     '    try:   # (22.10) fisiere necomise ramase in proiect: salvate intr-un commit, altfel lucrare.py refuza («dirty project»)\n'
     '        import preluare_redistribuire as PR\n'
     '        nota, _ = PR.preia_necomise(d, s["id"])\n'
     '        if nota:\n'
     '            text = nota + "\\n\\n" + text\n'
     '            s.setdefault("istoric", []).append(f"{time.strftime(\'%Y-%m-%d %H:%M\')} {nota[:300]}")\n'
     '    except Exception as e:\n'
     '        s.setdefault("istoric", []).append(f"{time.strftime(\'%Y-%m-%d %H:%M\')} preluare fisiere necomise esuata: {type(e).__name__}: {str(e)[:160]}")\n'
     '    lid = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]\n'),
    ("redistribuire după execuția oprită",   # doar execuția OPRITĂ; «Executie confirmata fizic…» (reușită, nevalidată) NU se reface
     '                f"Sarcina {s[\'id\']}, proiect {s[\'proiect\']}: {s[\'motiv_blocare\']}",\n'
     '                push=False, cheie=f"coada:{s[\'id\']}:rezultat-initial:{ultima[\'id\']}")\n        return True\n',
     '                f"Sarcina {s[\'id\']}, proiect {s[\'proiect\']}: {s[\'motiv_blocare\']}",\n'
     '                push=False, cheie=f"coada:{s[\'id\']}:rezultat-initial:{ultima[\'id\']}")\n'
     '        _redistribuie(s, s["motiv_blocare"], ora)   # (22.10) blocata -> sarcina noua cu motivul, pana la rezolvare sau escaladare\n'
     '        return True\n'),
    ("redistribuire după NEVERIFICATA",
     '                s["motiv_blocare"] = f"NEVERIFICATA: lucrarea e terminata, dar validarea independenta nu a dat VERIFICAT ({v[\'text\'][:150]})"\n',
     '                s["motiv_blocare"] = f"NEVERIFICATA: lucrarea e terminata, dar validarea independenta nu a dat VERIFICAT ({v[\'text\'][:150]})"\n'
     '                _redistribuie(s, s["motiv_blocare"], ora)   # (22.10) neverificata -> redistribuita: validarea se completeaza\n'),
]
VERIF = [
    ("cheia defectului dispărut se șterge",
     'for x in v:\n    if x["ok"] or x["ce"] == "toate legaturile interne verificate":\n        continue\n',
     'for x in v:\n'
     '    if x["ok"]:   # (22.10) defect disparut: cheia se sterge, ca o reaparitie sa fie preluata din nou (nu o data pentru totdeauna)\n'
     '        for k in [k for k in deja if k.startswith("picat|" + x["ce"] + "|")]:\n'
     '            deja.pop(k, None)\n'
     '    if x["ok"] or x["ce"] == "toate legaturile interne verificate":\n        continue\n'),
]


def _c(id_, cerinta, prima, actiune, mod="regula de lucru", dovada="neprobat; ramane deschisa pana la proba reala"):
    return {"id": id_, "de_la": "Adrian", "prima": prima, "cerinta": cerinta, "mod": mod, "cine": "Kelion (ChatGPT) + coada",
            "verifica": {"tip": "manual", "dovada": dovada}, "actiune": actiune}


R, AB, PAR = "21.10 20:42 (recapitulare dupa apel)", "21.10 (completarea A, retransmisa de la Claude)", "21.10 20:48 (completarea B)"
CH = "CHATGPT: "
NOI = [
    _c("K1", "Circuit direct voce-executie-rezultat: cerinta vocala -> starea reala -> lucrare autorizata -> rezultat verificat -> spus in aceeasi conversatie; un ID comun intre voce, punte, executor si jurnale", R,
       CH + "la fiecare cerere vocala parcurgi tot circuitul si spui ID-ul cererii din jurnal; proba = P1"),
    _c("K2", "Coordonare persistenta: cerintele, aprobarile, planul si dovezile raman intre apeluri; lucrarile continua dupa apel; o cerere retransmisa nu produce executii sau restarturi duplicate", R,
       CH + "tii aprobarile si planul in jurnal, nu in memoria conversatiei; proba = P3 si P4"),
    _c("K3", "Feedback automat cu stari explicite (primita, in lucru, blocata, terminata); progresul si rezultatul revin singure in conversatie; lipsa raspunsului, timeoutul si erorile se spun; niciun succes doar pentru ca mesajul a fost livrat", R,
       CH + "la fiecare cerere spui starea reala din jurnal si coada, nu o presupui"),
    _c("K4", "Acces direct: puntile si conectorii existenti inventariati, reutilizati si verificati la pornire", R,
       CH + "la inceputul fiecarei conversatii catalog_unelte si o verificare reala a accesului; spui ce merge si ce nu"),
    _c("K5", "Componente: coordonare, stare si aprobari persistente, coada cu reluare, conectori cu raspunsuri corelate, teste de comportament; ce exista vs ce lipseste, fara instalari redundante; modelul efectiv de rationament, contextul si limitele lui verificate", R,
       CH + "raporteaza ce exista si ce lipseste, cu dovada din server; nu instala ce exista deja"),
    _c("K6", "Limite clare: pentru fiecare functie, ce controleaza serverul si ce cere platforma vocala; un serviciu instalat nu e automat o unealta a modelului", R,
       CH + "cand propui o functie, spui unde e limita (server sau platforma vocala)"),
    _c("K7", "Protejarea apelurilor si a datelor: starea reala a apelurilor verificata inainte de orice restart; datele, drepturile si autoritatea lui Adrian separate de ale invitatilor", R,
       CH + "inainte de orice restart verifici apel_in_curs pe server; nu amesteci datele invitatilor cu ale lui Adrian"),
    _c("K8", "Orice numar WhatsApp primeste raspuns; numerele necunoscute pe ruta izolata de invitati (la 21.10 codul inca respingea necunoscutii; activarea NU e confirmata); restartul pregatit si testat inainte, coordonat cu apelul activ", R,
       CH + "activeaza si testeaza ruta izolata pentru necunoscuti, apoi proba P5"),
    _c("K9", "Reparatiile A-D aprobate (recuperarea apelului, canalul de mesaje, pornirea audio idempotenta, dovezi); A corectata; noua recuperare si E (asteptarea unui loc la pornire) tinute separat de aprobarile vechi si de ce e efectiv aplicat", R,
       CH + "tii separat ce e aprobat, ce e propus (A nou, E) si ce e aplicat, cu dovada pentru fiecare"),
    _c("K10", "Experienta vocala: Kelion se opreste cand utilizatorul incepe sa vorbeasca; actualizarile asteapta sfarsitul interventiei; fara intrebari repetate despre cerinte aprobate; fara «se lucreaza» fara actiune reala", R,
       CH + "nu spui ca lucrezi daca nu exista o lucrare pornita in coada cu ID"),
    _c("P1", "Proba: cerinta vocala -> operatie read-only pe server -> rezultat verificat in aceeasi conversatie, fara interventie manuala intre pasi", R,
       CH + "fa proba la urmatorul apel vocal si scrie dovada (ID cerere, ore, rezultat)", mod="proba"),
    _c("P2", "Proba: o modificare reversibila autorizata, executata si verificata", R, CH + "alege o modificare reversibila aprobata, executa, verifica, raporteaza", mod="proba"),
    _c("P3", "Proba: reluarea aceleiasi lucrari dupa intrerupere, cu aprobarile pastrate", R, CH + "intrerupe controlat o lucrare de proba si arata reluarea cu aceleasi aprobari", mod="proba"),
    _c("P4", "Proba: teste pentru conexiune cazuta, executor fara raspuns si retransmiterea aceleiasi cereri", R, CH + "ruleaza cele trei teste si arata ca nu apar executii duble", mod="proba"),
    _c("P5", "Proba: apel real de la un numar necunoscut, pe ruta izolata", R, CH + "dupa K8, cere-i lui Adrian o singura data sa sune de pe un numar necunoscut si raporteaza ce s-a intamplat", mod="proba"),
    _c("P6", "Proba: apeluri paralele WhatsApp/aplicatie + mesaj de canal in timpul apelului; capacitatea raportata doar dupa masurare (1.000 de apeluri NU e verificat)", R,
       CH + "intai doua apeluri izolate (M1-M5), apoi masurare; nu declara capacitate nemasurata", mod="proba"),
    _c("P7", "Proba pentru fiecare reparatie: backup, diferente de cod, teste trecute, servicii active si jurnalul cerut", R, CH + "la fiecare reparatie raportezi toate cinci, cu cai si ore", mod="proba"),
    _c("I1", "Companionul: robot sus, kelionDots mai mic sub el, Microfon in stanga si Camera in dreapta dedesubt", AB, CH + "verifica pe pagina live si raporteaza cu captura (1280 si 390 px)"),
    _c("I2", "Camera: video catre server/modelul de vedere (camera virtuala verificata sau cadre periodice cu costul spus inainte); proba: obiect aratat si identificat", AB, CH + "stabileste varianta, spune costul, apoi proba cu un obiect"),
    _c("I3", "Spatiul de lucru: browser live pe server in zona principala, profil separat de apeluri si canal; Word, Excel, PDF si site-uri; robot mic cu trei butoane, revenire la oprire, fara scroll la 1280/390 px; proba: scriere vizibila in Word si Excel", AB,
       CH + "proba: scriere vizibila in Word si Excel, cu captura"),
    _c("I4", "Pentru fiecare din I1-I3: backup, teste, proba reala si raport", AB, CH + "fara raportul complet, I1-I3 raman deschise"),
    _c("M1", "Apeluri paralele: un singur numar WhatsApp si aceeasi identitate Kelion, dar sesiune independenta pentru fiecare apel", PAR, CH + "arata doua apeluri simultane cu sesiuni separate"),
    _c("M2", "Fiecare sesiune de apel: call ID, audio, conversatie, memorie de lucru si sarcini separate; drepturi potrivite apelantului, fara amestec de date sau instructiuni", PAR, CH + "dovada: doua sesiuni cu ID-uri si date separate"),
    _c("M3", "Browser si instrumente alocate separat per apel; acces coordonat la resursele comune", PAR, CH + "arata alocarea separata in timpul a doua apeluri"),
    _c("M4", "Manager pentru alocarea, pornirea si eliberarea resurselor per apel", PAR, CH + "arata ca resursele se elibereaza la sfarsitul apelului"),
    _c("M5", "Limitele WhatsApp, ale serviciului vocal si ale serverului verificate separat; intai doua apeluri izolate, apoi capacitate masurata (nicio dovada pentru 1.000)", PAR, CH + "masoara, nu estima"),
    _c("M6", "Fiecare cerinta ramane deschisa pana la proba reala si intoarcerea rezultatului verificabil", PAR, CH + "nu inchizi nicio cerinta fara proba"),
]


def inlocuieste(text, lista, nume_fisier):
    for nume, vechi, nou in lista:
        if text.count(vechi) != 1:
            raise SystemExit(f"OPRIT: {nume_fisier}: «{nume}» găsit de {text.count(vechi)} ori. Nu s-a scris nimic.")
        text = text.replace(vechi, nou)
    return text


if __name__ == "__main__":
    sursa, dest, md = sys.argv[1], sys.argv[2], sys.argv[3]
    os.makedirs(os.path.join(dest, "cerinte"), exist_ok=True)
    coada = open(os.path.join(sursa, "coada-lucru.py"), encoding="utf-8").read()
    if MARCAJ_COADA not in coada:
        coada = inlocuieste(coada, COADA, "coada-lucru.py")
    verif = open(os.path.join(sursa, "verifica-site.py"), encoding="utf-8").read()
    if MARCAJ_VERIF not in verif:
        verif = inlocuieste(verif, VERIF, "verifica-site.py")
    reg = json.load(open(os.path.join(sursa, "cerinte", "registru-zi.json"), encoding="utf-8"))
    ids = {x["id"]: i for i, x in enumerate(reg["cerinte"])}
    for c in NOI:
        if c["id"] in ids:
            reg["cerinte"][ids[c["id"]]] = c
        else:
            reg["cerinte"].append(c)
    man = json.load(open(os.path.join(sursa, "cerinte", "reguli.json"), encoding="utf-8"))
    for camp in ("fisiere_obligatorii", "informative"):
        man.setdefault(camp, [])
        if MD not in man[camp]:
            man[camp].append(MD)
    for nume, text in (("coada-lucru.py", coada), ("verifica-site.py", verif)):
        open(os.path.join(dest, nume), "w", encoding="utf-8").write(text)
        py_compile.compile(os.path.join(dest, nume), doraise=True)
    for nume, d in (("registru-zi.json", reg), ("reguli.json", man)):
        with open(os.path.join(dest, "cerinte", nume), "w", encoding="utf-8") as h:
            json.dump(d, h, ensure_ascii=False, indent=1)
    shutil.copyfile(md, os.path.join(dest, "cerinte", MD))
    print(f"OK: coada-lucru.py + verifica-site.py compilate; registru {len(reg['cerinte'])} cerinte (+{len(NOI)} K/P/I/M); {MD} obligatoriu.")
