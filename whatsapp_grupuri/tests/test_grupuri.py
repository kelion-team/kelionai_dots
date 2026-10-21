import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import whatsapp_grupuri as G   # noqa: E402


class Raspuns:
    def __init__(self, st, d):
        self.status, self._d = st, d
    def read(self):
        return json.dumps(self._d).encode()
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


class MetaFals:
    """Înlocuiește rețeaua: înregistrează cererile și răspunde ca Meta."""
    def __init__(self, raspunsuri):
        self.raspunsuri, self.cereri = raspunsuri, []
    def __call__(self, req, timeout=0):
        self.cereri.append((req.get_method(), req.full_url, json.loads(req.data) if req.data else None,
                            req.headers.get("Authorization")))
        for cheie, (st, d) in self.raspunsuri.items():
            if cheie in req.full_url and (req.get_method(), cheie) == (req.get_method(), cheie):
                return Raspuns(st, d)
        return Raspuns(404, {"error": {"code": 803, "message": "not found"}})


class MentiuneTests(unittest.TestCase):
    def test_raspunde_doar_cu_nume_si_cerere(self):
        self.assertEqual(G.cerere_pentru_kelion("Kelion, ce vreme e mâine la Londra?"), "ce vreme e mâine la Londra")
        self.assertEqual(G.cerere_pentru_kelion("ce zici @Kelion de planul ăsta"), "ce zici de planul ăsta")
        self.assertEqual(G.cerere_pentru_kelion("KELION spune-ne o glumă"), "spune-ne o glumă")
        self.assertEqual(G.cerere_pentru_kelion("Mâine mergem la munte, Kelion?"), "Mâine mergem la munte")

    def test_ignora_fara_nume_sau_fara_cerere(self):
        for t in ("Bună tuturor!", "Kelion", "Kelion!", "  kelion ?", "am intrat pe kelionai.app", "scrie la a@kelion.ro",
                  "kelionul meu", "", None):
            self.assertIsNone(G.cerere_pentru_kelion(t), t)


class ComenziTests(unittest.TestCase):
    def test_comenzi_admin(self):
        self.assertEqual(G.comanda_admin("grup nou Familie"), ("nou", "Familie"))
        self.assertEqual(G.comanda_admin("Grup nou  Prieteni de liceu."), ("nou", "Prieteni de liceu"))
        self.assertEqual(G.comanda_admin("grupuri"), ("lista", None))
        self.assertIsNone(G.comanda_admin("ce grupuri am?"))
        self.assertIsNone(G.comanda_admin("vreau un grup nou cu familia"))

    def test_corp_pentru_grup_si_persoana(self):
        self.assertEqual(G.corp_mesaj("grup:123", "salut")["recipient_type"], "group")
        self.assertEqual(G.corp_mesaj("grup:123", "salut")["to"], "123")
        self.assertEqual(G.corp_mesaj("447700", "salut")["recipient_type"], "individual")
        m = {"de_la": "447700", "grup": "G1"}
        self.assertEqual((G.destinatar(m), G.cheie_istoric(m)), ("grup:G1", "grup:G1"))
        self.assertEqual(G.destinatar({"de_la": "447700"}), "447700")


class MetaTests(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.trimise = []
        self.trimite = lambda cfg, catre, text, la=None: self.trimise.append((catre, text))

    def tearDown(self):
        self.t.cleanup()

    def test_grup_nou_cu_link_si_registru(self):
        fals = MetaFals({"PID/groups": (200, {"id": "G77"}), "G77/invite_link": (200, {"invite_link": "https://chat.whatsapp.com/abc"})})
        meta = G.Meta("TOK", deschide=fals)
        ok = G.executa_admin({"phone_id": "PID"}, {"de_la": "4477", "text": "grup nou Familie", "phone_id": "PID", "id": "m1"},
                             meta, self.t.name, self.trimite)
        self.assertTrue(ok)
        metoda, url, corp, auth = fals.cereri[0]
        self.assertEqual((metoda, corp["subject"], corp["messaging_product"]), ("POST", "Familie", "whatsapp"))
        self.assertEqual(auth, "Bearer TOK")
        self.assertTrue(url.startswith("https://graph.facebook.com/v23.0/PID/groups"))
        self.assertIn("https://chat.whatsapp.com/abc", self.trimise[0][1])
        self.assertEqual(G.citeste_registru(self.t.name)["G77"]["nume"], "Familie")
        # a doua oară: nu se creează un duplicat
        G.executa_admin({"phone_id": "PID"}, {"de_la": "4477", "text": "grup nou familie", "phone_id": "PID", "id": "m2"},
                        meta, self.t.name, self.trimite)
        self.assertEqual(sum(1 for c in fals.cereri if c[0] == "POST"), 1)
        self.assertIn("există deja", self.trimise[1][1])

    def test_fara_official_business_account_explica_motivul(self):
        fals = MetaFals({"PID/groups": (400, {"error": {"code": 100, "message": "Groups are only available to Official Business Accounts"}})})
        G.executa_admin({}, {"de_la": "4477", "text": "grup nou Prieteni", "phone_id": "PID"}, G.Meta("T", deschide=fals),
                        self.t.name, self.trimite)
        self.assertIn("Official Business Account", self.trimise[0][1])
        self.assertEqual(G.citeste_registru(self.t.name), {})

    def test_mesaj_obisnuit_nu_e_comanda(self):
        fals = MetaFals({})
        self.assertFalse(G.executa_admin({}, {"de_la": "1", "text": "ce faci?"}, G.Meta("T", deschide=fals), self.t.name, self.trimite))
        self.assertEqual(fals.cereri, [])


if __name__ == "__main__":
    unittest.main()
