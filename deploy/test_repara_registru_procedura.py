import json, subprocess, sys, tempfile, unittest
from pathlib import Path
SCRIPT = Path(__file__).with_name("repara_registru_procedura.py")
COADA = '''import os
BAZA = "/x"
def delegare_rol(s):
    try:
        import types
        RD = types.SimpleNamespace(delegare=lambda r, s, b: ("ROL", "PREFIX"))
        rol = subrol = None; ales = ""
        efectiv, prefix = RD.delegare(rol, subrol, BAZA)
        return efectiv + ales, prefix
    except Exception as e:
        return "x", ""
'''


class Teste(unittest.TestCase):
    def test_procedura_in_instructiuni_si_registru(self):
        s = Path(tempfile.mkdtemp()); (s / "cerinte").mkdir()
        (s / "coada-lucru.py").write_text(COADA)
        (s / "cerinte" / "registru-zi.json").write_text(json.dumps({"cerinte": [{"id": i, "verifica": {}} for i in ("R17", "R20", "R33", "A4", "A12", "R1")]}))
        d = Path(tempfile.mkdtemp())
        r = subprocess.run([sys.executable, "-B", str(SCRIPT), str(s), str(d)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        (d / "cerinte" / "procedura-nou.md").write_text("PROCEDURA KELION")
        ns = {"__file__": str(d / "coada-lucru.py")}; exec((d / "coada-lucru.py").read_text(), ns)
        self.assertEqual(ns["delegare_rol"]({}), ("ROL", "PREFIX\n\nPROCEDURA KELION"))
        (d / "cerinte" / "procedura-nou.md").unlink()
        rol, pref = ns["delegare_rol"]({})
        self.assertIn("indisponibila", rol); self.assertTrue(pref.startswith("OPRESTE"))
        reg = {x["id"]: x for x in json.loads((d / "cerinte" / "registru-zi.json").read_text())["cerinte"]}
        self.assertIn("Plasa de siguranta", reg["R20"]["verifica"]["contine"]); self.assertIn("test.sh (OBLIGATORIU", reg["R33"]["verifica"]["contine"]); self.assertEqual(reg["R1"]["verifica"], {})


if __name__ == "__main__":
    unittest.main()
