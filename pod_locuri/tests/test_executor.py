import os
import tempfile
import time
import unittest
from unittest import mock

from pod_locuri.executor_server import ExecutorServer
from pod_locuri.locuri import descrie_loc, LOGIN_NECESAR, PORNIRE


class ProcViu:
    def poll(self):
        return None


class LoginTests(unittest.TestCase):
    def test_dupa_logare_reporneste_in_mod_pod(self):
        with tempfile.TemporaryDirectory() as d:
            ex = ExecutorServer(jurnal_cale=os.path.join(d, "j"), alerte_cale=os.path.join(d, "a"))
            loc = descrie_loc(5, director_profile=d)
            pornite = []
            with mock.patch.object(ex, "_sinks", return_value={loc.wa_in}), \
                 mock.patch("pod_locuri.executor_server.subprocess.Popen", side_effect=lambda *a, **k: ProcViu()) as popen, \
                 mock.patch.object(ex, "opreste", side_effect=lambda l: ex.procese.pop(l.numar, None)):
                ex.porneste(loc, login=True)
                self.assertFalse(any("--remote-debugging-port" in x for x in popen.call_args[0][0]))
                self.assertEqual(ex.pregatit(loc), LOGIN_NECESAR)          # încă nelogat
                cookies = os.path.join(loc.profil, "Default", "Network", "Cookies")
                os.makedirs(os.path.dirname(cookies))
                open(cookies, "w").close()                                 # Adrian s-a logat: cookie-urile se schimbă
                self.assertEqual(ex.pregatit(loc), LOGIN_NECESAR)          # așteaptă să se liniștească
                ex.login[5][2] -= 30                                       # 30 s fără alte schimbări
                self.assertEqual(ex.pregatit(loc), PORNIRE)                # repornit în modul pod
                self.assertTrue(any("--remote-debugging-port=%d" % loc.port_cdp in x for x in popen.call_args[0][0]))
                self.assertNotIn(5, ex.login)


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
