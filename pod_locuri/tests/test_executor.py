import os
import tempfile
import time
import unittest
from unittest import mock

from pod_locuri.executor_server import ExecutorServer
from pod_locuri.locuri import descrie_loc, LOGIN_NECESAR, PORNIRE


def scrie_cookie(cale, nume):
    import sqlite3
    con = sqlite3.connect(cale)
    con.execute("CREATE TABLE IF NOT EXISTS cookies (host_key TEXT, name TEXT, encrypted_value BLOB)")
    con.execute("INSERT INTO cookies VALUES ('.chatgpt.com', ?, x'00')", (nume,))
    con.commit()
    con.close()


class ProcViu:
    def poll(self):
        return None


class LoginTests(unittest.TestCase):
    def test_dupa_logare_reporneste_in_mod_pod(self):
        with tempfile.TemporaryDirectory() as d:
            ex = ExecutorServer(jurnal_cale=os.path.join(d, "j"), alerte_cale=os.path.join(d, "a"))
            loc = descrie_loc(5, director_profile=d)
            pornite = []
            with mock.patch.object(ex, "_nume_sunet", return_value={loc.wa_in, loc.chrome_out, loc.mic}), \
                 mock.patch("pod_locuri.executor_server.subprocess.Popen", side_effect=lambda *a, **k: ProcViu()) as popen, \
                 mock.patch.object(ex, "opreste", side_effect=lambda l: ex.procese.pop(l.numar, None)):
                ex.porneste(loc, login=True)
                self.assertFalse(any("--remote-debugging-port" in x for x in popen.call_args[0][0]))
                self.assertEqual(ex.pregatit(loc), LOGIN_NECESAR)          # încă nelogat
                cookies = os.path.join(loc.profil, "Default", "Network", "Cookies")
                os.makedirs(os.path.dirname(cookies))
                scrie_cookie(cookies, "oai-did")                           # cookie fără sesiune (pagina de login)
                ex.login[5][2] -= 30
                self.assertEqual(ex.pregatit(loc), LOGIN_NECESAR)
                self.assertEqual(ex.pregatit(loc), LOGIN_NECESAR)          # nu se repornește fără sesiune
                scrie_cookie(cookies, "__Secure-next-auth.session-token")  # Adrian s-a logat
                os.utime(cookies, (time.time() + 5, time.time() + 5))
                self.assertEqual(ex.pregatit(loc), LOGIN_NECESAR)          # așteaptă să se liniștească
                ex.login[5][2] -= 30                                       # 30 s fără alte schimbări
                self.assertEqual(ex.pregatit(loc), PORNIRE)                # repornit în modul pod
                self.assertTrue(any("--remote-debugging-port=%d" % loc.port_cdp in x for x in popen.call_args[0][0]))
                self.assertNotIn(5, ex.login)


class SunetIdempotentTests(unittest.TestCase):
    def _ex(self, d):
        return ExecutorServer(jurnal_cale=os.path.join(d, "j"), alerte_cale=os.path.join(d, "a"))

    def test_loc_pe_jumatate_creat_completeaza_doar_ce_lipseste(self):
        with tempfile.TemporaryDirectory() as d:
            ex, loc = self._ex(d), descrie_loc(7, director_profile=d)
            rulate = []
            ok = mock.Mock(returncode=0, stdout="", stderr="")
            with mock.patch.object(ex, "_nume_sunet", return_value={loc.wa_in, "wa_in_7.monitor"}), \
                 mock.patch("pod_locuri.executor_server.subprocess.run", side_effect=lambda c, **k: rulate.append(c) or ok), \
                 mock.patch("pod_locuri.executor_server.subprocess.Popen", side_effect=lambda *a, **k: ProcViu()):
                ex.porneste(loc)
            create = [next(a for a in c if a.startswith(("sink_name=", "source_name="))) for c in rulate]
            self.assertEqual(create, ["sink_name=chrome_out_7", "source_name=mic_wa_7"])   # wa_in_7 exista deja

    def test_eroare_pactl_e_jurnalizata_cu_motivul(self):
        with tempfile.TemporaryDirectory() as d:
            ex, loc = self._ex(d), descrie_loc(8, director_profile=d)
            rau = mock.Mock(returncode=1, stdout="", stderr="Failure: Module initialization failed")
            with mock.patch.object(ex, "_nume_sunet", return_value=set()), \
                 mock.patch("pod_locuri.executor_server.subprocess.run", return_value=rau), \
                 mock.patch("pod_locuri.executor_server.subprocess.Popen") as popen:
                with self.assertRaises(RuntimeError):
                    ex.porneste(loc)
                popen.assert_not_called()                                     # fara sunet nu porneste Chrome
            jurnal = open(os.path.join(d, "j")).read()
            self.assertIn("sunet_loc_esuat", jurnal)
            self.assertIn("Module initialization failed", jurnal)

    def test_toate_bucatile_existente_nu_ruleaza_pactl(self):
        with tempfile.TemporaryDirectory() as d:
            ex, loc = self._ex(d), descrie_loc(9, director_profile=d)
            with mock.patch.object(ex, "_nume_sunet", return_value={loc.wa_in, loc.chrome_out, loc.mic}), \
                 mock.patch("pod_locuri.executor_server.subprocess.run") as run, \
                 mock.patch("pod_locuri.executor_server.subprocess.Popen", side_effect=lambda *a, **k: ProcViu()):
                ex.porneste(loc)
            run.assert_not_called()


if __name__ == "__main__":
    unittest.main()


class OprireTests(unittest.TestCase):
    def test_oprirea_locului_2_nu_atinge_locul_20(self):
        from pod_locuri.executor_server import module_ale_locului
        lista = "\n".join([
            "31\tmodule-null-sink\tsink_name=wa_in_2 rate=48000 channels=1",
            "32\tmodule-null-sink\tsink_name=chrome_out_2 rate=48000 channels=1",
            "33\tmodule-remap-source\tmaster=wa_in_2.monitor source_name=mic_wa_2",
            "71\tmodule-null-sink\tsink_name=wa_in_20 rate=48000 channels=1",
            "72\tmodule-null-sink\tsink_name=chrome_out_20 rate=48000 channels=1",
            "73\tmodule-remap-source\tmaster=wa_in_20.monitor source_name=mic_wa_20",
            "5\tmodule-null-sink\tsink_name=wa_in rate=48000 channels=1",
        ])
        self.assertEqual(module_ale_locului(lista, descrie_loc(2)), ["31", "32", "33"])
        self.assertEqual(module_ale_locului(lista, descrie_loc(20)), ["71", "72", "73"])


class CgroupTests(unittest.TestCase):
    def test_limita_cgroup_nu_e_depasita(self):
        from pod_locuri import resurse
        cfg = dict(resurse.CONFIG_IMPLICIT)
        with mock.patch.object(resurse, "cgroup_folosit_mb", return_value=3000):
            cap = resurse.calculeaza(cfg, meminfo={"MemTotal": 64000, "MemAvailable": 60000}, nuclee=32,
                                     incarcare=0.1, cgroup_mb=4000)
        # limita 4000, folosit 3000 -> liber 1000; rezerva 800 -> 200 MB, sub un loc
        self.assertLessEqual(cap.maxim_ram * cfg["ram_pe_loc_mb"], 4000)
        self.assertEqual(cap.maxim_ram, 0)

    def test_locuri_active_nu_umfla_peste_total(self):
        from pod_locuri import resurse
        cfg = dict(resurse.CONFIG_IMPLICIT)
        cap = resurse.calculeaza(cfg, meminfo={"MemTotal": 4000, "MemAvailable": 3900}, nuclee=8,
                                 incarcare=0.1, cgroup_mb=None, locuri_active=10)
        self.assertLessEqual(cap.maxim_ram * cfg["ram_pe_loc_mb"], 4000 * 0.8)
