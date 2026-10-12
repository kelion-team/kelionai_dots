"""Offline acceptance checks; no external calls, subscriptions or app mutations."""
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("kelion_route", HERE / "scripts" / "route.py")
router = importlib.util.module_from_spec(spec)
spec.loader.exec_module(router)


def fixture():
    def model(name, tier, cost, surface="work", billing="included", enabled=True, verified=True,
              levels=None):
        return dict(id=name, capability_tier=tier, cost_rank=cost, surface=surface,
                    billing_mode=billing, enabled=enabled, verified=verified,
                    reasoning_levels=levels or ["low", "medium", "high"])
    return dict(schema_version=1,
                models=[model("eco", 1, 1), model("standard", 2, 3), model("advanced", 3, 8),
                        model("max", 4, 15), model("expensive-but-low", 4, 100, billing="metered"),
                        model("internal-economy", 1, 1, "connector:agent_app")],
                connectors=[dict(id="github", enabled=True, authenticated=True, attached_to_agent=True,
                                 model_control="host"),
                            dict(id="agent_app", enabled=True, authenticated=True, attached_to_agent=True,
                                 model_control="internal", model_switch_verified=True),
                            dict(id="unknown_auth", enabled=True, authenticated=None, attached_to_agent=False,
                                 model_control="unknown")])


class GuardianTests(unittest.TestCase):
    def setUp(self):
        self.catalog = fixture()

    def ask(self, task="Rezuma textul", **kw):
        return router.route(dict(task=task, **kw), self.catalog)

    def test_economic_simple(self):
        response = self.ask()
        self.assertEqual(response["policy_tier"], 1)
        self.assertEqual(response["host_model"]["id"], "eco")
        self.assertFalse(response["settings_changed"])

    def test_summary_report_stays_economic(self):
        d = self.ask("Rezumă raportul de test")
        self.assertEqual(d["policy_tier"], 1)
        self.assertEqual(d["host_model"]["id"], "eco")

    def test_programming_standard(self):
        self.assertEqual(self.ask("Scrie cod si teste unitare")["host_model"]["id"], "standard")

    def test_advanced_architecture(self):
        self.assertEqual(self.ask("Analiza arhitectura pentru o migrare complexa")["host_model"]["id"], "advanced")

    def test_critical_explicit_security(self):
        d = self.ask("Revizie", risk_flags=["security"])
        self.assertEqual(d["host_model"]["id"], "max")
        self.assertTrue(d["requires_action_approval"])

    def test_critical_language(self):
        self.assertEqual(self.ask("Incident de securitate critica")["policy_tier"], 4)

    def test_escalation_never_replays_work(self):
        d = self.ask("Rezuma textul", previous_attempt={"tier": 1, "result": "failed", "failure_verified": True})
        self.assertEqual(d["policy_tier"], 2)
        self.assertTrue(d["auto_escalated"])
        self.assertTrue(d["reuse_successful_work"])

    def test_no_escalation_on_unverified_failure(self):
        d = self.ask("Rezuma textul", previous_attempt={"tier": 1, "result": "failed", "failure_verified": False})
        self.assertEqual(d["policy_tier"], 1)
        self.assertFalse(d["auto_escalated"])

    def test_already_critical_cannot_escalate(self):
        d = self.ask("Test", risk_flags=["safety"], previous_attempt={"tier": 4, "result": "failed", "failure_verified": True})
        self.assertEqual(d["policy_tier"], 4)
        self.assertFalse(d["auto_escalated"])

    def test_no_fake_entitlement(self):
        for m in self.catalog["models"]:
            m["verified"] = False
        d = self.ask()
        self.assertEqual(d["status"], "blocked_no_verified_included_model")
        self.assertIsNone(d["host_model"])

    def test_connectors_need_target_agent_proof(self):
        d = self.ask(connector="unknown_auth")
        self.assertEqual(d["status"], "blocked_connector_not_usable")
        self.assertFalse(d["connector_call_performed"])

    def test_connector_host_only(self):
        d = self.ask(connector="github")
        self.assertEqual(d["status"], "plan_only")
        self.assertEqual(d["connector_status"], "host_model_only")
        self.assertIsNone(d["connector_model"])

    def test_internal_model_require_verified_switch(self):
        d = self.ask(connector="agent_app")
        self.assertEqual(d["connector_model"]["id"], "internal-economy")
        self.catalog["connectors"][1]["model_switch_verified"] = False
        d = self.ask(connector="agent_app")
        self.assertIsNone(d["connector_model"])
        self.assertEqual(d["status"], "blocked_connector_internal_model_selection")

    def test_never_purchases_credits(self):
        d = self.ask("Verifica", action="purchase")
        self.assertTrue(d["requires_action_approval"])
        self.assertFalse(d["requires_paid_credit_purchase"])
        self.assertFalse(d["settings_changed"])

    def test_meters_excluded(self):
        self.catalog["models"] = [m for m in self.catalog["models"] if m["billing_mode"] == "metered"]
        d = self.ask("Incident de securitate critica")
        self.assertEqual(d["status"], "blocked_no_verified_included_model")

    def test_missing_critical_model_blocks_not_downgrade(self):
        self.catalog["models"] = [m for m in self.catalog["models"] if m["capability_tier"] <= 3]
        d = self.ask("Evaluare", risk_flags=["production"])
        self.assertEqual(d["status"], "blocked_no_verified_included_model")

    def test_real_cost_and_savings_never_invented(self):
        d = self.ask()
        self.assertIsNone(d["actual_credit_cost"])
        self.assertIsNone(d["measured_savings"])

    def test_invalid_manifest_strict_boolean(self):
        self.catalog["models"][0]["verified"] = 1
        with self.assertRaises(ValueError):
            self.ask()

    def test_risk_flags_validate(self):
        with self.assertRaises(ValueError):
            self.ask(risk_flags=["not-real"])

    def test_unknown_connector_no_guessing(self):
        d = self.ask(connector="unlisted")
        self.assertEqual(d["status"], "blocked_connector_not_usable")

    def test_command_line_reproducibility(self):
        with tempfile.TemporaryDirectory() as td:
            manifest = Path(td, "catalog.json")
            manifest.write_text(json.dumps(self.catalog), encoding="utf-8")
            cmd = [sys.executable, str(HERE / "scripts" / "route.py"), "--manifest", str(manifest)]
            p = subprocess.run(cmd, input='{"task":"Rezuma in romana","surface":"work"}',
                               capture_output=True, text=True, timeout=10)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertEqual(json.loads(p.stdout)["policy_tier"], 1)


if __name__ == "__main__":
    unittest.main()
