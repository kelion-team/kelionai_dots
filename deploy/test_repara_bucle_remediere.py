import json, os, re, subprocess, sys, tempfile, time, unittest
from pathlib import Path
SCRIPT = Path(__file__).with_name("repara_bucle_remediere.py")
VER = '''import re
out = []
for x in v:
    cheie = "picat|" + x["ce"] + "|" + x["detaliu"][:80]
    out.append(cheie)
'''
TES = '''import json, os, time
OUT = "{out}"
PUSE = []
class C:
    @staticmethod
    def adauga(p, text, sursa):
        PUSE.append(text); return {{"id": "S%d" % len(PUSE)}}
def main(defecte):
    rez = {{}}
    if defecte and os.environ.get("KELION_TESTER_REPARA", "1") == "1":
        try:
            s = C.adauga("p", " | ".join(defecte), "t")
            rez["reparatie"] = s["id"] + (" (exista deja, urmarita)" if s.get("_exista") else " (noua)")
        except Exception as e:
            rez["reparatie"] = str(e)
    return rez
'''


class Teste(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp()); self.out = self.d / "tester.json"
        (self.d / "verifica-site.py").write_text(VER); (self.d / "tester-ui.py").write_text(TES.format(out=self.out))

    def aplica(self):
        dest = Path(tempfile.mkdtemp())
        r = subprocess.run([sys.executable, "-B", str(SCRIPT), str(self.d), str(dest)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return dest

    def test_cheia_verificatorului_nu_depinde_de_cifre(self):
        cod = (self.aplica() / "verifica-site.py").read_text()
        def chei(v):
            ns = {"v": v}; exec(cod, ns); return ns["out"]
        a = chei([{"ce": "Tester", "detaliu": "Tester 02:55 (acum 8 min): /app/ PICAT, reimprospatare 4.0 s"}])
        b = chei([{"ce": "Tester", "detaliu": "Tester 03:05 (acum 18 min): /app/ PICAT, reimprospatare 4.5 s"}])
        self.assertEqual(a, b)
        c = chei([{"ce": "Tester", "detaliu": "Tester 03:05: /app/cont PICAT"}])
        self.assertNotEqual(a, c)

    def test_testerul_pune_o_singura_sarcina_pentru_aceleasi_defecte(self):
        ns = {}; exec((self.aplica() / "tester-ui.py").read_text(), ns)
        r1 = ns["main"](["/app/: reimprospatare 4.0 s"]); r2 = ns["main"](["/app/: reimprospatare 4.4 s"])
        self.assertEqual(len(ns["PUSE"]), 1); self.assertIn("deja in coada", r2["reparatie"])
        ns["main"](["/app/cerinte.html: datele nu se afiseaza"])
        self.assertEqual(len(ns["PUSE"]), 2)

    def test_a_doua_rulare_refuzata(self):
        dest = self.aplica()
        r = subprocess.run([sys.executable, "-B", str(SCRIPT), str(dest), tempfile.mkdtemp()], capture_output=True, text=True)
        self.assertIn("DEJA APLICAT", r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
