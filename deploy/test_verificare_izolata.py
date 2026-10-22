import importlib.util, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path
AICI = Path(__file__).parent
spec = importlib.util.spec_from_file_location("verificare_izolata", AICI / "verificare_izolata.py")
VI = importlib.util.module_from_spec(spec); spec.loader.exec_module(VI)


def proiect(test="echo ok"):
    d = tempfile.mkdtemp()
    if test is not None:
        Path(d, "test.sh").write_text(test + "\n")
    Path(d, ".kelion").mkdir(); Path(d, ".kelion", "receipt.json").write_text("{}")
    return d


class Fals:
    def __init__(self, cod=0, out="ok", ex=None):
        self.cod, self.out, self.ex, self.argv = cod, out, ex, None

    def __call__(self, argv, **kw):
        self.argv = argv
        copie = argv[argv.index("--bind") + 1]
        self.copie_avea_kelion = os.path.exists(os.path.join(copie, ".kelion"))
        Path(copie, "scris-de-test.txt").write_text("x")   # testul scrie in copie, nu in proiect
        if self.ex:
            raise self.ex
        return subprocess.CompletedProcess(argv, self.cod, self.out, "")


class Teste(unittest.TestCase):
    def test_verificat_izolat_fara_retea_si_fara_server(self):
        d, f = proiect(), Fals()
        t = VI.verifica(d, "L1", rulare=f)
        self.assertTrue(t.startswith("VERIFICAT"), t)
        a = f.argv
        for x in ("--unshare-all", "--clearenv", "--die-with-parent", "--new-session"):
            self.assertIn(x, a)
        self.assertEqual(a[a.index("--bind") + 2], "/work"); self.assertEqual(a[-2:], ["/usr/bin/bash", "test.sh"])
        self.assertFalse(any(x.startswith(("/opt", "/var", "/home", "/srv")) for x in a), a)
        self.assertFalse(any("kelion" in x for x in a if x.startswith("/etc")))
        self.assertFalse(f.copie_avea_kelion); self.assertFalse(Path(d, "scris-de-test.txt").exists())

    def test_esuat_timeout_fara_teste(self):
        self.assertTrue(VI.verifica(proiect(), "L", rulare=Fals(cod=3, out="AssertionError")).startswith("ESUAT"))
        t = VI.verifica(proiect(), "L", rulare=Fals(ex=subprocess.TimeoutExpired("bwrap", 5)))
        self.assertTrue(t.startswith("ESUAT") and "cod 124" in t, t)
        t = VI.verifica(proiect(test=None), "L", rulare=Fals())
        self.assertTrue(t.startswith("PARTIAL") and "fara teste" in t, t)
        self.assertTrue(VI.verifica("/nu/exista", "L").startswith("INDISPONIBIL"))
        t = VI.verifica(proiect(), "L", rulare=Fals(ex=FileNotFoundError("bwrap")))
        self.assertTrue(t.startswith("INDISPONIBIL"), t)

    @unittest.skipUnless(shutil.which("bwrap"), "bwrap lipseste")
    def test_bwrap_real(self):
        d = proiect("ls /opt/kelion-brain 2>/dev/null && exit 9; getent hosts github.com && exit 8; echo izolat")
        t = VI.verifica(d, "L")
        self.assertTrue(t.startswith(("VERIFICAT", "INDISPONIBIL", "ESUAT")), t)


COADA = '''import os, time
PROIECTE = os.environ["T_PROIECTE"]
def nume_valid(p):
    return p
def verifica_receptie(s, ultima):
    if ultima.get("rau"):
        raise ValueError("receipt does not match execution")
    return {"commit": "c"}
def _normal(t):
    return " ".join(str(t).lower().split())
def pas(s, ultima):
    cale = []
    if ultima and ultima.get("stare") == "gata":
        # Initial admission never imports project tests into the parent and never deploys.
        cale.append("garda")
        return cale
    if ultima and ultima.get("stare") == "gata":
        cale.append("flux complet: " + valideaza(s["proiect"], ultima["id"]))
    return cale
def valideaza(proiect, lid):
    if os.environ.get("KELION_FARA_VALIDARE"):
        return "nevalidat (dezactivat in proba)"
    return "vechi: brain.verifica_lucrare"
'''


class Patch(unittest.TestCase):
    def test_garda_trece_la_fluxul_complet_si_valideaza_izolat(self):
        s = Path(tempfile.mkdtemp()); (s / "coada-lucru.py").write_text(COADA)
        d = Path(tempfile.mkdtemp())
        r = subprocess.run([sys.executable, "-B", str(AICI / "repara_verificare_izolata.py"), str(s), str(d)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r2 = subprocess.run([sys.executable, "-B", str(AICI / "repara_verificare_izolata.py"), str(d), str(tempfile.mkdtemp())], capture_output=True, text=True)
        self.assertIn("DEJA APLICAT", r2.stdout)
        p = Path(tempfile.mkdtemp()); (p / "pr").mkdir(); (p / "pr" / "test.sh").write_text("echo ok\n")
        os.environ["T_PROIECTE"] = str(p); sys.path.insert(0, str(AICI))
        ns = {"__name__": "c"}; exec((d / "coada-lucru.py").read_text(), ns)
        ok = ns["pas"]({"proiect": "pr", "istoric": []}, {"id": "L1", "stare": "gata"})
        self.assertEqual(len(ok), 1); self.assertTrue(ok[0].startswith("flux complet: "), ok)
        self.assertNotIn("vechi", ok[0])   # valideaza nu mai ruleaza testele in procesul parinte
        s2 = {"proiect": "pr", "istoric": []}
        self.assertEqual(ns["pas"](s2, {"id": "L2", "stare": "gata", "rau": 1}), ["garda"])
        self.assertIn("receptie neconfirmata", s2["istoric"][-1])

    def test_ancora_lipsa(self):
        s = Path(tempfile.mkdtemp()); (s / "coada-lucru.py").write_text("x = 1\n")
        r = subprocess.run([sys.executable, "-B", str(AICI / "repara_verificare_izolata.py"), str(s), str(tempfile.mkdtemp())], capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0); self.assertIn("OPRIT", r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
