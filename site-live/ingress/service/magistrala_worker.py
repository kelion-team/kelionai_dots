"""Worker-ul magistralei Kelion.

Preia fiecare cerere nouă de pe kelionai.app (long-poll pe ingress, local), o trece prin
magistrală (rutare + escaladare) și scrie rezultatul înapoi. Fiecare pas e măsurat în jurnal.

Backend-urile sunt comenzi configurate în /etc/kelion-magistrala/config.json (vezi
config.example.json). O comandă primește cererea pe stdin, planul în variabilele
KELION_SURFACE / KELION_EFFORT / KELION_MODEL / KELION_TASK_ID și răspunde pe stdout cu JSON
{"status": "completed"|"needs_code"|"needs_tools"|"insufficient"|"failed", "output": "..."}
sau cu text simplu (considerat răspuns complet). O suprafață fără comandă e "unavailable"
și magistrala escaladează la următoarea.
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import magistrala  # noqa: E402
from dots_profiles import Profiles  # noqa: E402


def command_backend(spec):
    command = spec.get("command")
    if not isinstance(command, list) or not command or not all(isinstance(c, str) for c in command):
        raise ValueError("Backend command must be a non-empty argv list")
    timeout = int(spec.get("timeout", 600))
    models = spec.get("models", {})

    def call(task_id, task, plan):
        env = {k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "LANG", "CODEX_HOME")}
        # "reasoning" din config (ex. "minimal" la chat) suprascrie efortul trimis la Codex, pentru răspuns rapid.
        env.update(KELION_SURFACE=plan["surface"], KELION_EFFORT=spec.get("reasoning") or plan["effort"], KELION_TASK_ID=task_id,
                   KELION_MODEL=models.get(plan["effort"], spec.get("model", "")))
        if spec.get("web_search"):
            env["KELION_WEB_SEARCH"] = "1"  # căutare pe internet permisă pentru această suprafață
        if spec.get("codex_home"):
            # Login-ul Codex e per director; folosim exact directorul în care s-a făcut login-ul.
            env["CODEX_HOME"] = spec["codex_home"]
        done = subprocess.run(command, input=task, capture_output=True, text=True, timeout=timeout, env=env)
        out = done.stdout.strip()
        if done.returncode != 0:
            return {"status": "failed", "detail": (done.stderr or out)[-300:]}
        try:
            result = json.loads(out)
            if isinstance(result, dict) and "status" in result:
                return result
        except json.JSONDecodeError:
            pass
        return {"status": "completed" if out else "insufficient", "output": out}
    return call


def load_backends(config_path):
    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    backends = {}
    for surface, spec in (config.get("surfaces") or {}).items():
        if surface in magistrala.SURFACES and spec.get("enabled", True) and spec.get("command"):
            backends[surface] = command_backend(spec)
    return backends


class Ingress:
    def __init__(self, base, token, opener=urllib.request.urlopen):
        self.base, self.token, self.opener = base.rstrip("/"), token, opener

    def post(self, path, data, timeout=40):
        request = urllib.request.Request(self.base + path, data=json.dumps(data).encode(), method="POST",
                                         headers={"Authorization": "Bearer " + self.token,
                                                  "Content-Type": "application/json"})
        with self.opener(request, timeout=timeout) as response:
            return json.loads(response.read())


def log_event(path, entry):
    line = json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **entry}, ensure_ascii=False)
    print("[magistrala] " + line, flush=True)
    if path:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")


def serve_once(ingress, backends, worker_id, events=None, wait=25, profiles=None):
    task = ingress.post("/v1/worker/magistrala/take", {"worker_id": worker_id, "wait_seconds": wait})["task"]
    if not task:
        return None
    text = task["payload"]["request"]["task"]
    log_event(events, {"event": "task_taken", "task_id": task["task_id"], "route": magistrala.route(text, profiles)})
    def on_progress(hop):
        try:  # monitorul live: pasul apare imediat pe kelionai.app
            ingress.post("/v1/worker/magistrala/progress", {"task_id": task["task_id"], "take_token": task["take_token"],
                                                            "event": {k: hop.get(k) for k in ("surface", "effort", "reason", "status", "duration_ms", "detail", "profile") if hop.get(k) is not None}})
        except Exception as error:  # monitorul nu oprește execuția
            log_event(events, {"event": "progress_error", "detail": str(error)[:200]})
    def on_hop(hop):
        log_event(events, {"event": "hop", **hop})
        on_progress(hop)
    result = magistrala.run(task["task_id"], text, backends, record=on_hop, progress=on_progress, profiles=profiles)
    ingress.post("/v1/worker/magistrala/finish", {"task_id": task["task_id"], "take_token": task["take_token"],
                                                   "status": result["status"], "output": result["output"],
                                                   "hops": result["hops"]})
    log_event(events, {"event": "task_finished", "task_id": task["task_id"], "status": result["status"],
                       "hops": len(result["hops"])})
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="/etc/kelion-magistrala/config.json")
    parser.add_argument("--ingress", default="http://127.0.0.1:8765")
    parser.add_argument("--worker-id", default="kelion-magistrala")
    parser.add_argument("--events", default="/var/lib/kelion-magistrala/events.jsonl")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args(argv)
    token = os.environ.get("KELION_WORKER_TOKEN", "")
    if len(token) < 32:
        raise SystemExit("KELION_WORKER_TOKEN lipsește din mediul serviciului")
    Path(args.events).parent.mkdir(parents=True, exist_ok=True)
    backends = load_backends(args.config)
    profiles = Profiles.load(json.loads(Path(args.config).read_text(encoding="utf-8")).get("profiles_path"))
    log_event(args.events, {"event": "worker_start", "surfaces": sorted(backends), "dots_profiles": len(profiles)})
    ingress = Ingress(args.ingress, token)
    while True:
        try:
            serve_once(ingress, backends, args.worker_id, args.events, profiles=profiles)
        except Exception as error:  # rețea/ingress indisponibil: nu se pierde nicio cerere, se reîncearcă
            log_event(args.events, {"event": "worker_error", "detail": str(error)[:300]})
            time.sleep(5)
        if args.once:
            return


if __name__ == "__main__":
    main()
