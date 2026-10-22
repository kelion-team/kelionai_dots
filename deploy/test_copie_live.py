import importlib.util, os, subprocess, sys, tempfile, unittest
from pathlib import Path
AICI = Path(__file__).parent
spec = importlib.util.spec_from_file_location("copie_live", AICI / "copie_live.py")
CL = importlib.util.module_from_spec(spec); spec.loader.exec_module(CL)


class Teste(unittest.TestCase):
    def test_copie_fara_secrete_si_date_personale(self):
        src = Path(tempfile.mkdtemp())
        (src / "brain.py").write_text("print('ok')\n")
        (src / "cerinte").mkdir(); (src / "cerinte" / "registru-zi.json").write_text("{}")
        for d in ("work", "cariera", "venv", "tunnel", "backup-x"):
            (src / d).mkdir(); (src / d / "a.py").write_text("x")
        (src / "noutati.jsonl").write_text("{}"); (src / "kelion.env").write_text("K=1"); (src / "jurnal.sqlite3").write_text("x")
        (src / "cheie.py").write_text("T = 'sk-" + "a" * 30 + "'\n")
        (src / "poza.png").write_bytes(b"\x89PNG")
        site = Path(tempfile.mkdtemp()); (site / "app").mkdir(); (site / "app" / "nav.js").write_text("//")
        sen = Path(tempfile.mkdtemp()) / "verificare-site.json"; sen.write_text("{}")
        proiect = Path(tempfile.mkdtemp())
        nota = CL.sincronizeaza(str(proiect), surse=((str(src), "opt-kelion-brain"), (str(site), "var-www-kelion")), senzori=(str(sen),))
        live = proiect / ".kelion" / "live"
        fis = sorted(str(p.relative_to(live)) for p in live.rglob("*") if p.is_file())
        self.assertEqual(fis, ["INDEX.md", "opt-kelion-brain/brain.py", "opt-kelion-brain/cerinte/registru-zi.json",
                               "senzori/verificare-site.json", "var-www-kelion/app/nav.js"])
        self.assertIn("cheie.py", (live / "INDEX.md").read_text())   # numit, necopiat
        self.assertIn("DOAR DE CITIT", nota)
        self.assertFalse(os.access(live / "opt-kelion-brain" / "brain.py", os.W_OK) and os.geteuid() != 0)
        CL.sincronizeaza(str(proiect), surse=((str(src), "opt-kelion-brain"),), senzori=())   # re-rulare: copia veche se inlocuieste
        self.assertFalse((live / "var-www-kelion").exists())


COADA = '''import time, uuid
def porneste(s, text, d):
    try:
        raise ValueError("x")
    except Exception as e:
        s.setdefault("istoric", []).append(f"{time.strftime('%Y-%m-%d %H:%M')} preluare fisiere necomise esuata: {type(e).__name__}: {str(e)[:160]}")
    lid = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]
    return text
'''


class Patch(unittest.TestCase):
    def test_patch_si_rerulare(self):
        s = Path(tempfile.mkdtemp()); (s / "coada-lucru.py").write_text(COADA)
        d = Path(tempfile.mkdtemp())
        r = subprocess.run([sys.executable, "-B", str(AICI / "repara_copie_live.py"), str(s), str(d)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r2 = subprocess.run([sys.executable, "-B", str(AICI / "repara_copie_live.py"), str(d), str(tempfile.mkdtemp())], capture_output=True, text=True)
        self.assertIn("DEJA APLICAT", r2.stdout)
        sys.path.insert(0, str(AICI)); ns = {}
        exec((d / "coada-lucru.py").read_text(), ns)
        out = ns["porneste"]({}, "SARCINA", tempfile.mkdtemp())
        self.assertTrue(out.startswith("COPIA LIVE") and out.endswith("SARCINA"), out[:80])

    def test_ancora_lipsa(self):
        s = Path(tempfile.mkdtemp()); (s / "coada-lucru.py").write_text("x = 1\n")
        r = subprocess.run([sys.executable, "-B", str(AICI / "repara_copie_live.py"), str(s), str(tempfile.mkdtemp())], capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0); self.assertIn("OPRIT", r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
