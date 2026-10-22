"""(22.10.2026) Livrarea pe live DOAR cu aprobarea explicită a lui Adrian, pentru fiecare lucrare (decizia lui Adrian, 06:33).

  python3 repara_livrare_aprobata.py SURSA DESTINATIE      (SURSA = /opt/kelion-brain)

Până acum, după VERIFICAT, coada pornea singură kelion-livrare. Acum, înainte de pornire, coada cere aprobarea:
  - sarcina rămâne DESCHISĂ, «asteapta-aprobare», cu ce anume se aprobă (lucrarea), și se anunță o singură dată;
  - Adrian aprobă ca root: kelion-aproba-livrare <lucrare> (sau îi spune lui Kelion, care are root prin Desktop Commander);
  - după aprobare, livrarea pornește singură, pe drumul existent (backup, probă, rollback).
KELION_LIVRARE_AUTOMATA=1 în mediul cozii readuce comportamentul vechi. Fiecare înlocuire se potrivește exact o dată; altfel «OPRIT».
"""
import os
import py_compile
import sys

MARCAJ = "(22.10) livrare doar cu aprobare"
COADA = [
    ("comutatorul",
     'MAX_BLOCARI_REGULI = int(os.environ.get("KELION_COADA_BLOCARI_REGULI", "3"))',
     'MAX_BLOCARI_REGULI = int(os.environ.get("KELION_COADA_BLOCARI_REGULI", "3"))\n'
     '# (22.10) livrare doar cu aprobare: Adrian aproba fiecare livrare pe live (kelion-aproba-livrare <lucrare>); =1 readuce livrarea automata\n'
     'LIVRARE_AUTOMATA = os.environ.get("KELION_LIVRARE_AUTOMATA") == "1"'),
    ("aprobarile includ lucrarile",
     '            return set((json.load(h).get("skilluri") or {}).keys())\n',
     '            a = json.load(h)\n'
     '            return set((a.get("skilluri") or {}).keys()) | {"lucrare:" + k for k in (a.get("lucrari") or {})}\n'),
    ("poarta inainte de pornirea livrarii",
     '    if L.get("lucrare") != lid or (L.get("stare") == "amanat" and acum >= L.get("urmatoarea", 0)) or aprobat_acum:\n',
     '    if not LIVRARE_AUTOMATA and ("lucrare:" + lid) not in _aprobate():\n'
     '        # (22.10) livrare doar cu aprobare: nimic nu pleaca pe live fara aprobarea lui Adrian pentru ACEASTA lucrare\n'
     '        if not (L.get("lucrare") == lid and L.get("stare") == "asteapta-aprobare"):\n'
     '            cerute = [{"dest": f"livrarea pe live a lucrarii {lid}", "sha256": "lucrare:" + lid}]\n'
     '            s["live"] = {"lucrare": lid, "stare": "asteapta-aprobare", "aprobari_cerute": cerute, "cerut": acum}\n'
     '            s["istoric"].append(f"{ora} ASTEAPTA APROBAREA LUI ADRIAN pentru livrarea pe live a lucrarii {lid}: nimic schimbat pe live; aprobare: kelion-aproba-livrare {lid}")\n'
     '            noutate(f"Coada: sarcina {s[\'id\']} ASTEAPTA APROBAREA LUI ADRIAN pentru livrare",\n'
     '                    f"Proiect {s[\'proiect\']}, lucrarea {lid} a trecut verificarea (rosu->verde). Livrarea pe live porneste doar dupa "\n'
     '                    f"aprobarea lui Adrian: ca root, kelion-aproba-livrare {lid}. Nimic nu s-a schimbat pe live; sarcina NU e rezolvata.",\n'
     '                    cheie=f"coada:{s[\'id\']}:aprobare-livrare:{lid}")\n'
     '        return None\n'
     '    if L.get("lucrare") != lid or (L.get("stare") == "amanat" and acum >= L.get("urmatoarea", 0)) or aprobat_acum:\n'),
]


MARCAJ2 = "(22.10) livrare doar cu aprobare v2"
# v2 (recenzia Codex la #93): o așteptare veche (skill-uri) pentru aceeași lucrare primește și aprobarea lucrării, cu anunț;
# cu KELION_LIVRARE_AUTOMATA=1 o lucrare care aștepta doar aprobarea lucrării pornește singură.
COADA2 = [
    ("poarta v2",
     '        if not (L.get("lucrare") == lid and L.get("stare") == "asteapta-aprobare"):\n'
     '            cerute = [{"dest": f"livrarea pe live a lucrarii {lid}", "sha256": "lucrare:" + lid}]\n'
     '            s["live"] = {"lucrare": lid, "stare": "asteapta-aprobare", "aprobari_cerute": cerute, "cerut": acum}\n',
     '        # (22.10) livrare doar cu aprobare v2: o asteptare veche (skill-uri) a aceleiasi lucrari primeste si aprobarea lucrarii\n'
     '        jeton = "lucrare:" + lid\n'
     '        vechi = list(L.get("aprobari_cerute") or []) if (L.get("lucrare") == lid and L.get("stare") == "asteapta-aprobare") else []\n'
     '        if not any(x.get("sha256") == jeton for x in vechi):\n'
     '            cerute = vechi + [{"dest": f"livrarea pe live a lucrarii {lid}", "sha256": jeton}]\n'
     '            s["live"] = dict(L if L.get("lucrare") == lid else {}, lucrare=lid, stare="asteapta-aprobare", aprobari_cerute=cerute, cerut=acum)\n'),
    ("reluare cu livrarea automata",
     '    if L.get("lucrare") != lid or (L.get("stare") == "amanat" and acum >= L.get("urmatoarea", 0)) or aprobat_acum:\n',
     '    reluare_automata = LIVRARE_AUTOMATA and L.get("lucrare") == lid and L.get("stare") == "asteapta-aprobare" and \\\n'
     '        {x.get("sha256") for x in L.get("aprobari_cerute") or []} - _aprobate() <= {"lucrare:" + lid}\n'
     '    if L.get("lucrare") != lid or (L.get("stare") == "amanat" and acum >= L.get("urmatoarea", 0)) or aprobat_acum or reluare_automata:\n'),
]


def aplica(t):
    schimbat = False
    if MARCAJ not in t:
        for nume, vechi, nou in COADA:
            if t.count(vechi) != 1:
                raise SystemExit(f"OPRIT: coada-lucru.py: «{nume}» găsit de {t.count(vechi)} ori. Nu s-a scris nimic.")
            t = t.replace(vechi, nou)
        schimbat = True
    if MARCAJ2 not in t:
        for nume, vechi, nou in COADA2:
            if t.count(vechi) != 1:
                raise SystemExit(f"OPRIT: coada-lucru.py: «{nume}» găsit de {t.count(vechi)} ori. Nu s-a scris nimic.")
            t = t.replace(vechi, nou)
        schimbat = True
    return t, schimbat


if __name__ == "__main__":
    sursa, dest = sys.argv[1], sys.argv[2]
    os.makedirs(dest, exist_ok=True)
    t, schimbat = aplica(open(os.path.join(sursa, "coada-lucru.py"), encoding="utf-8").read())
    print("aplicat" if schimbat else "DEJA APLICAT: coada-lucru.py cere deja aprobarea livrarii.")
    open(os.path.join(dest, "coada-lucru.py"), "w", encoding="utf-8").write(t)
    py_compile.compile(os.path.join(dest, "coada-lucru.py"), doraise=True)
