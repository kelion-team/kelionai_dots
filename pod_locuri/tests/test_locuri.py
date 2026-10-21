import json
import os
import tempfile
import time
import unittest

from pod_locuri.locuri import Manager, descrie_loc, comanda_chrome, comenzi_sunet, PREGATIT, OCUPAT, LOGIN_NECESAR, OPRIT
from pod_locuri.resurse import Config, calculeaza, CONFIG_IMPLICIT

MB = 1024


class FakeExec:
    def __init__(self):
        self.pornite, self.oprite, self.alerte, self.ev = [], [], [], []
        self.nelogate = set()

    def porneste(self, loc, login=False):
        self.pornite.append((loc.numar, login))

    def opreste(self, loc):
        self.oprite.append(loc.numar)

    def pregatit(self, loc):
        return LOGIN_NECESAR if loc.numar in self.nelogate else PREGATIT

    def alerta(self, text):
        self.alerte.append(text)

    def jurnal(self, e):
        self.ev.append(e)


def resurse_fixe(maxim):
    holder = {"maxim": maxim}

    def citeste(cfg, active):
        from pod_locuri.resurse import Capacitate
        return Capacitate(12000, 9000, 6, 0.3, holder["maxim"], holder["maxim"], holder["maxim"], "RAM")
    return holder, citeste


class ResurseTests(unittest.TestCase):
    @staticmethod
    def scrie(cale, data, text=None):
        with open(cale, "w") as h:
            h.write(text if text is not None else json.dumps(data))

    def test_capacitate_din_ram_si_cpu(self):
        cfg = dict(CONFIG_IMPLICIT)
        cap = calculeaza(cfg, meminfo={"MemTotal": 11960, "MemAvailable": 9300}, nuclee=6, incarcare=0.5, cgroup_mb=None)
        # RAM: (9300 - 20% din 11960) / 650 = 10,6 -> 10 ; CPU: (6*0.75 - 0.5) / 0.15 = 26
        self.assertEqual(cap.maxim_ram, 10)
        self.assertEqual(cap.maxim, 10)
        self.assertEqual(cap.motiv, "RAM")

    def test_server_marit_creste_singur(self):
        cfg = dict(CONFIG_IMPLICIT)
        mic = calculeaza(cfg, meminfo={"MemTotal": 11960, "MemAvailable": 9300}, nuclee=6, incarcare=0.5, cgroup_mb=None)
        mare = calculeaza(cfg, meminfo={"MemTotal": 23920, "MemAvailable": 21000}, nuclee=12, incarcare=0.5, cgroup_mb=None)
        self.assertGreater(mare.maxim, mic.maxim * 1.8)

    def test_locuri_active_nu_scad_maximul(self):
        cfg = dict(CONFIG_IMPLICIT)
        gol = calculeaza(cfg, meminfo={"MemTotal": 11960, "MemAvailable": 9300}, nuclee=6, incarcare=0.5, cgroup_mb=None)
        plin = calculeaza(cfg, meminfo={"MemTotal": 11960, "MemAvailable": 9300 - 4 * 650}, nuclee=6,
                          incarcare=0.5 + 4 * 0.15, cgroup_mb=None, locuri_active=4)
        self.assertEqual(gol.maxim, plin.maxim)

    def test_config_recitita_fara_restart(self):
        with tempfile.TemporaryDirectory() as d:
            cale = os.path.join(d, "locuri.json")
            self.scrie(cale, {"ram_pe_loc_mb": 650})
            cfg = Config(cale)
            self.assertTrue(cfg.actualizeaza())
            self.assertFalse(cfg.actualizeaza())
            time.sleep(0.01)
            self.scrie(cale, {"ram_pe_loc_mb": 300})
            os.utime(cale, ns=(time.time_ns() + 10**9, time.time_ns() + 10**9))
            self.assertTrue(cfg.actualizeaza())
            self.assertEqual(cfg.valori["ram_pe_loc_mb"], 300)
            self.scrie(cale, None, "{stricat")
            os.utime(cale, ns=(time.time_ns() + 2 * 10**9, time.time_ns() + 2 * 10**9))
            self.assertFalse(cfg.actualizeaza())
            self.assertEqual(cfg.valori["ram_pe_loc_mb"], 300)   # o configurare stricată nu o înlocuiește pe cea bună


class IzolareTests(unittest.TestCase):
    def test_fiecare_loc_are_sunet_port_si_profil_propriu(self):
        locuri = [descrie_loc(n) for n in range(1, 11)]
        for camp in ("wa_in", "chrome_out", "mic", "port_cdp", "profil"):
            valori = [getattr(l, camp) for l in locuri]
            self.assertEqual(len(set(valori)), len(valori), camp)
        self.assertNotIn(9278, [l.port_cdp for l in locuri])          # portul invitaților rămâne neatins
        self.assertNotIn("/var/lib/kelion-pod/chrome2", [l.profil for l in locuri])

    def test_chrome_foloseste_doar_sunetul_locului_lui(self):
        loc = descrie_loc(3)
        env, args = comanda_chrome(loc)
        self.assertEqual(env["PULSE_SINK"], "chrome_out_3")
        self.assertEqual(env["PULSE_SOURCE"], "mic_wa_3")
        self.assertIn("--remote-debugging-port=%d" % loc.port_cdp, args)
        sunet = " ".join(" ".join(c) for c in comenzi_sunet(loc))
        self.assertIn("master=wa_in_3.monitor", sunet)
        self.assertNotIn("wa_in ", sunet)

    def test_login_fara_automatizare_si_fara_copiere_sesiune(self):
        env, args = comanda_chrome(descrie_loc(4), login=True)
        self.assertTrue(args[-1].endswith("/auth/login"))
        self.assertFalse(any(a.startswith("--remote-debugging") for a in args))
        self.assertTrue(any(a == "--user-data-dir=/var/lib/kelion-pod/loc4" for a in args))


class ManagerTests(unittest.TestCase):
    def setUp(self):
        self.ex = FakeExec()
        self.res, citeste = resurse_fixe(3)
        self.m = Manager(self.ex, None, citeste_resurse=citeste)

    def test_tine_locuri_pregatite_si_aloca_fara_ocupat(self):
        self.m.sincronizeaza()
        self.assertEqual([l.stare for l in self.m.locuri.values()].count(PREGATIT), 2)
        a = self.m.aloca("apel-1")
        b = self.m.aloca("apel-2")
        c = self.m.aloca("apel-3")
        self.assertEqual(len({a.numar, b.numar, c.numar}), 3)
        self.assertTrue(all(l.stare == OCUPAT for l in (a, b, c)))
        self.assertIsNone(self.m.aloca("apel-4"))             # peste maxim: ocupat + alertă
        self.assertEqual(len(self.ex.alerte), 1)

    def test_server_marit_primeste_apeluri_noi_fara_restart(self):
        self.m.sincronizeaza()
        for i in range(3):
            self.assertIsNotNone(self.m.aloca(f"a{i}"))
        self.assertIsNone(self.m.aloca("a3"))
        self.res["maxim"] = 6                                  # Adrian a mărit serverul
        self.assertIsNotNone(self.m.aloca("a3"))
        self.assertTrue(any(e["ev"] == "capacitate_noua" for e in self.ex.ev))

    def test_eliberare_redevine_pregatit_si_nu_atinge_alte_apeluri(self):
        self.m.sincronizeaza()
        a = self.m.aloca("x")
        b = self.m.aloca("y")
        self.m.elibereaza("x")
        self.assertEqual(a.stare, PREGATIT)
        self.assertEqual(b.stare, OCUPAT)
        self.assertEqual(b.apel, "y")

    def test_acelasi_apel_nu_primeste_doua_locuri(self):
        self.m.sincronizeaza()
        self.assertIs(self.m.aloca("dup"), self.m.aloca("dup"))

    def test_loc_nelogat_porneste_in_mod_login_si_anunta_o_data(self):
        self.ex.nelogate = {2}
        self.m.sincronizeaza()
        self.assertEqual(self.m.locuri[2].stare, LOGIN_NECESAR)
        self.assertIn((2, True), self.ex.pornite)
        self.m.sincronizeaza()
        self.assertEqual(sum("logarea" in a for a in self.ex.alerte), 1)
        self.ex.nelogate = set()                               # Adrian s-a logat
        self.m.sincronizeaza()
        self.assertEqual(self.m.locuri[2].stare, PREGATIT)

    def test_locurile_libere_in_plus_se_opresc_dar_niciodata_cele_ocupate(self):
        self.res["maxim"] = 6
        self.m.sincronizeaza()
        apeluri = [self.m.aloca(f"z{i}") for i in range(4)]
        self.m.sincronizeaza()
        for i in range(4):
            self.m.elibereaza(f"z{i}")
        self.m.sincronizeaza()
        pregatite = [l for l in self.m.locuri.values() if l.stare == PREGATIT]
        self.assertLessEqual(len(pregatite), 2 + 1)            # rezerva (+ locul 1, care nu se oprește)
        self.assertTrue(all(l.stare in (PREGATIT, OPRIT) for l in self.m.locuri.values()))


if __name__ == "__main__":
    unittest.main()
