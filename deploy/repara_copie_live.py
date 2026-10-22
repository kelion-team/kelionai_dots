"""Coada pune copia live (doar de citit, fără secrete și date personale) în fiecare lucrare (22.10.2026). Vezi copie_live.py.

  python3 repara_copie_live.py SURSA DESTINATIE     (SURSA = /opt/kelion-brain)
Înlocuirea trebuie să se potrivească exact o dată; altfel «OPRIT» și nu se scrie nimic. Re-rulabil (marcaj).
"""
import os
import py_compile
import sys

MARCAJ = "(22.10) copia live"
ANCORA = ('        s.setdefault("istoric", []).append(f"{time.strftime(\'%Y-%m-%d %H:%M\')} preluare fisiere necomise esuata: '
          '{type(e).__name__}: {str(e)[:160]}")\n'
          '    lid = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]\n')
NOU = ('        s.setdefault("istoric", []).append(f"{time.strftime(\'%Y-%m-%d %H:%M\')} preluare fisiere necomise esuata: '
       '{type(e).__name__}: {str(e)[:160]}")\n'
       '    try:   # (22.10) copia live: codul live DOAR DE CITIT in .kelion/live/ (fara secrete, fara date personale)\n'
       '        import copie_live as CL\n'
       '        text = CL.sincronizeaza(d) + "\\n\\n" + text\n'
       '    except Exception as e:\n'
       '        s.setdefault("istoric", []).append(f"{time.strftime(\'%Y-%m-%d %H:%M\')} copia live esuata: {type(e).__name__}: {str(e)[:160]}")\n'
       '    lid = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]\n')

if __name__ == "__main__":
    sursa, dest = sys.argv[1], sys.argv[2]
    os.makedirs(dest, exist_ok=True)
    t = open(os.path.join(sursa, "coada-lucru.py"), encoding="utf-8").read()
    if MARCAJ in t:
        print("DEJA APLICAT: coada-lucru.py pune deja copia live.")
    else:
        if t.count(ANCORA) != 1:
            raise SystemExit(f"OPRIT: coada-lucru.py: ancora (preluarea din #87) găsită de {t.count(ANCORA)} ori. Nu s-a scris nimic.")
        t = t.replace(ANCORA, NOU)
    open(os.path.join(dest, "coada-lucru.py"), "w", encoding="utf-8").write(t)
    py_compile.compile(os.path.join(dest, "coada-lucru.py"), doraise=True)
    print("OK: coada-lucru.py (copia live in fiecare lucrare), compilare reușită.")
