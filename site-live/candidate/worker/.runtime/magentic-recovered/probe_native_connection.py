"""Read-only native connection probe; never starts an agent or inference turn."""
import hashlib
import json
import os
import re
from pathlib import Path
import selectors
import subprocess
import time

ROOT = Path(__file__).resolve().parent
STATE = ROOT / "state"
STATE.mkdir(mode=0o700, exist_ok=True)
ARGV = ["codex", "app-server", "--stdio", "--strict-config", "-c",
        f'sqlite_home="{STATE}"']
started = time.monotonic()
process = subprocess.Popen(ARGV, cwd=ROOT, stdin=subprocess.PIPE,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
selector = selectors.DefaultSelector()
selector.register(process.stdout, selectors.EVENT_READ, "stdout")
selector.register(process.stderr, selectors.EVENT_READ, "stderr")
buffers = {"stdout": b"", "stderr": b""}
records = []
notification_methods = set()


def send(value):
    process.stdin.write((json.dumps(value) + "\n").encode())
    process.stdin.flush()


def request(method, params, identifier, timeout=8):
    send({"id": identifier, "method": method, "params": params})
    begin = time.monotonic()
    deadline = begin + timeout
    while time.monotonic() < deadline:
        for key, _ in selector.select(min(0.3, deadline - time.monotonic())):
            data = os.read(key.fileobj.fileno(), 65536)
            if not data:
                selector.unregister(key.fileobj)
                continue
            stream = key.data
            buffers[stream] += data
            if stream == "stderr":
                buffers[stream] = buffers[stream][-65536:]
                continue
            while b"\n" in buffers[stream]:
                line, buffers[stream] = buffers[stream].split(b"\n", 1)
                try:
                    value = json.loads(line)
                except (ValueError, UnicodeDecodeError):
                    continue
                if value.get("id") == identifier:
                    records.append({"method": method, "params": params,
                                    "seconds": round(time.monotonic() - begin, 3),
                                    "response": value})
                    return value
                if "method" in value:
                    notification_methods.add(value["method"])
        if process.poll() is not None:
            break
    failure = {"error": {"code": "probe_timeout_or_process_exit"}}
    records.append({"method": method, "params": params,
                    "seconds": round(time.monotonic() - begin, 3),
                    "response": failure})
    return failure


summary = {"new_agent_started": False, "inference_performed": False,
           "credentials_changed": False, "persistent_configuration_changed": False,
           "process_configuration_override": {"sqlite_home": str(STATE)}}
try:
    initial = request("initialize", {
        "clientInfo": {"name": "kelion_native_connection_readonly",
                       "title": "Kelion native connection probe", "version": "0.1"},
        "capabilities": {"experimentalApi": True}}, 1)
    summary["initialized"] = "result" in initial
    if summary["initialized"]:
        send({"method": "initialized", "params": {}})
        account = request("account/read", {"refreshToken": False}, 2)
        account_data = account.get("result", {}).get("account") or {}
        summary["account_type"] = account_data.get("type")
        summary["account_plan_type"] = account_data.get("planType")
        # Never retain email, account identifiers, or credential material.
        records[-1]["response"] = {"result": {
            "account_type": summary["account_type"],
            "account_plan_type": summary["account_plan_type"]},
            "error_code": account.get("error", {}).get("code")}
        apps = request("app/list", {"limit": 50, "forceRefetch": False}, 3, 12)
        items = apps.get("result", {}).get("data", [])
        summary["apps"] = [{"id": x.get("id"), "name": x.get("name"),
                            "isAccessible": x.get("isAccessible"),
                            "isEnabled": x.get("isEnabled")} for x in items]
        summary["app_next_cursor_present"] = bool(apps.get("result", {}).get("nextCursor"))
        summary["app_error_code"] = apps.get("error", {}).get("code")
        records[-1]["response"] = {"result": {"data": summary["apps"],
             "nextCursorPresent": summary["app_next_cursor_present"]},
             "error_code": summary["app_error_code"]}
        installed = request("app/installed", {"forceRefresh": False}, 5, 12)
        installed_data = installed.get("result", {})
        summary["installed_apps"] = [{"id": x.get("id"), "name": x.get("name"),
            "isAccessible": x.get("isAccessible"), "isEnabled": x.get("isEnabled")}
            for x in installed_data.get("data", [])]
        summary["installed_app_error_code"] = installed.get("error", {}).get("code")
        records[-1]["response"] = {"result": {"data": summary["installed_apps"]},
            "error_code": summary["installed_app_error_code"]}
        threads = request("thread/list", {"limit": 50, "searchTerm": "Kelion",
            "useStateDbOnly": True, "sourceKinds": ["cli", "exec", "appServer",
            "vscode", "subAgent", "subAgentReview", "subAgentCompact",
            "subAgentThreadSpawn", "subAgentOther", "unknown"]}, 4)
        summary["existing_kelion_threads"] = [{"id": x.get("id"),
            "name": x.get("name"), "status": x.get("status")}
            for x in threads.get("result", {}).get("data", [])]
        summary["thread_error_code"] = threads.get("error", {}).get("code")
        records[-1]["response"] = {"result": {"data": summary["existing_kelion_threads"]},
                                   "error_code": summary["thread_error_code"]}
finally:
    process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=3)
    selector.close()
    summary["elapsed_seconds"] = round(time.monotonic() - started, 3)
    summary["process_exit_code"] = process.returncode
    stderr_text = buffers["stderr"].decode("utf-8", errors="replace")[-2500:]
    stderr_text = re.sub(r'https?://\S+', '[URL withheld]', stderr_text)
    stderr_text = re.sub(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', '[email withheld]', stderr_text)
    stderr_text = re.sub(r'(?i)(bearer\s+|(?:access_token|refresh_token|api_key)\s*[=:]\s*)[^\s,]+', r'\1[credential withheld]', stderr_text)
    stderr_text = re.sub(r'sk-[A-Za-z0-9_-]+', '[credential withheld]', stderr_text)
    summary["sanitized_startup_diagnostic"] = stderr_text
    report = {"argv": ARGV, "cwd": str(ROOT), "outer_timeout_seconds": 45,
              "read_only_rpc_records": records, "summary": summary,
              "notification_methods": sorted(notification_methods)}
    target = ROOT / "native-connection-readonly-evidence.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"summary": summary, "evidence_path": str(target),
                      "sha256": hashlib.sha256(target.read_bytes()).hexdigest()},
                     ensure_ascii=False))
