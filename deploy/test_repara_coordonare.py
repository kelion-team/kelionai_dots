import importlib.util, json, os, subprocess, sys, tempfile, unittest
from pathlib import Path
AICI = Path(__file__).parent
SCRIPT, MD = AICI / "repara_coordonare.py", AICI / "cerinte" / "coordonare-21-10.md"
COADA = '''import os, time, uuid
COADA = os.environ["T_COADA"]
ANUNTURI = []
def scrie(f, x):
    open(f, "w").write(repr(x))
def noutate(titlu, detalii, push=True, cheie=None):
    ANUNTURI.append(titlu)
def adauga(proiect, sarcina, sursa="", cerere=None):
    return {"id": "NOU1", "proiect": proiect, "sarcina": sarcina}
def _normal(t):
    return " ".join(str(t).lower().split())
def porneste(s, text):
    d = s["d"]
    lucrari = os.path.join(d, ".kelion", "lucrari")
    os.makedirs(lucrari, exist_ok=True)
    lid = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]
    return lid, text
def oprita(s, ultima, ora):
    if ultima:
        noutate("t", "d",
                push=False, cheie=f"coada:{s['id']}:rezultat-initial:{ultima['id']}")
        return True
def neverificata(s, v, ora):
    if v:
        if v:
            if v:
                s["motiv_blocare"] = f"NEVERIFICATA: lucrarea e terminata, dar validarea independenta nu a dat VERIFICAT ({v['text'][:150]})"
    return s
'''
VERIF = '''deja = {"picat|X|vechi": 1, "picat|Y|d": 2}
v = [{"ok": True, "ce": "X", "detaliu": ""}, {"ok": False, "ce": "Y", "detaliu": "d"}]
for x in v:
    if x["ok"] or x["ce"] == "toate legaturile interne verificate":
        continue
'''


class Teste(unittest.TestCase):
    def sursa(self):
        s = Path(tempfile.mkdtemp()); (s / "cerinte").mkdir()
        (s / "coada-lucru.py").write_text(COADA); (s / "verifica-site.py").write_text(VERIF)
        (s / "cerinte" / "registru-zi.json").write_text(json.dumps({"descriere": "x", "cerinte": [{"id": "R1"}, {"id": "K1", "vechi": 1}]}))
        (s / "cerinte" / "reguli.json").write_text(json.dumps({"versiune": 3, "fisiere_obligatorii": ["roluri.md"], "informative": [], "tipuri": {}, "reguli": []}))
        return s

    def ruleaza(self, s):
        d = Path(tempfile.mkdtemp())
        r = subprocess.run([sys.executable, "-B", str(SCRIPT), str(s), str(d), str(MD)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return d

    def test_patch_registru_si_comportament(self):
        d = self.ruleaza(self.sursa())
        reg = json.loads((d / "cerinte" / "registru-zi.json").read_text())["cerinte"]
        ids = [x["id"] for x in reg]
        self.assertEqual(len(ids), len(set(ids))); self.assertEqual(len(reg), 2 + 26)
        self.assertNotIn("vechi", reg[1])
        for i in ("K1", "K10", "P1", "P7", "I1", "I4", "M1", "M6"):
            self.assertIn(i, ids)
        self.assertTrue(all(x["actiune"].startswith("CHATGPT:") for x in reg if x["id"][0] in "KPIM"))
        man = json.loads((d / "cerinte" / "reguli.json").read_text())
        self.assertIn("coordonare-21-10.md", man["fisiere_obligatorii"]); self.assertIn("coordonare-21-10.md", man["informative"])
        self.assertTrue((d / "cerinte" / "coordonare-21-10.md").read_text().startswith("# Cerințe obligatorii"))
        # re-rulare pe rezultat: nimic dublat
        d2 = self.ruleaza(d)
        self.assertEqual((d2 / "coada-lucru.py").read_text(), (d / "coada-lucru.py").read_text())
        self.assertEqual(len(json.loads((d2 / "cerinte" / "registru-zi.json").read_text())["cerinte"]), 28)
        # comportament: proiect murdar preluat; blocata -> redistribuita; neverificata -> redistribuita; cheia defectului disparut stearsa
        sys.path.insert(0, str(AICI)); os.environ["T_COADA"] = tempfile.mkdtemp()
        ns = {"__name__": "c"}; exec((d / "coada-lucru.py").read_text(), ns)
        p = tempfile.mkdtemp(); g = lambda *a: subprocess.run(["git", "-C", p, *a], check=True, capture_output=True)
        g("init", "-q"); Path(p, "a").write_text("1"); g("add", "-A"); g("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "b")
        Path(p, "ramas.txt").write_text("x")
        s = {"id": "S1", "d": p, "istoric": []}
        _, text = ns["porneste"](s, "SARCINA")
        self.assertTrue(text.startswith("NOTA PRELUARE")); self.assertTrue(text.endswith("SARCINA"))
        s = {"id": "S1", "proiect": "p", "sarcina": "fa", "istoric": [], "motiv_blocare": "Activare new-only: reluarea automata este oprita; dirty project"}
        self.assertTrue(ns["oprita"](s, {"id": "L1"}, "ora")); self.assertEqual(s["inlocuita_de"], "NOU1")
        s2 = ns["neverificata"]({"id": "S2", "proiect": "p", "sarcina": "fa", "istoric": []}, {"text": "fara test.sh"}, "ora")
        self.assertEqual(s2["redistribuita_in"], "NOU1")
        nv = {}; exec((d / "verifica-site.py").read_text(), nv)
        self.assertEqual(nv["deja"], {"picat|Y|d": 2})

    def test_ancora_lipsa_opreste_fara_scriere(self):
        s = self.sursa(); (s / "coada-lucru.py").write_text("x = 1\n")
        d = Path(tempfile.mkdtemp())
        r = subprocess.run([sys.executable, "-B", str(SCRIPT), str(s), str(d), str(MD)], capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0); self.assertIn("OPRIT", r.stdout + r.stderr); self.assertFalse((d / "coada-lucru.py").exists())


if __name__ == "__main__":
    unittest.main()
