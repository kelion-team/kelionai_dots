import importlib.util, sqlite3, tempfile, unittest
from pathlib import Path
spec = importlib.util.spec_from_file_location("o", Path(__file__).with_name("inchide_pasi_orfani.py"))
o = importlib.util.module_from_spec(spec); spec.loader.exec_module(o)


class Teste(unittest.TestCase):
    def test_doar_procesele_moarte_se_inchid(self):
        import os
        cale = str(Path(tempfile.mkdtemp()) / "j.sqlite3")
        db = sqlite3.connect(cale)
        db.execute("CREATE TABLE pasi(id INTEGER PRIMARY KEY, cerere TEXT, stare TEXT, t_sfarsit REAL, dovada TEXT, pid INTEGER)")
        db.executemany("INSERT INTO pasi(id, cerere, stare, pid) VALUES(?,?,?,?)",
                       [(1, "MORT", "in executie", 2 ** 22 + 7), (2, "VIU", "in executie", os.getpid()), (3, "GATA", "gata", 2 ** 22 + 7)])
        db.commit(); db.close()
        self.assertEqual([c for _, c, _ in o.inchide(cale)], ["MORT"])
        st = dict(sqlite3.connect(cale).execute("SELECT cerere, stare FROM pasi"))
        self.assertEqual(st, {"MORT": "esuat", "VIU": "in executie", "GATA": "gata"})
        self.assertEqual(o.inchide(cale), [])


if __name__ == "__main__":
    unittest.main()
