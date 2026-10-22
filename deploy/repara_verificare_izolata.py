"""S5 (22.10.2026): coada trece lucrările terminate prin verificarea IZOLATĂ și apoi prin livrarea automată (aprobată de Adrian 04:33).

  python3 repara_verificare_izolata.py SURSA DESTINATIE      (SURSA = /opt/kelion-brain)

- valideaza(): în loc să ruleze testele executantului în procesul părinte (brain.verifica_lucrare), le rulează izolat
  (verificare_izolata.verifica: copie, bwrap fără rețea și fără acces la server). Verdictul are același format.
- Garda «new-only» (oprea totul după receipt cu «verificarea independenta in sandbox lipseste»): dacă receiptul și commitul se confirmă,
  lucrarea merge pe fluxul complet existent: verificare (pasul «adevar» în jurnal) → poarta de reguli → livrare pe live prin
  kelion-livrare (backup, probă, rollback automat) → «rezolvata». ESUAT/NEVERIFICAT → redistribuire cu motivul (din #87).
  Dacă receiptul nu se confirmă, rămâne comportamentul vechi (blocată, cu motivul).
Fiecare înlocuire trebuie să se potrivească exact o dată; altfel «OPRIT» și nu se scrie nimic. Re-rulabil (marcaj).
"""
import os
import py_compile
import sys

MARCAJ = "(22.10) S5"
COADA = [
    ("_receptie_ok lângă _normal",
     'def _normal(t):\n    return " ".join(str(t).lower().split())\n',
     'def _normal(t):\n    return " ".join(str(t).lower().split())\n\n\n'
     'def _receptie_ok(s, ultima):\n'
     '    """(22.10) S5: receiptul si commitul lucrarii confirmate fizic -> True (lucrarea merge la verificarea izolata si livrare);\n'
     '    altfel False (ramane calea veche: blocata cu motivul)."""\n'
     '    try:\n'
     '        s["verificare_receptie"] = verifica_receptie(s, ultima)\n'
     '        s["raspuns"] = (ultima.get("raspuns") or "")[:4000]\n'
     '        s.pop("neverificata", None)\n'
     '        return True\n'
     '    except Exception as e:\n'
     '        s.setdefault("istoric", []).append(f"{time.strftime(\'%Y-%m-%d %H:%M\')} receptie neconfirmata: {type(e).__name__}: {str(e)[:160]}")\n'
     '        return False\n'),
    ("garda new-only → fluxul complet",
     '    if ultima and ultima.get("stare") == "gata":\n        # Initial admission never imports project tests into the parent and never deploys.\n',
     '    if ultima and ultima.get("stare") == "gata" and _receptie_ok(s, ultima):\n'
     '        pass   # (22.10) S5: receptie confirmata -> fluxul complet: verificare IZOLATA, poarta de reguli, livrare automata pe live\n'
     '    elif ultima and ultima.get("stare") == "gata":\n        # Initial admission never imports project tests into the parent and never deploys.\n'),
    ("valideaza izolat",
     '    if os.environ.get("KELION_FARA_VALIDARE"):\n        return "nevalidat (dezactivat in proba)"\n',
     '    if os.environ.get("KELION_FARA_VALIDARE"):\n        return "nevalidat (dezactivat in proba)"\n'
     '    try:   # (22.10) S5: testele executantului ruleaza IZOLAT (copie, bwrap, fara retea, fara acces la server), nu in procesul parinte\n'
     '        import verificare_izolata as VI\n'
     '        return VI.verifica(os.path.join(PROIECTE, nume_valid(proiect)), lid)\n'
     '    except Exception as e:\n'
     '        return f"INDISPONIBIL: verificarea izolata a esuat ({type(e).__name__}: {str(e)[:120]})"\n'),
]

if __name__ == "__main__":
    sursa, dest = sys.argv[1], sys.argv[2]
    os.makedirs(dest, exist_ok=True)
    t = open(os.path.join(sursa, "coada-lucru.py"), encoding="utf-8").read()
    if MARCAJ in t:
        print("DEJA APLICAT: coada-lucru.py are deja verificarea izolata.")
    else:
        for nume, vechi, nou in COADA:
            if t.count(vechi) != 1:
                raise SystemExit(f"OPRIT: coada-lucru.py: «{nume}» găsit de {t.count(vechi)} ori. Nu s-a scris nimic.")
            t = t.replace(vechi, nou)
    open(os.path.join(dest, "coada-lucru.py"), "w", encoding="utf-8").write(t)
    py_compile.compile(os.path.join(dest, "coada-lucru.py"), doraise=True)
    print("OK: coada-lucru.py (verificare izolata + flux complet), compilare reușită.")
