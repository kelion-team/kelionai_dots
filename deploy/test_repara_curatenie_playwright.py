import os, subprocess, sys, tempfile, unittest
from pathlib import Path
AICI = Path(__file__).parent
SCRIPT = AICI / "repara_curatenie_playwright.py"
EXEC = '''import time
class E:
    def stare(self, loc):
        if True:
            from playwright.sync_api import sync_playwright
            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{loc.port_cdp}", timeout=3000)
                    pages = [p for c in browser.contexts for p in c.pages]
                    if len(pages) != 1:
                        return 1
                    return 2
            except Exception:
                return 0
'''
PAZ = '''async def chrome():
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        b = await p.chromium.connect_over_cdp(CDP)
        pg = b
        logat = True
        buton = None
        return {"logat": logat, "buton_apel": buton, "url": pg.url[:60]}
'''


class Teste(unittest.TestCase):
    def ruleaza(self, src):
        dest = tempfile.mkdtemp()
        return subprocess.run([sys.executable, "-B", str(SCRIPT), src, dest], capture_output=True, text=True), Path(dest)

    def sursa(self, ex=EXEC, pz=PAZ):
        d = Path(tempfile.mkdtemp()); (d / "pod_locuri").mkdir()
        (d / "pod_locuri/executor_server.py").write_text(ex); (d / "paznic.py").write_text(pz)
        return str(d)

    def test_aplica_si_proba(self):
        r, dest = self.ruleaza(self.sursa())
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        ex = (dest / "pod_locuri/executor_server.py").read_text()
        self.assertIn("contextlib.closing(", ex)
        self.assertNotIn("browser = pw.chromium.connect_over_cdp", ex)
        self.assertIn("stiva.push_async_callback(b.close)", (dest / "paznic.py").read_text())

    def test_a_doua_rulare_refuzata(self):
        r, dest = self.ruleaza(self.sursa())
        r2, _ = self.ruleaza(str(dest))
        self.assertNotEqual(r2.returncode, 0); self.assertIn("DEJA APLICAT", r2.stdout + r2.stderr)

    def test_actualizare_de_la_prima_versiune(self):
        v1_ex = EXEC.replace("            from playwright.sync_api import sync_playwright\n",
                             "            import contextlib\n            from playwright.sync_api import sync_playwright\n").replace(
            "                with sync_playwright() as pw:\n                    browser = pw.chromium.connect_over_cdp(f\"http://127.0.0.1:{loc.port_cdp}\", timeout=3000)\n",
            "                with sync_playwright() as pw, contextlib.closing(\n                        pw.chromium.connect_over_cdp(f\"http://127.0.0.1:{loc.port_cdp}\", timeout=3000)) as browser:\n")
        v1_pz = PAZ.replace('        return {"logat": logat, "buton_apel": buton, "url": pg.url[:60]}\n',
            '        rez = {"logat": logat, "buton_apel": buton, "url": pg.url[:60]}\n'
            '        await b.close()   # doar deconectare + ștergerea directorului temporar; Chrome rămâne\n'
            '        return rez\n')
        r, dest = self.ruleaza(self.sursa(ex=v1_ex, pz=v1_pz))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual((dest / "pod_locuri/executor_server.py").read_text(), v1_ex)
        pz = (dest / "paznic.py").read_text()
        self.assertIn("stiva.push_async_callback(b.close)", pz); self.assertNotIn("return rez", pz)

    def test_text_schimbat_nu_scrie_nimic(self):
        r, dest = self.ruleaza(self.sursa(ex=EXEC.replace("timeout=3000", "timeout=5000")))
        self.assertNotEqual(r.returncode, 0); self.assertIn("OPRIT", r.stdout + r.stderr)
        self.assertEqual(list(dest.iterdir()), [])


class InchidereLaExceptie(unittest.TestCase):
    def test_stiva_inchide_si_la_exceptie(self):
        import asyncio, contextlib
        inchis = []
        class B:
            async def close(self): inchis.append(1)
        async def chrome():
            async with contextlib.AsyncExitStack() as stiva:
                b = B(); stiva.push_async_callback(b.close)
                raise RuntimeError("pagina a picat")
        with self.assertRaises(RuntimeError): asyncio.run(chrome())
        self.assertEqual(inchis, [1])


if __name__ == "__main__":
    unittest.main()
