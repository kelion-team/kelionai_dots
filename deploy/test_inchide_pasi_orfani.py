import importlib.util, sqlite3, tempfile, unittest
from pathlib import Path
spec = importlib.util.spec_from_file_location("o", Path(__file__).with_name("inchide_pasi_orfani.py"))
o = importlib.util.module_from_spec(spec); spec.loader.exec_module(o)


class Teste(unittest.TestCase):
    def test_doar_procesele_moarte_se_inchid(self):
        import os
        cale = str(Path(tempfile.mkdtemp()) / "j.sqlite3")
        db = sqlite3.connect(cale)
        db.execute("CREATE TABLE pasi(id INTEGER PRIMARY KEY, cerere TEXT, stare TEXT, t_start REAL, t_sfarsit REAL, dovada TEXT, pid INTEGER, amprenta TEXT)")
        m, v = 2 ** 22 + 7, os.getpid()
        db.executemany("INSERT INTO pasi(id, cerere, stare, pid, amprenta, t_start, dovada) VALUES(?,?,?,?,?,?,?)",
                       [(1, "MORT", "in executie", m, f"{m}:1", 1000, "dovada veche"), (2, "VIU", "in executie", v, f"{v}:1", 1000, None),
                        (3, "GATA", "gata", m, f"{m}:1", 1000, None), (4, "RECENT", "in executie", m, f"{m}:1", 9000, None),
                        (5, "FARA_AMPRENTA", "in executie", m, None, 1000, None), (6, "FARA_PID", "in executie", None, None, 1000, None)])
        db.commit(); db.close()
        self.assertEqual([c for _, c, _ in o.inchide(cale, acum=10000)], ["MORT"])
        st = dict(sqlite3.connect(cale).execute("SELECT cerere, stare FROM pasi"))
        self.assertEqual(st, {"MORT": "esuat", "VIU": "in executie", "GATA": "gata", "RECENT": "in executie",
                              "FARA_AMPRENTA": "in executie", "FARA_PID": "in executie"})
        dov = sqlite3.connect(cale).execute("SELECT dovada FROM pasi WHERE id=1").fetchone()[0]
        self.assertTrue(dov.startswith("dovada veche | proces mort"))
        self.assertEqual(o.inchide(cale, acum=10000), [])

    def test_eroare_sqlite_iese_cu_cod(self):
        import subprocess, sys
        r = subprocess.run([sys.executable, "-B", spec.origin, str(Path(tempfile.mkdtemp()) / "nu-are-tabel.sqlite3")], capture_output=True)
        self.assertNotEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()
