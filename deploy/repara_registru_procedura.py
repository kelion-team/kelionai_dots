"""R17 / R20 / R33 / A12 (22.10.2026).

- R17, R20, R33: verificatorul căuta codul în fișierele de dinainte de refactorizare (lucrare.py e acum doar rularea
  izolată). Funcțiile există, în alte fișiere (citit pe server 22.10, doar citire):
    R17 declanșarea automată: transfer_automat.py `def declanseaza_kelion`, coada-lucru.py `def porneste_supraveghetor`;
    R20 rolul de rezervă: brain.py «Plasa de siguranta» + CLASIFICA_ROL_CERERE (apel haiku separat);
    R33 livrarea prin flux: coada-lucru.py cere kelion-pregateste-livrare și test.sh OBLIGATORIU la validare.
  Registrul (cerinte/registru-zi.json) se actualizează să verifice acolo. Aceasta e dovadă de cod, nu probă live.
- A4: nav.js arată deja pe fiecare buton dovada de fișier și de funcționare («Fișier verificat; funcționare
  neconfirmată» / «Ultimul test funcțional a trecut», liniile 465-490); registrul căuta alt text («funcționare dovedită»).
- A12: procedura-nou.md nu mai era citită nicăieri. coada-lucru.py o adaugă acum la instrucțiunile fiecărei lucrări.

  python3 repara_registru_procedura.py SURSA DESTINATIE   (SURSA = /opt/kelion-brain)
"""
import json
import os
import py_compile
import sys

VERIFICA = {
    "R17": {"tip": "fisier", "cale": ["/opt/kelion-brain/transfer_automat.py", "/opt/kelion-brain/coada-lucru.py"],
            "contine": ["def declanseaza_kelion", "def porneste_supraveghetor"]},
    "R20": {"tip": "fisier", "cale": ["/opt/kelion-brain/brain.py"], "contine": ["Plasa de siguranta", "CLASIFICA_ROL_CERERE"]},
    "R33": {"tip": "fisier", "cale": ["/opt/kelion-brain/coada-lucru.py"], "contine": ["kelion-pregateste-livrare", "OBLIGATORIU"]},
    "A4": {"tip": "fisier", "cale": ["/var/www/kelion/app/nav.js"],
           "contine": ["Ultimul test funcțional a trecut", "Fișier verificat; funcționare neconfirmată"]},
    "A12": {"tip": "fisier", "cale": ["/opt/kelion-brain/cerinte/procedura-nou.md", "/opt/kelion-brain/coada-lucru.py"],
            "contine": ["procedura-nou.md"]},
}
COADA = [("procedura-nou.md în fiecare lucrare",
          "        efectiv, prefix = RD.delegare(rol, subrol, BAZA)\n        return efectiv + ales, prefix\n",
          "        efectiv, prefix = RD.delegare(rol, subrol, BAZA)\n"
          "        try:   # A12 (22.10): procedura pentru orice componentă nouă intră în instrucțiunile fiecărei lucrări\n"
          "            cale = os.path.join(os.path.dirname(os.path.abspath(__file__)), \"cerinte\", \"procedura-nou.md\")\n"
          "            prefix = (prefix + \"\\n\\n\" if prefix else \"\") + open(cale, encoding=\"utf-8\").read()\n"
          "        except OSError:\n"
          "            pass\n"
          "        return efectiv + ales, prefix\n")]
MARCAJ = "A12 (22.10)"


if __name__ == "__main__":
    sursa, dest = sys.argv[1], sys.argv[2]
    os.makedirs(os.path.join(dest, "cerinte"), exist_ok=True)
    coada = open(os.path.join(sursa, "coada-lucru.py"), encoding="utf-8").read()
    if MARCAJ not in coada:
        for nume, vechi, nou in COADA:
            if coada.count(vechi) != 1:
                raise SystemExit(f"OPRIT: coada-lucru.py: «{nume}» găsit de {coada.count(vechi)} ori. Nu s-a scris nimic.")
            coada = coada.replace(vechi, nou)
    if "import os" not in coada:
        raise SystemExit("OPRIT: coada-lucru.py nu importă os. Nu s-a scris nimic.")
    reg = json.load(open(os.path.join(sursa, "cerinte", "registru-zi.json"), encoding="utf-8"))
    ids = {x["id"]: x for x in reg["cerinte"]}
    for i, v in VERIFICA.items():
        if i not in ids:
            raise SystemExit(f"OPRIT: {i} lipsește din registru. Nu s-a scris nimic.")
        ids[i]["verifica"] = v
    open(os.path.join(dest, "coada-lucru.py"), "w", encoding="utf-8").write(coada)
    py_compile.compile(os.path.join(dest, "coada-lucru.py"), doraise=True)
    with open(os.path.join(dest, "cerinte", "registru-zi.json"), "w", encoding="utf-8") as h:
        json.dump(reg, h, ensure_ascii=False, indent=1)
    print("OK: coada-lucru.py (A12) + registru (R17, R20, R33, A4, A12), compilare reușită.")
