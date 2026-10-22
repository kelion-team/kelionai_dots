import json, subprocess, sys, tempfile, unittest
from pathlib import Path
AICI = Path(__file__).parent


class Laptop(unittest.TestCase):
    def test_patch_registru_si_rerulare(self):
        s = Path(tempfile.mkdtemp()); (s / "cerinte").mkdir()
        (s / "verifica-site.py").write_text('d = {"aparate": [{"tip": "laptop"}, {"tip": "telefon", "chatgpt": "instalat"}]}\nnote = []\n'
                                            'def nota(*a):\n    note.append(a[0])\nif True:\n'
                                            '        for a in d["aparate"]:\n            nota(f"aparat {a[\'tip\']} raporteaza ChatGPT", str(a.get("chatgpt", "")).startswith("instalat"), None, a.get("chatgpt"))\n')
        (s / "cerinte" / "registru-zi.json").write_text(json.dumps({"cerinte": [{"id": "R1"}]}))
        (s / "cerinte" / "reguli.json").write_text(json.dumps({"informative": []}))
        d = Path(tempfile.mkdtemp())
        r = subprocess.run([sys.executable, "-B", str(AICI / "repara_laptop_retras.py"), str(s), str(d), str(AICI / "laptop-retras.md")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        ns = {}; exec((d / "verifica-site.py").read_text(), ns)
        self.assertEqual(ns["note"], ["aparat telefon raporteaza ChatGPT"])
        self.assertEqual([x["id"] for x in json.loads((d / "cerinte" / "registru-zi.json").read_text())["cerinte"]], ["R1", "AE1"])
        self.assertIn("laptop-retras.md", json.loads((d / "cerinte" / "reguli.json").read_text())["informative"])
        d2 = Path(tempfile.mkdtemp())   # re-rulare pe rezultat: nimic dublat
        r = subprocess.run([sys.executable, "-B", str(AICI / "repara_laptop_retras.py"), str(d), str(d2), str(AICI / "laptop-retras.md")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((d2 / "verifica-site.py").read_text(), (d / "verifica-site.py").read_text())
        self.assertEqual(len(json.loads((d2 / "cerinte" / "registru-zi.json").read_text())["cerinte"]), 2)


if __name__ == "__main__":
    unittest.main()
