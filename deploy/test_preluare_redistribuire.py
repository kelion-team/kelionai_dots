import importlib.util, os, subprocess, sys, tempfile, unittest
from pathlib import Path
spec = importlib.util.spec_from_file_location("preluare_redistribuire", Path(__file__).with_name("preluare_redistribuire.py"))
PR = importlib.util.module_from_spec(spec); spec.loader.exec_module(PR)


def repo():
    d = tempfile.mkdtemp()
    g = lambda *a: subprocess.run(["git", "-C", d, *a], check=True, capture_output=True)
    g("init", "-q"); Path(d, "a.txt").write_text("1"); Path(d, ".gitignore").write_text(".kelion/\n")
    g("add", "-A"); g("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "baza")
    return d


class Preluare(unittest.TestCase):
    def test_necomise_salvate_kelion_si_credentiale_neatinse(self):
        d = repo()
        Path(d, "a.txt").write_text("2"); Path(d, "diag").mkdir(); Path(d, "diag", "test.sh").write_text("x")
        Path(d, ".kelion").mkdir(); Path(d, ".kelion", "l.json").write_text("{}"); Path(d, ".env").write_text("K=1")
        nota, sens = PR.preia_necomise(d, "S1")
        self.assertIn("2 fisiere necomise", nota); self.assertIn("ATENTIE", nota); self.assertEqual(sens, [".env"])
        self.assertEqual(PR.necomise(d), [".env"])   # restul e in commit, .kelion ignorat, .env neatins
        log = subprocess.run(["git", "-C", d, "log", "-1", "--format=%s"], capture_output=True, text=True).stdout
        self.assertIn("preluate 2 fișiere necomise înainte de sarcina S1", log)
        self.assertEqual(Path(d, ".env").read_text(), "K=1")

    def test_curat_si_fara_git(self):
        self.assertEqual(PR.preia_necomise(repo(), "S"), ("", []))
        self.assertEqual(PR.preia_necomise(tempfile.mkdtemp(), "S"), ("", []))


class Redistribuire(unittest.TestCase):
    def setUp(self):
        self.noi, self.anunturi, self.salvate = [], [], []

    def adauga(self, proiect, text, sursa):
        n = {"id": f"N{len(self.noi) + 1}", "proiect": proiect, "sarcina": text, "stare": "asteapta"}
        self.noi.append(n); return dict(n)

    def noutate(self, titlu, detalii, push=True, cheie=None):
        self.anunturi.append((titlu, push, cheie))

    def r(self, s, motiv):
        return PR.redistribuie(s, motiv, self.adauga, self.noutate, self.salvate.append, "ora")

    def test_lant_pana_la_escaladare(self):
        s = {"id": "S1", "proiect": "p", "sarcina": "fa X", "istoric": ["a", "b"], "rol_efectiv": "SOLUTII"}
        self.assertEqual(self.r(s, "dirty project; preserve preexisting changes"), "N1")
        n = self.salvate[-1]
        self.assertEqual((n["generatie"], n["radacina"], n["sarcina_initiala"]), (1, "S1", "fa X"))
        self.assertIn("MOTIVUL BLOCARII: dirty project", n["sarcina"]); self.assertTrue(n["sarcina"].endswith("SARCINA INITIALA:\nfa X"))
        self.assertEqual(s["inlocuita_de"], "N1"); self.assertIsNone(self.r(s, "x"))   # o singura data
        for g in (2, 3):
            n = dict(self.salvate[-1], istoric=[]); self.assertEqual(self.r(n, "tot blocat"), f"N{g}")
        ultima = dict(self.salvate[-1], istoric=[])
        self.assertEqual(ultima["generatie"], 3)
        self.assertIsNone(self.r(ultima, "tot blocat")); self.assertTrue(ultima["escaladata"])
        self.assertTrue(self.anunturi[-1][1]); self.assertIn("S1", self.anunturi[-1][0]); self.assertNotIn("inlocuita_de", ultima)

    def test_conectare_nefacuta_se_escaladeaza_direct(self):
        s = {"id": "S2", "proiect": "p", "sarcina": "y"}
        self.assertIsNone(self.r(s, "CONECTARE NEFACUTA: login")); self.assertEqual(self.noi, []); self.assertTrue(s["escaladata"])

    def test_cheie_defect_ignora_cifrele(self):
        a = {"proiect": "k", "sarcina": "Verificarea automata a site-ului Kelion a gasit o problema: Locatia (acum 3743 min)."}
        b = {"proiect": "k", "sarcina": "Verificarea automata a site-ului Kelion a gasit o problema: Locatia (acum 12 min)."}
        self.assertEqual(PR.cheie_defect(a), PR.cheie_defect(b))


class Repunere(unittest.TestCase):
    def test_o_sarcina_pe_defect_meta_inchisa_restul_inlocuite(self):
        import json, shutil, time
        d = Path(tempfile.mkdtemp()); shutil.copy(Path(__file__).with_name("preluare_redistribuire.py"), d)
        coada = d / "q"; coada.mkdir(); acum = time.time()
        def sarcina(i, text, motiv, creat=acum - 600, **k):
            x = {"id": i, "proiect": "kelion-remediere", "sarcina": text, "stare": "blocata", "motiv_blocare": motiv, "creat": creat, "istoric": []}
            x.update(k); (coada / f"{i}.json").write_text(json.dumps(x))
        P = "Verificarea automata a site-ului Kelion a gasit o problema: "
        sarcina("A1", P + "Locatia (acum 3743 min).", "Activare new-only: reluarea automata este oprita; dirty project")
        sarcina("A2", P + "Locatia (acum 3753 min).", "Activare new-only: reluarea automata este oprita; dirty project", creat=acum - 300)
        sarcina("B1", P + "nicio lucrare blocata (A1, A2).", "Activare new-only: reluarea automata este oprita; dirty project")
        sarcina("C1", "altceva", "CONECTARE NEFACUTA: x", asteapta_aprobare="x")
        sarcina("D1", P + "Vechi (1).", "Activare new-only: x", creat=acum - 3 * 86400)
        (d / "coada-lucru.py").write_text(f'''import json, os, glob
COADA = {str(coada)!r}
def toate():
    return [json.load(open(f)) for f in sorted(glob.glob(os.path.join(COADA, "*.json")))]
def scrie(f, x):
    json.dump(x, open(f, "w"))
def _redistribuie(s, motiv, ora):
    s["inlocuita_de"] = "NOU-" + s["id"]; return s["inlocuita_de"]
''')
        r = subprocess.run([sys.executable, "-B", str(Path(__file__).with_name("repune_blocate.py")), str(d / "coada-lucru.py")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        st = {x["id"]: x for x in (json.load(open(f)) for f in coada.glob("*.json"))}
        self.assertEqual(st["A1"]["inlocuita_de"], "NOU-A2"); self.assertEqual(st["A2"]["inlocuita_de"], "NOU-A2")
        self.assertEqual(st["B1"]["inlocuita_de"], "curatenie-dirty-20261022")
        self.assertNotIn("inlocuita_de", st["C1"]); self.assertNotIn("inlocuita_de", st["D1"])
        self.assertIn("repuse în lucru: 1", r.stdout)


if __name__ == "__main__":
    unittest.main()
