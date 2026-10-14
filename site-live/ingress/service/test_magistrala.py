import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import magistrala  # noqa: E402
import magistrala_worker  # noqa: E402
from store import Store, Conflict  # noqa: E402


class RouteTests(unittest.TestCase):
    def test_chat_for_plain_question(self):
        r = magistrala.route("Ce vreme e mâine la Londra?")
        self.assertEqual((r["surface"], r["effort"]), ("chat", "low"))

    def test_codex_for_code(self):
        self.assertEqual(magistrala.route("Repară bug-ul din script-ul python")["surface"], "codex")

    def test_work_for_connectors(self):
        self.assertEqual(magistrala.route("Trimite un email și pune o întâlnire în calendar")["surface"], "work")

    def test_magentic_for_multi_domain(self):
        r = magistrala.route("Fă un proiect complet: cod pe server și raport în document")
        self.assertEqual(r["surface"], "magentic")
        self.assertGreaterEqual(r["difficulty"], 3)

    def test_deeper_task_gets_more_reasoning(self):
        self.assertEqual(magistrala.route("Analiză și strategie: de ce scad vânzările? " + "x " * 250)["effort"], "high")

    def test_empty_rejected(self):
        with self.assertRaises(ValueError):
            magistrala.route("  ")


class EscalationTests(unittest.TestCase):
    def test_effort_then_surface(self):
        plan = {"surface": "chat", "effort": "medium", "difficulty": 2, "reason": ""}
        plan = magistrala.escalate(plan, {"status": "insufficient"})
        self.assertEqual((plan["surface"], plan["effort"]), ("chat", "high"))
        plan = magistrala.escalate(plan, {"status": "insufficient"})
        self.assertEqual(plan["surface"], "work")
        plan = magistrala.escalate(plan, {"status": "failed"})
        self.assertEqual(plan["surface"], "magentic")

    def test_result_hints(self):
        base = {"surface": "chat", "effort": "low", "difficulty": 1, "reason": ""}
        self.assertEqual(magistrala.escalate(base, {"status": "needs_code"})["surface"], "codex")
        self.assertEqual(magistrala.escalate(base, {"status": "needs_tools"})["surface"], "work")

    def test_technical_failure_does_not_pay_more_on_same_channel(self):
        plan = {"surface": "codex", "effort": "low", "difficulty": 1, "reason": ""}
        nxt = magistrala.escalate(plan, {"status": "failed", "detail": "usage limit"})
        self.assertEqual((nxt["surface"], nxt["effort"]), ("magentic", "low"))
        nxt = magistrala.escalate({"surface": "chat", "effort": "low", "difficulty": 1, "reason": ""}, {"status": "unavailable"})
        self.assertEqual((nxt["surface"], nxt["effort"]), ("work", "low"))

    def test_insufficient_keeps_reached_effort_on_next_channel(self):
        nxt = magistrala.escalate({"surface": "chat", "effort": "high", "difficulty": 1, "reason": ""}, {"status": "insufficient"})
        self.assertEqual((nxt["surface"], nxt["effort"]), ("work", "high"))

    def test_top_stops(self):
        self.assertIsNone(magistrala.escalate({"surface": "magentic", "effort": "xhigh", "difficulty": 4, "reason": ""}, {"status": "failed"}))


class RunTests(unittest.TestCase):
    def test_escalates_until_answer_and_measures(self):
        calls, hops = [], []
        def chat(task_id, task, plan):
            calls.append(("chat", plan["effort"]))
            return {"status": "insufficient"}
        def work(task_id, task, plan):
            calls.append(("work", plan["effort"]))
            return {"status": "completed", "output": "Răspuns real"}
        result = magistrala.run("t1", "Salut, ce faci?", {"chat": chat, "work": work}, record=hops.append)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["output"], "Răspuns real")
        self.assertEqual(calls, [("chat", "low"), ("chat", "medium"), ("chat", "high"), ("work", "high")])
        self.assertEqual(len(hops), 4)
        self.assertTrue(all("duration_ms" in h for h in hops))

    def test_unavailable_and_crash_escalate_then_block(self):
        def boom(*_):
            raise RuntimeError("down")
        result = magistrala.run("t2", "Salut", {"chat": boom})
        self.assertEqual(result["status"], "blocked")
        self.assertEqual([h["status"] for h in result["hops"]][-1], "unavailable")

    def test_failure_detail_is_kept(self):
        result = magistrala.run("t4", "Salut", {"chat": lambda *_: {"status": "failed", "detail": "model inexistent"}})
        self.assertEqual(result["hops"][0]["detail"], "model inexistent")

    def test_empty_output_is_not_success(self):
        result = magistrala.run("t3", "Salut", {"chat": lambda *_: {"status": "completed", "output": " "}})
        self.assertEqual(result["status"], "blocked")


class StoreFlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "db.sqlite3",
                           {"adapter": "native-parent", "runtime_id": "test-runtime", "execution_surface": "codex"})

    def tearDown(self):
        self.tmp.cleanup()

    def intake(self, task_id, text):
        self.store.intake({"task_id": task_id, "task": text, "origin": "chat", "input_mode": "text"})

    def test_take_finish_completed(self):
        self.intake("web-0001", "Salut")
        task = self.store.magistrala_take("kelion-magistrala")
        self.assertEqual(task["state"], "running_magistrala")
        self.assertIsNone(self.store.magistrala_take("kelion-magistrala"))
        hops = [{"surface": "chat", "effort": "low", "status": "completed", "duration_ms": 5}]
        with self.assertRaises(Conflict):
            self.store.magistrala_finish("web-0001", "gresit", "completed", "x", hops)
        view = self.store.magistrala_finish("web-0001", task["take_token"], "completed", "Bună!", hops)
        self.assertEqual((view["state"], view["output"], view["result_retrieved"]), ("result_received", "Bună!", True))
        self.assertEqual(view["output_provenance"], "kelion_magistrala_backend_output")
        with self.assertRaises(Conflict):
            self.store.magistrala_finish("web-0001", task["take_token"], "completed", "din nou", hops)

    def test_blocked_has_reason(self):
        self.intake("web-0002", "Salut")
        task = self.store.magistrala_take("kelion-magistrala")
        view = self.store.magistrala_finish("web-0002", task["take_token"], "blocked", None,
                                            [{"surface": "magentic", "status": "unavailable"}])
        self.assertEqual(view["state"], "blocked")
        self.assertIn("magentic", view["block_reason"])

    def test_worker_end_to_end_with_command_backend(self):
        self.intake("web-0003", "Ce faci?")
        script = Path(self.tmp.name) / "chat.sh"
        script.write_text('#!/bin/sh\necho "[$KELION_SURFACE/$KELION_EFFORT/$KELION_MODEL] am primit: $(cat)"\n')
        script.chmod(script.stat().st_mode | stat.S_IEXEC)
        backends = {"chat": magistrala_worker.command_backend({"command": [str(script)], "models": {"low": "gpt-6-astra"}})}
        store = self.store

        class LocalIngress:
            def post(self, path, data, timeout=40):
                if path.endswith("/take"):
                    return {"task": store.magistrala_take(data["worker_id"])}
                if path.endswith("/progress"):
                    store.magistrala_progress(**data)
                    seen.append(store.get(data["task_id"])["progress"][-1]["status"])
                    return {}
                return store.magistrala_finish(**data)
        seen = []
        events = Path(self.tmp.name) / "events.jsonl"
        result = magistrala_worker.serve_once(LocalIngress(), backends, "kelion-magistrala", str(events), wait=0)
        self.assertEqual(result["status"], "completed")
        view = store.get("web-0003")
        self.assertEqual(view["state"], "result_received")
        self.assertIn("[chat/low/gpt-6-astra] am primit: Ce faci?", view["output"])
        lines = [json.loads(l) for l in events.read_text().splitlines()]
        self.assertEqual([l["event"] for l in lines], ["task_taken", "hop", "task_finished"])
        self.assertEqual(seen, ["running", "completed"])  # monitorul live vede pasul înainte și după

    def test_progress_requires_running_and_token(self):
        self.intake("web-0004", "Salut")
        with self.assertRaises(Conflict):
            self.store.magistrala_progress("web-0004", "x", {"status": "running"})
        task = self.store.magistrala_take("kelion-magistrala")
        with self.assertRaises(Conflict):
            self.store.magistrala_progress("web-0004", "gresit", {"status": "running"})
        self.store.magistrala_progress("web-0004", task["take_token"], {"surface": "chat", "status": "running"})
        self.assertEqual(self.store.get("web-0004")["progress"][0]["surface"], "chat")


class WebSearchTests(unittest.TestCase):
    def test_web_search_flag_reaches_backend(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "b.sh"
            script.write_text('#!/bin/sh\ncat >/dev/null; echo "search=${KELION_WEB_SEARCH:-0}"\n')
            script.chmod(script.stat().st_mode | stat.S_IEXEC)
            on = magistrala_worker.command_backend({"command": [str(script)], "web_search": True})
            off = magistrala_worker.command_backend({"command": [str(script)]})
            self.assertEqual(on("t", "x", {"surface": "chat", "effort": "low"})["output"], "search=1")
            self.assertEqual(off("t", "x", {"surface": "chat", "effort": "low"})["output"], "search=0")


class ReasoningOverrideTests(unittest.TestCase):
    def test_reasoning_override_reaches_backend(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "b.sh"
            script.write_text('#!/bin/sh\ncat >/dev/null; echo "effort=$KELION_EFFORT"\n')
            script.chmod(script.stat().st_mode | stat.S_IEXEC)
            fast = magistrala_worker.command_backend({"command": [str(script)], "reasoning": "minimal"})
            normal = magistrala_worker.command_backend({"command": [str(script)]})
            self.assertEqual(fast("t", "x", {"surface": "chat", "effort": "high"})["output"], "effort=minimal")
            self.assertEqual(normal("t", "x", {"surface": "chat", "effort": "high"})["output"], "effort=high")

class DotsProfileTests(unittest.TestCase):
    from dots_profiles import Profiles
    profiles = Profiles.load()

    def test_registry_has_22_profiles_all_addressable(self):
        self.assertEqual(len(self.profiles), 22)
        for name in self.profiles.roles:
            self.assertEqual(self.profiles.pick("@" + name.removeprefix("dots_") + " salut")[0], name)

    def test_keyword_and_explicit_routing(self):
        plan = magistrala.route("Repară bug-ul din pagina de login", self.profiles)
        self.assertEqual((plan["profile"], plan["surface"]), ("dots_reparator", "codex"))
        self.assertEqual(magistrala.route("@ux propune un ecran nou", self.profiles)["profile"], "dots_ux")
        self.assertNotIn("profile", magistrala.route("Salut, ce faci?", self.profiles))
        self.assertNotIn("profile", magistrala.route("Ce mașină de lux îmi recomanzi?", self.profiles))

    def test_backend_receives_profile_instructions_and_hop_records_it(self):
        seen = {}
        def codex(task_id, task, plan):
            seen["task"] = task
            return {"status": "completed", "output": "ok"}
        result = magistrala.run("t9", "@reparator repară scriptul", {"codex": codex}, profiles=self.profiles)
        self.assertEqual(result["status"], "completed")
        self.assertIn("[Profil DOTS: 🔧 DOTS — Programator și reparator de cod]", seen["task"])
        self.assertIn("phase=work", seen["task"])
        self.assertTrue(seen["task"].rstrip().endswith("repară scriptul"))
        self.assertEqual(result["hops"][0]["profile"], "dots_reparator")


class CodexHomeTests(unittest.TestCase):
    def test_codex_home_passed_to_backend(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "b.sh"
            script.write_text('#!/bin/sh\ncat >/dev/null; echo "home=$CODEX_HOME"\n')
            script.chmod(script.stat().st_mode | stat.S_IEXEC)
            call = magistrala_worker.command_backend({"command": [str(script)], "codex_home": "/srv/codex-login"})
            self.assertEqual(call("t", "x", {"surface": "chat", "effort": "low"})["output"], "home=/srv/codex-login")


if __name__ == "__main__":
    unittest.main()
