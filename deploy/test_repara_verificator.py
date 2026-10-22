import os, subprocess, sys, tempfile, unittest
from pathlib import Path
SCRIPT = Path(__file__).with_name("repara_verificator.py")
SURSA = '''import os
WWW = "/var/www/kelion"
def lega(tinta, href):
    for _ in [0]:
        if tinta.startswith("/app/api/"):
            continue
        return "verificat"
    return "sarit"
def functionare(href):
    if True:
        if href.endswith("Kelion-Brain-Setup.run"):
            return False, "arhiva stricata"
        return True, "pagina statica"
'''


class Teste(unittest.TestCase):
    def ruleaza(self, text):
        s, d = tempfile.mkdtemp(), tempfile.mkdtemp()
        Path(s, "verifica-site.py").write_text(text)
        return subprocess.run([sys.executable, "-B", str(SCRIPT), s, d], capture_output=True, text=True), Path(d)

    def test_portal_si_kit_retras(self):
        r, d = self.ruleaza(SURSA)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        ns = {}
        exec(compile(Path(d, "verifica-site.py").read_text(), "v", "exec"), ns)
        self.assertEqual(ns["lega"]("/app/cont", "/app/cont"), "sarit")
        self.assertEqual(ns["lega"]("/app/control-api/state", "x"), "sarit")
        self.assertEqual(ns["lega"]("/app/oglinda.html", "x"), "verificat")
        with tempfile.TemporaryDirectory() as www:
            ns["WWW"] = www
            k = Path(www, "app/descarcari/linux"); k.mkdir(parents=True)
            (k / "Kelion-Brain-Setup.run").write_text("#!/bin/bash\nprintf RETRASA\nexit 78\n")
            ok, txt = ns["functionare"]("/app/descarcari/linux/Kelion-Brain-Setup.run")
            self.assertTrue(ok); self.assertIn("retras", txt)
            (k / "Kelion-Brain-Setup.run").write_text("#!/bin/bash\n__PAYLOAD__\n")
            self.assertEqual(ns["functionare"]("/app/descarcari/linux/Kelion-Brain-Setup.run"), (False, "arhiva stricata"))

    def test_text_schimbat_oprit(self):
        r, d = self.ruleaza(SURSA.replace('"/app/api/"', '"/app/api2/"'))
        self.assertNotEqual(r.returncode, 0); self.assertEqual(list(d.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
