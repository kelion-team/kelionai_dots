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
