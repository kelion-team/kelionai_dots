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
                return store.magistrala_finish(**data)
        events = Path(self.tmp.name) / "events.jsonl"
        result = magistrala_worker.serve_once(LocalIngress(), backends, "kelion-magistrala", str(events), wait=0)
        self.assertEqual(result["status"], "completed")
        view = store.get("web-0003")
        self.assertEqual(view["state"], "result_received")
        self.assertIn("[chat/low/gpt-6-astra] am primit: Ce faci?", view["output"])
        lines = [json.loads(l) for l in events.read_text().splitlines()]
        self.assertEqual([l["event"] for l in lines], ["task_taken", "hop", "task_finished"])


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
