"""O singură dată (22.10.2026): sarcinile blocate din ultimele 48 h se repun în lucru, câte una pe defect.

Intră: execuția inițială oprită («Activare new-only: …», inclusiv «dirty project») și «NEVERIFICATA». Nu intră: ce așteaptă aprobarea
lui Adrian, ce e deja înlocuit sau escaladat.

Rulat ca brain cu timerul cozii oprit:  python3 repune_blocate.py /opt/kelion-brain/coada-lucru.py
Pentru fiecare defect distinct (proiect + text fără cifre/ore) cea mai nouă sarcină blocată se redistribuie (sarcină nouă, prima
execuție); celelalte sarcini ale aceluiași defect se marchează înlocuite de ea. «nicio lucrare blocata» e consecința blocărilor
înseși: se marchează înlocuită, nu se repune.
"""
import importlib.util
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(sys.argv[1])))
spec = importlib.util.spec_from_file_location("coada_lucru", sys.argv[1])
Q = importlib.util.module_from_spec(spec)
spec.loader.exec_module(Q)
import preluare_redistribuire as PR  # noqa: E402

ora = time.strftime("%Y-%m-%d %H:%M")
LIMITA = time.time() - 48 * 3600
blocate = [s for s in Q.toate() if s.get("stare") == "blocata" and not s.get("inlocuita_de") and not s.get("asteapta_aprobare")
           and not s.get("escaladata") and s.get("creat", 0) > LIMITA
           and (str(s.get("motiv_blocare", "")).startswith(("Activare new-only", "NEVERIFICATA"))
                or (str(s.get("motiv_blocare", "")).startswith(("Executie confirmata fizic", "Receptie neverificata"))
                    and s.get("proiect") in ("kelion-remediere", "kelion-tester-remediere")))]   # S5: executate dar neverificate (doar remedierea automata)
altele = [s for s in Q.toate() if s.get("stare") == "blocata" and not s.get("inlocuita_de") and s.get("creat", 0) > LIMITA
          and str(s.get("motiv_blocare", "")).startswith("Executie confirmata fizic") and s.get("proiect") not in ("kelion-remediere", "kelion-tester-remediere")]
grupe = {}
for s in sorted(blocate, key=lambda x: x.get("creat", 0)):
    grupe.setdefault(PR.cheie_defect(s), []).append(s)
noi, meta = [], 0
for (proiect, defect), lista in grupe.items():
    ultima = lista[-1]
    if defect.startswith("nicio lucrare blocata"):
        inloc, meta = "curatenie-dirty-20261022", meta + len(lista)
    else:
        inloc = Q._redistribuie(ultima, ultima.get("motiv_blocare"), ora)
        if not inloc:
            print(f"ATENȚIE: {proiect} «{defect[:60]}»: nu s-a putut redistribui ({ultima.get('istoric', ['-'])[-1][:160]})")
            Q.scrie(os.path.join(Q.COADA, ultima["id"] + ".json"), ultima)
            continue
        noi.append(f"{inloc} ← {proiect}: {defect[:70]} ({len(lista)} blocate)")
    for s in lista:
        if not s.get("inlocuita_de"):
            s["inlocuita_de"] = inloc
            s.setdefault("istoric", []).append(f"{ora} inlocuita de {inloc} (repunere dupa reparatia «dirty project» / redistribuire)")
        Q.scrie(os.path.join(Q.COADA, s["id"] + ".json"), s)
print(f"sarcini blocate repuse la analiză (48 h): {len(blocate)}; defecte distincte: {len(grupe)}; repuse în lucru: {len(noi)}; "
      f"«nicio lucrare blocata» închise ca urmare: {meta}")
for x in noi:
    print("  " + x)
if altele:   # sarcinile venite de la Kelion/ChatGPT: executate, neverificate; nu le relansez singur (decide Kelion sau Adrian)
    print(f"executate dar neverificate, din alte proiecte (nerepuse): {len(altele)}: " + ", ".join(f"{s['id']} ({s['proiect']})" for s in altele[:10]))
