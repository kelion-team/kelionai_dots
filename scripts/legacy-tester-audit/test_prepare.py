import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

import prepare

ROOT = Path(__file__).parent
BASELINE = (ROOT / "fixtures/tester-structure.py.txt").read_bytes()


def load_candidate():
    module = types.ModuleType("tester_candidate")
    fake_playwright = types.ModuleType("playwright.sync_api")
    fake_playwright.sync_playwright = Mock()
    with patch.dict(sys.modules, {"playwright": types.ModuleType("playwright"),
                                 "playwright.sync_api": fake_playwright}), patch.dict(os.environ):
        exec(compile(prepare.transform(BASELINE), "candidate.py", "exec"), module.__dict__)
    return module


def page(*, good=False):
    return {
        "pagina": "/app/", "latime": 1280, "status_http": 200,
        "date_afisate_s": 1.17, "reimprospatare_s": 4.0,
        "erori_consola": [] if good else ["Failed to load resource: the server responded with a status of 404 (Not Found)"],
        "erori_http": [] if good else [{"url": "/app/control-api/state", "status": 404}],
        "cereri_esuate": [], "ok": good,
    }


class RegressionTests(unittest.TestCase):
    def setUp(self):
        pinned = patch.object(prepare, "EXPECTED_SHA256", hashlib.sha256(BASELINE).hexdigest())
        pinned.start()
        self.addCleanup(pinned.stop)
        self.mod = load_candidate()

    def run_main(self, pages, repair=True):
        browser = Mock()
        playwright = Mock()
        playwright.chromium.launch.return_value = browser
        context = Mock()
        context.__enter__ = Mock(return_value=playwright)
        context.__exit__ = Mock(return_value=False)
        server = Mock(server_address=("127.0.0.1", 9999))
        queue = types.SimpleNamespace(C=Mock())
        queue.C.adauga.return_value = {"id": "offline-test-only"}
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"KELION_TESTER_REPARA": str(int(repair))}), \
             patch.dict(sys.modules, {"coada": queue}), patch.object(sys, "path", list(sys.path)), \
             patch.object(self.mod, "OUT", str(Path(tmp) / "result.json")), \
             patch.object(self.mod, "server_local", return_value=server), \
             patch.object(self.mod, "sync_playwright", return_value=context), \
             patch.object(self.mod, "testeaza", side_effect=copy.deepcopy(pages)), \
             patch("urllib.request.urlopen", side_effect=AssertionError("network forbidden")), \
             patch("socket.socket", side_effect=AssertionError("network forbidden")):
            result = self.mod.main(["/app/"] * (len(pages) // 2))
            persisted = json.loads(Path(self.mod.OUT).read_text())
        self.assertEqual(result, persisted)
        server.shutdown.assert_called_once()
        return result, queue.C

    def test_synthetic_fixture_and_candidate_compile(self):
        self.assertIn(b"Synthetic structural fixture", BASELINE)
        self.assertNotIn(b"class OAuthVerifier", BASELINE)
        compile(prepare.transform(BASELINE), "candidate", "exec")

    def test_source_drift_rejected(self):
        for data in (BASELINE + b"\n", BASELINE.replace(b"5.0", b"9.0"), b""):
            with self.subTest(length=len(data)), self.assertRaisesRegex(ValueError, "source drift"):
                prepare.transform(data)

    def test_ambiguous_anchor_rejected(self):
        with self.assertRaises(ValueError):
            prepare.replace_once("one one", "one", "two")

    def test_known_route_gap_is_not_application_proof(self):
        self.assertTrue(self.mod.coverage_only(page()))

    def test_other_http_errors_are_not_filtered(self):
        for error in ({"url": "/app/api/sistem", "status": 404},
                      {"url": "/app/control-api/state", "status": 500},
                      {"url": "/app/control-api/state", "status": 401}):
            current = page()
            current["erori_http"].append(error)
            with self.subTest(error=error):
                self.assertFalse(self.mod.coverage_only(current))

    def test_javascript_errors_are_not_filtered(self):
        current = page()
        current["erori_consola"].append("ReferenceError: K is not defined")
        self.assertFalse(self.mod.coverage_only(current))

    def test_navigation_data_refresh_and_request_failures_are_not_filtered(self):
        changes = [("status_http", 500), ("date_afisate_s", None),
                   ("prea_rar", "refresh >5 s"), ("eroare", "navigation failed"),
                   ("cereri_esuate", ["/app/api/sistem net::ERR_FAILED"])]
        for key, value in changes:
            current = page()
            current[key] = value
            with self.subTest(key=key):
                self.assertFalse(self.mod.coverage_only(current))

    def test_latency_threshold_is_preserved(self):
        for latency, expected in ((3.9, True), (4.27, True), (5.0, True), (5.01, False), (None, False)):
            current = page()
            current.update(eveniment={"id": "OFFLINE"}, eveniment_ecran_s=latency)
            with self.subTest(latency=latency):
                self.assertEqual(expected, self.mod.coverage_only(current))

    def test_no_errors_is_not_classified_as_route_gap(self):
        self.assertFalse(self.mod.coverage_only(page(good=True)))

    def test_http_url_and_status_visible_in_defect(self):
        description = self.mod.describe_defect(page())
        self.assertIn("404 /app/control-api/state", description)
        self.assertIn("endpointul LIVE nu a fost masurat", description)

    def test_fourteen_coverage_only_failures_preserved_without_repair_loop(self):
        result, queue = self.run_main([page() for _ in range(14)])
        self.assertFalse(result["ok"])
        self.assertFalse(result["legacy_ok"])
        self.assertFalse(result["live_acceptance"])
        self.assertEqual(14, len(result["pagini"]))
        self.assertEqual(14, sum(not p["ok"] for p in result["pagini"]))
        self.assertTrue(all(p["erori_http"][0]["status"] == 404 for p in result["pagini"]))
        self.assertTrue(result["defecte_legacy"])
        self.assertEqual([], result["defecte_reparabile"])
        queue.adauga.assert_not_called()
        queue.porneste_supraveghetor.assert_not_called()
        self.assertNotIn("reparatie", result)

    def test_all_legacy_green_never_sets_live_acceptance(self):
        result, queue = self.run_main([page(good=True), page(good=True)])
        self.assertTrue(result["legacy_ok"])
        self.assertFalse(result["ok"])
        self.assertFalse(result["live_acceptance"])
        self.assertEqual("legacy-static-local", result["surface"])
        self.assertEqual(2, len(result["coverage_gaps"]))
        queue.adauga.assert_not_called()

    def test_real_defect_still_queued_with_truthful_scope(self):
        current = page()
        current["erori_consola"].append("ReferenceError: K is not defined")
        result, queue = self.run_main([current, page()])
        queue.adauga.assert_called_once()
        queue.porneste_supraveghetor.assert_called_once()
        prompt = queue.adauga.call_args.args[1]
        self.assertIn("NU acceptanta LIVE", prompt)
        self.assertIn("Nu modifica LIVE", prompt)
        self.assertNotIn("a gasit pe LIVE", prompt)
        self.assertEqual(1, len(result["defecte_reparabile"]))

    def test_existing_repair_off_switch_preserved(self):
        current = page()
        current["eroare"] = "navigation failed"
        result, queue = self.run_main([current, current], repair=False)
        self.assertTrue(result["defecte_reparabile"])
        queue.adauga.assert_not_called()

    def test_summary_does_not_claim_live_or_hide_404(self):
        result, _ = self.run_main([page(), page()])
        summary = self.mod.rezumat(result)
        self.assertIn("LEGACY LOCAL", summary)
        self.assertIn("Acceptanta LIVE: NEVERIFICATA", summary)
        self.assertIn("/app/control-api/state", summary)
        self.assertIn("404", summary)
        self.assertIn("LIPSA ACOPERIRE ADAPTOR", summary)
        self.assertNotIn("TOATE OK", summary)

    def test_prepare_outputs_only_new_patch_and_leaves_input_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.py"
            source.write_bytes(BASELINE)
            output = Path(tmp) / "candidate.patch"
            prepare.main(["--source", str(source), "--output", str(output)])
            self.assertEqual(BASELINE, source.read_bytes())
            self.assertTrue(output.read_text().startswith("--- /opt/kelion-brain/tester-ui.py\n"))
            with self.assertRaises(SystemExit):
                prepare.main(["--source", str(source), "--output", str(output)])

    def test_prepare_refuses_non_patch_output(self):
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(SystemExit):
            prepare.main(["--source", str(ROOT / "fixtures/tester-structure.py.txt"),
                          "--output", str(Path(tmp) / "tester-ui.py")])

    def test_prepare_drift_writes_no_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "drift.py"
            source.write_bytes(BASELINE + b"\n")
            output = Path(tmp) / "candidate.patch"
            with self.assertRaises(ValueError):
                prepare.main(["--source", str(source), "--output", str(output)])
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
