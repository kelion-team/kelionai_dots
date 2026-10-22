"""Laptopul AE nu se mai folosește (Adrian, 22.10.2026 05:31): Kelion trebuie să știe, iar verificatorul nu mai cere rapoarte de pe el.

  python3 repara_laptop_retras.py SURSA DESTINATIE MD     (SURSA = /opt/kelion-brain)
- verifica-site.py: «aparat laptop raporteaza ChatGPT» nu se mai verifică (era singurul defect permanent al verificatorului);
- cerinte/laptop-retras.md (informativ în manifestul regulilor) + cerința AE1 în registru: Kelion le primește la fiecare apel.
"""
import json
import os
import py_compile
import shutil
import sys

MD = "laptop-retras.md"
MARCAJ = "(22.10) laptop retras"
VECHI = '        for a in d["aparate"]:\n            nota(f"aparat {a[\'tip\']} raporteaza ChatGPT", '
NOU = ('        for a in d["aparate"]:\n'
       '            if a.get("tip") == "laptop":   # (22.10) laptop retras: Adrian, «AE nu se mai foloseste; doar serverul»\n'
       '                continue\n'
       '            nota(f"aparat {a[\'tip\']} raporteaza ChatGPT", ')
AE1 = {"id": "AE1", "de_la": "Adrian", "prima": "22.10 05:31 (chat)", "mod": "regula fixa", "cine": "Kelion (ChatGPT)",
       "cerinta": "Laptopul AE nu se mai foloseste: totul ruleaza pe serverul Contabo; fara unelte pe laptop (laptop, afiseaza unde=laptop, video OBS)",
       "verifica": {"tip": "manual", "dovada": "regula in cerinte/laptop-retras.md"},
       "actiune": "CHATGPT: nu folosi laptopul AE; lucreaza doar pe server; locatia si pozele vin de la telefon"}

if __name__ == "__main__":
    sursa, dest, md = sys.argv[1], sys.argv[2], sys.argv[3]
    os.makedirs(os.path.join(dest, "cerinte"), exist_ok=True)
    v = open(os.path.join(sursa, "verifica-site.py"), encoding="utf-8").read()
    if MARCAJ not in v:
        if v.count(VECHI) != 1:
            raise SystemExit(f"OPRIT: verifica-site.py: verificarea laptopului găsită de {v.count(VECHI)} ori. Nu s-a scris nimic.")
        v = v.replace(VECHI, NOU)
    reg = json.load(open(os.path.join(sursa, "cerinte", "registru-zi.json"), encoding="utf-8"))
    reg["cerinte"] = [x for x in reg["cerinte"] if x["id"] != "AE1"] + [AE1]
    man = json.load(open(os.path.join(sursa, "cerinte", "reguli.json"), encoding="utf-8"))
    man.setdefault("informative", [])
    if MD not in man["informative"]:
        man["informative"].append(MD)
    open(os.path.join(dest, "verifica-site.py"), "w", encoding="utf-8").write(v)
    py_compile.compile(os.path.join(dest, "verifica-site.py"), doraise=True)
    for nume, d in (("registru-zi.json", reg), ("reguli.json", man)):
        with open(os.path.join(dest, "cerinte", nume), "w", encoding="utf-8") as h:
            json.dump(d, h, ensure_ascii=False, indent=1)
    shutil.copyfile(md, os.path.join(dest, "cerinte", MD))
    print(f"OK: verificatorul nu mai cere laptopul; AE1 în registru ({len(reg['cerinte'])} cerințe); {MD} informativ.")
