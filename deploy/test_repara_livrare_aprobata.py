import json, os, subprocess, sys, tempfile, unittest
from pathlib import Path
AICI = Path(__file__).parent

COADA = '''import json, os, time
APROBARI = os.environ["T_APROBARI"]
MAX_BLOCARI_REGULI = int(os.environ.get("KELION_COADA_BLOCARI_REGULI", "3"))
ANUNTURI = []
def noutate(t, d, push=True, cheie=None):
    ANUNTURI.append((t, cheie))
def _aprobate():
    try:
        with open(APROBARI, encoding="utf-8") as h:
            return set((json.load(h).get("skilluri") or {}).keys())
    except (OSError, ValueError, AttributeError):
        return set()
def etapa_live(s, lucrare, ora):
    lid, acum, L = lucrare["id"], time.time(), s.get("live") or {}
    aprobat_acum = L.get("lucrare") == lid and L.get("stare") == "asteapta-aprobare" and L.get("aprobari_cerute") and \\
        {x.get("sha256") for x in L["aprobari_cerute"]} <= _aprobate()
    if L.get("lucrare") != lid or (L.get("stare") == "amanat" and acum >= L.get("urmatoarea", 0)) or aprobat_acum:
        s["live"] = {"lucrare": lid, "stare": "cerut"}
        return None
    return "altceva"
'''


class Teste(unittest.TestCase):
    def setUp(self):
        self.src = Path(tempfile.mkdtemp()); (self.src / "coada-lucru.py").write_text(COADA)
        self.dst = Path(tempfile.mkdtemp())
        r = subprocess.run([sys.executable, "-B", str(AICI / "repara_livrare_aprobata.py"), str(self.src), str(self.dst)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.apr = Path(tempfile.mkdtemp()) / "aprobari.json"; self.apr.write_text(json.dumps({"skilluri": {"abc": {}}}))
        os.environ["T_APROBARI"] = str(self.apr); os.environ.pop("KELION_LIVRARE_AUTOMATA", None)

    def ns(self):
        ns = {"__name__": "c"}; exec((self.dst / "coada-lucru.py").read_text(), ns); return ns

    def test_fara_aprobare_nu_porneste_livrarea_si_anunta_o_data(self):
        ns = self.ns(); s = {"id": "S1", "proiect": "p", "istoric": []}
        self.assertIsNone(ns["etapa_live"](s, {"id": "20261022-080000-abcd"}, "ora"))
        self.assertEqual(s["live"]["stare"], "asteapta-aprobare")
        ns["etapa_live"](s, {"id": "20261022-080000-abcd"}, "ora")
        self.assertEqual(len(ns["ANUNTURI"]), 1); self.assertIn("kelion-aproba-livrare", s["istoric"][0])
        self.assertIn("abc", ns["_aprobate"]())   # aprobarile vechi (skilluri) raman

    def test_dupa_aprobare_porneste(self):
        ns = self.ns(); s = {"id": "S1", "proiect": "p", "istoric": []}
        ns["etapa_live"](s, {"id": "20261022-080000-abcd"}, "ora")
        self.apr.write_text(json.dumps({"skilluri": {}, "lucrari": {"20261022-080000-abcd": {}}}))
        ns["etapa_live"](s, {"id": "20261022-080000-abcd"}, "ora")
        self.assertEqual(s["live"]["stare"], "cerut")

    def test_comutator_livrare_automata(self):
        os.environ["KELION_LIVRARE_AUTOMATA"] = "1"
        try:
            ns = self.ns(); s = {"id": "S1", "proiect": "p", "istoric": []}
            ns["etapa_live"](s, {"id": "20261022-080000-abcd"}, "ora")
            self.assertEqual(s["live"]["stare"], "cerut")
        finally:
            os.environ.pop("KELION_LIVRARE_AUTOMATA")

    def test_rerulare_si_ancora_lipsa(self):
        r = subprocess.run([sys.executable, "-B", str(AICI / "repara_livrare_aprobata.py"), str(self.dst), str(tempfile.mkdtemp())], capture_output=True, text=True)
        self.assertIn("DEJA APLICAT", r.stdout)
        s = Path(tempfile.mkdtemp()); (s / "coada-lucru.py").write_text("x = 1\n")
        r = subprocess.run([sys.executable, "-B", str(AICI / "repara_livrare_aprobata.py"), str(s), str(tempfile.mkdtemp())], capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0); self.assertIn("OPRIT", r.stdout + r.stderr)


class Aproba(unittest.TestCase):
    @unittest.skipUnless(os.geteuid() == 0, "doar ca root")
    def test_aproba_pastreaza_skilluri(self):
        apr = Path(tempfile.mkdtemp()) / "aprobari.json"; apr.write_text(json.dumps({"skilluri": {"x": 1}}))
        env = dict(os.environ, KELION_APROBARI=str(apr))
        r = subprocess.run([sys.executable, str(AICI / "kelion-aproba-livrare"), "20261022-080000-abcd"], capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stdout)
        d = json.loads(apr.read_text()); self.assertEqual(d["skilluri"], {"x": 1}); self.assertIn("20261022-080000-abcd", d["lucrari"])
        r = subprocess.run([sys.executable, str(AICI / "kelion-aproba-livrare"), "../rau"], capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main()
