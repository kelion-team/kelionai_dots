"""R5 / R32 / S8 (22.10.2026): bucla de remediere automată.

Dovadă (doar citire, /opt/kelion-brain/work/coada): din 73 de sarcini blocate în 24 h, 57 sunt puse automat de
verifica-site.py (proiect kelion-remediere) și 14 de tester-ui.py (kelion-tester-remediere). Cauza: cheia de
deduplicare conține detaliul defectului cu cifre și ore («acum 3693 min», «Tester 02:55», «50 din 55»), deci fiecare
rulare (la 10 minute) vede un defect „nou” și pune încă o sarcină pentru același lucru.

Reparația: cheia/semnătura se calculează fără cifre și ore; testerul nu mai pune aceeași sarcină în 24 h.

  python3 repara_bucle_remediere.py SURSA DESTINATIE   (SURSA = /opt/kelion-brain)
"""
import os
import py_compile
import sys

FARA_CIFRE = r'r"\d+([.,:]\d+)*"'
R = {
    "verifica-site.py": [
        ("cheie stabilă pentru defecte",
         '    cheie = "picat|" + x["ce"] + "|" + x["detaliu"][:80]\n',
         '    # cheie fără cifre/ore: altfel fiecare rulare (la 10 min) punea o sarcină nouă pentru același defect (R5, 22.10)\n'
         '    cheie = "picat|" + x["ce"] + "|" + re.sub(' + FARA_CIFRE + ', "#", x["detaliu"])[:80]\n'),
    ],
    "tester-ui.py": [
        ("testerul nu repetă aceeași sarcină",
         '    if defecte and os.environ.get("KELION_TESTER_REPARA", "1") == "1":\n',
         '    import hashlib, re\n'
         '    semn = hashlib.sha256(re.sub(' + FARA_CIFRE + ', "#", " | ".join(defecte)).encode()).hexdigest()[:16] if defecte else ""\n'
         '    stare_rep = OUT + ".reparatie"\n'
         '    try:\n'
         '        ultim = json.load(open(stare_rep, encoding="utf-8"))\n'
         '    except (OSError, ValueError):\n'
         '        ultim = {}\n'
         '    # aceleași defecte (fără cifre/ore) în ultimele 24 h: nu se mai pune o sarcină nouă (R5, 22.10: 14 blocate/zi)\n'
         '    repetat = bool(defecte) and ultim.get("semn") == semn and time.time() - ultim.get("t", 0) < 86400\n'
         '    if repetat:\n'
         '        rez["reparatie"] = f"{ultim.get(\'sarcina\')} (aceleasi defecte, deja in coada)"\n'
         '    if defecte and not repetat and os.environ.get("KELION_TESTER_REPARA", "1") == "1":\n'),
        ("testerul ține minte ultima sarcină",
         '            rez["reparatie"] = s["id"] + (" (exista deja, urmarita)" if s.get("_exista") else " (noua)")\n',
         '            rez["reparatie"] = s["id"] + (" (exista deja, urmarita)" if s.get("_exista") else " (noua)")\n'
         '            with open(stare_rep, "w", encoding="utf-8") as h:\n'
         '                json.dump({"semn": semn, "t": time.time(), "sarcina": s["id"]}, h)\n'),
    ],
}
MARCAJ = {"verifica-site.py": "cheie fără cifre/ore", "tester-ui.py": "stare_rep = OUT"}


# Dacă patch-ul de diagnostic al lui Kelion (scripts/legacy-tester-audit, PR #70) e aplicat întâi, condiția testerului
# devine «if reparabile and ...»: aceeași reparație se aplică și acolo.
VARIANTE = [('    if defecte and os.environ.get("KELION_TESTER_REPARA", "1") == "1":\n',
             '    if reparabile and os.environ.get("KELION_TESTER_REPARA", "1") == "1":\n')]


def aplica(text, inl, fisier):
    for nume, vechi, nou in inl:
        for a, b in VARIANTE:
            if vechi == a and text.count(a) == 0 and text.count(b) == 1:
                vechi, nou = b, nou.replace("if defecte and not repetat and", "if reparabile and not repetat and")
        n = text.count(vechi)
        if n != 1:
            raise SystemExit(f"OPRIT: {fisier}: «{nume}» găsit de {n} ori (trebuie exact 1). Nu s-a scris nimic.")
        text = text.replace(vechi, nou)
    return text


if __name__ == "__main__":
    sursa, dest = sys.argv[1], sys.argv[2]
    texte = {f: open(os.path.join(sursa, f), encoding="utf-8").read() for f in R}
    if all(MARCAJ[f] in t for f, t in texte.items()):
        raise SystemExit("DEJA APLICAT.")
    noi = {f: (t if MARCAJ[f] in t else aplica(t, R[f], f)) for f, t in texte.items()}
    os.makedirs(dest, exist_ok=True)
    for f, t in noi.items():
        cale = os.path.join(dest, f)
        open(cale, "w", encoding="utf-8").write(t)
        py_compile.compile(cale, doraise=True)
    print("OK: reparații aplicate, compilare reușită.")
