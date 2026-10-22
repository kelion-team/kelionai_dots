import importlib.util, json, os, shutil, subprocess, sys, tempfile, unittest
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
    """Ruleaza «testul» in procesul de test: verdictul vine din functia data (copia proiectului -> cod)."""
    def __init__(self, cod=0, out="ok", ex=None, judeca=None):
        self.cod, self.out, self.ex, self.judeca, self.argvs, self.copii, self.timeouts = cod, out, ex, judeca, [], [], []

    def __call__(self, argv, **kw):
        self.argvs.append(argv); self.timeouts.append(kw.get("timeout"))
        copie = argv[argv.index("--bind") + 1]
        self.copii.append(sorted(str(x.relative_to(copie)) for x in Path(copie).rglob("*")))
        Path(copie, "scris-de-test.txt").write_text("x")   # testul scrie in copie, nu in proiect
        if self.ex:
            raise self.ex
        r = self.judeca(Path(copie)) if self.judeca else self.cod
        cod, out = r if isinstance(r, tuple) else (r, self.out)
        return subprocess.CompletedProcess(argv, cod, out, "")


def git_proiect(cod_baza, cod_lucrare, test_in_lucrare=True):
    d = tempfile.mkdtemp(); g = lambda *a: subprocess.run(["git", "-C", d, "-c", "user.name=t", "-c", "user.email=t@t", *a], check=True, capture_output=True)
    g("init", "-q"); Path(d, "aduna.py").write_text(cod_baza)
    if not test_in_lucrare:
        Path(d, "test.sh").write_text("python3 -c 'import aduna; assert aduna.f(2,3)==5'\n")
    g("add", "-A"); g("commit", "-qm", "baza"); baza = subprocess.run(["git", "-C", d, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    Path(d, "aduna.py").write_text(cod_lucrare)
    if test_in_lucrare:
        Path(d, "test.sh").write_text("python3 -c 'import aduna; assert aduna.f(2,3)==5'\n")
    Path(d, ".env").write_text("SECRET=1")
    g("add", "aduna.py", "test.sh"); g("commit", "-qm", "lucrare"); cap = subprocess.run(["git", "-C", d, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    Path(d, ".kelion", "lucrari").mkdir(parents=True)
    Path(d, ".kelion", "lucrari", "L1.receipt.json").write_text(json.dumps({"base_commit": baza, "commit": cap}))
    return d


def judeca_aduna(copie):
    return 0 if "a + b" in (copie / "aduna.py").read_text() and (copie / "test.sh").exists() else 1


class Teste(unittest.TestCase):
    def test_izolat_fara_retea_fara_server_fara_secrete(self):
        d, f = proiect(), Fals()
        Path(d, ".env").write_text("K=1"); Path(d, "id_rsa").write_text("x"); Path(d, ".git").mkdir(); Path(d, ".git", "config").write_text("token")
        t = VI.verifica(d, "L1", rulare=f)
        self.assertTrue(t.startswith("PARTIAL") and "rosu->verde" in t, t)   # fara receipt: nu e VERIFICAT
        a = f.argvs[0]
        for x in ("--unshare-all", "--clearenv", "--die-with-parent", "--new-session"):
            self.assertIn(x, a)
        self.assertEqual(a[a.index("--bind") + 2], "/work"); self.assertEqual(a[-2:], ["/usr/bin/bash", "test.sh"])
        self.assertFalse(any(x.startswith(("/opt", "/var", "/home", "/srv")) for x in a), a)
        self.assertFalse(any("kelion" in x for x in a if x.startswith("/etc")))
        for interzis in (".kelion", ".env", "id_rsa", ".git", ".git/config"):
            self.assertNotIn(interzis, f.copii[0])
        self.assertFalse(Path(d, "scris-de-test.txt").exists())

    def test_verificat_doar_rosu_apoi_verde(self):
        d = git_proiect("def f(a, b):\n    return a - b\n", "def f(a, b):\n    return a + b\n")
        f = Fals(judeca=judeca_aduna)
        t = VI.verifica(d, "L1", rulare=f)
        self.assertTrue(t.startswith("VERIFICAT") and "rosu->verde" in t, t)
        self.assertEqual(len(f.argvs), 2)
        self.assertIn("test.sh", f.copii[1])            # testul nou pus peste codul vechi
        self.assertNotIn(".env", f.copii[1]); self.assertNotIn(".env", f.copii[0])

    def test_test_care_trece_si_fara_reparatie_nu_e_dovada(self):
        d = git_proiect("def f(a, b):\n    return a + b\n", "def f(a, b):\n    return a + b  # comentariu\n")
        t = VI.verifica(d, "L1", rulare=Fals(cod=0))
        self.assertTrue(t.startswith("PARTIAL") and "nu dovedesc reparatia" in t, t)

    def test_test_vechi_care_pica_inainte_e_dovada(self):
        d = git_proiect("def f(a, b):\n    return a - b\n", "def f(a, b):\n    return a + b\n", test_in_lucrare=False)
        t = VI.verifica(d, "L1", rulare=Fals(judeca=judeca_aduna))
        self.assertTrue(t.startswith("VERIFICAT"), t)

    def test_esuat_timeout_fara_teste(self):
        self.assertTrue(VI.verifica(proiect(), "L", rulare=Fals(cod=3, out="AssertionError")).startswith("ESUAT"))
        t = VI.verifica(proiect(), "L", rulare=Fals(ex=subprocess.TimeoutExpired("bwrap", 5)))
        self.assertTrue(t.startswith("ESUAT") and "cod 124" in t, t)
        t = VI.verifica(proiect(test=None), "L", rulare=Fals())
        self.assertTrue(t.startswith("PARTIAL") and "fara teste" in t, t)
        self.assertTrue(VI.verifica("/nu/exista", "L").startswith("INDISPONIBIL"))
        t = VI.verifica(proiect(), "L", rulare=Fals(ex=FileNotFoundError("bwrap")))
        self.assertTrue(t.startswith("INDISPONIBIL"), t)

    def test_iesirea_e_limitata_si_timpul_respectat(self):
        p = VI.ruleaza_limitat(["/usr/bin/python3", "-c", "import sys\nfor _ in range(4000): sys.stdout.write('x'*1000)"], timeout=30)
        self.assertEqual(p.returncode, 0); self.assertLessEqual(len(p.stdout), VI.LIMITA_IESIRE)
        with self.assertRaises(subprocess.TimeoutExpired):
            VI.ruleaza_limitat(["/usr/bin/sleep", "5"], timeout=1)

    def test_se_testeaza_commitul_din_receipt_nu_directorul_de_lucru(self):
        d = git_proiect("def f(a, b):\n    return a - b\n", "def f(a, b):\n    return a * b\n")   # commit stricat
        Path(d, "aduna.py").write_text("def f(a, b):\n    return a + b\n")                          # reparat doar in director
        t = VI.verifica(d, "L1", rulare=Fals(judeca=judeca_aduna))
        self.assertTrue(t.startswith("ESUAT"), t)

    def test_rosu_din_pregatire_nu_e_dovada(self):
        d = git_proiect("def f(a, b):\n    return a - b\n", "def f(a, b):\n    return a + b\n")
        judeca = lambda c: 0 if "a + b" in (c / "aduna.py").read_text() else (1, "ModuleNotFoundError: No module named 'x'")
        t = VI.verifica(d, "L1", rulare=Fals(judeca=judeca))
        self.assertTrue(t.startswith("PARTIAL") and "pregatire" in t, t)

    def test_dependentele_instalate_ajung_in_copii_si_limita_e_comuna(self):
        d = git_proiect("def f(a, b):\n    return a - b\n", "def f(a, b):\n    return a + b\n")
        Path(d, "node_modules", "pachet").mkdir(parents=True); Path(d, "node_modules", "pachet", "index.js").write_text("//")
        f = Fals(judeca=judeca_aduna)
        t = VI.verifica(d, "L1", limita=50, rulare=f)
        self.assertTrue(t.startswith("PARTIAL") and "node_modules" in t, t)   # dependente nelegate de commit: nu e dovada
        for c in f.copii:
            self.assertIn("node_modules/pachet/index.js", c)
        self.assertLessEqual(f.timeouts[1], f.timeouts[0]); self.assertLessEqual(f.timeouts[0], 50)

    def test_testul_care_se_modifica_singur_nu_dovedeste(self):
        d = git_proiect("def f(a, b):\n    return a + b\n", "def f(a, b):\n    return a + b  # nimic reparat\n")
        def judeca(c):
            t = (c / "test.sh").read_text()
            if "exit 1" in t:
                return 1
            (c / "test.sh").write_text("exit 1\n")   # «verde» isi strica testul ca baza sa pice
            return 0
        t = VI.verifica(d, "L1", rulare=Fals(judeca=judeca))
        self.assertFalse(t.startswith("VERIFICAT"), t)

    def test_legatura_spre_director_in_baza_nu_scrie_afara(self):
        afara = Path(tempfile.mkdtemp())
        d = tempfile.mkdtemp(); g = lambda *a: subprocess.run(["git", "-C", d, "-c", "user.name=t", "-c", "user.email=t@t", *a], check=True, capture_output=True)
        g("init", "-q"); Path(d, "aduna.py").write_text("def f(a, b):\n    return a - b\n"); os.symlink(afara, Path(d, "tests"))
        g("add", "-A"); g("commit", "-qm", "baza"); baza = subprocess.run(["git", "-C", d, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        os.unlink(Path(d, "tests")); Path(d, "tests").mkdir(); Path(d, "tests", "test_x.py").write_text("x")
        Path(d, "aduna.py").write_text("def f(a, b):\n    return a + b\n"); Path(d, "test.sh").write_text("true\n")
        g("add", "-A"); g("commit", "-qm", "lucrare"); cap = subprocess.run(["git", "-C", d, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        Path(d, ".kelion", "lucrari").mkdir(parents=True)
        Path(d, ".kelion", "lucrari", "L1.receipt.json").write_text(json.dumps({"base_commit": baza, "commit": cap}))
        VI.verifica(d, "L1", rulare=Fals(judeca=lambda c: 0 if "a + b" in (c / "aduna.py").read_text() else 1))
        self.assertEqual(list(afara.iterdir()), [])

    def test_limita_de_marime_pe_commit(self):
        d = git_proiect("def f(a, b):\n    return a - b\n", "def f(a, b):\n    return a + b\n")
        vechi = VI.LIMITA_OCTETI
        try:
            VI.LIMITA_OCTETI = 10 ** 9
            m = VI._marime_rev(d, "HEAD"); self.assertGreater(m, 0)
            VI.LIMITA_OCTETI = m - 1
            t = VI.verifica(d, "L1", rulare=Fals(judeca=judeca_aduna))
            self.assertFalse(t.startswith("VERIFICAT"), t)
        finally:
            VI.LIMITA_OCTETI = vechi

    @unittest.skipUnless(shutil.which("bwrap"), "bwrap lipseste")
    def test_bwrap_real(self):
        d = proiect("ls /opt/kelion-brain 2>/dev/null && exit 9; getent hosts github.com && exit 8; echo izolat")
        t = VI.verifica(d, "L")
        self.assertTrue(t.startswith(("PARTIAL", "INDISPONIBIL", "ESUAT")), t)


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
