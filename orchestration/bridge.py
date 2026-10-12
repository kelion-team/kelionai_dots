#!/usr/bin/env python3
"""Workspace-Agent trigger transport and read-only status check.

This does not install agents or retrieve their answer content.
Only `trigger --execute` causes an agent run. No polling loops, no secrets on disk.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import sys
import urllib.error
import urllib.request

BASE = "https://api.chatgpt.com/v1/workspace_agents"
AGENT_ID = re.compile(r"^agt_[A-Za-z0-9_-]+$")
CHANNEL_ID = re.compile(r"^agtch_[A-Za-z0-9_-]+$")
RUN_ID = re.compile(r"^apirun_[A-Za-z0-9_-]+$")
SURFACES = ("chat", "work", "codex")
RUN_STATUSES = {"queued", "in_progress", "suspended", "completed", "failed"}


def utcnow():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def parse_json(filepath):
    return json.loads(pathlib.Path(filepath).read_text(encoding="utf-8"))


def save_json(filepath, data):
    p = pathlib.Path(filepath)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def _match(pattern, value, label):
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise ValueError("Invalid " + label)
    return value


def prepare(task_id, surface, agent_id, channel_id, input_text, issue_url):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{3,127}", task_id):
        raise ValueError("Invalid task_id")
    if surface not in SURFACES:
        raise ValueError("Invalid surface")
    _match(AGENT_ID, agent_id, "agent_id")
    _match(CHANNEL_ID, channel_id, "channel_id")
    if not isinstance(input_text, str) or not input_text.strip() or len(input_text) > 100000:
        raise ValueError("Invalid input")
    if issue_url and not issue_url.startswith("https://github.com/"):
        raise ValueError("Issue must be a GitHub URL")
    return {
        "schema_version": 1,
        "task_id": task_id,
        "origin": surface,
        "agent_id": agent_id,
        "api_trigger_id": channel_id,
        "input": input_text,
        "issue_url": issue_url or None,
        "created_at_utc": utcnow(),
        "status": "prepared_not_dispatched",
    }


def api_request(channel_id, token, method, suffix="/trigger", body=None, key=None, opener=None):
    _match(CHANNEL_ID, channel_id, "api_trigger_id")
    if not token or not isinstance(token, str):
        raise ValueError("Missing WORKSPACE_AGENT_ACCESS_TOKEN")
    if not suffix.startswith("/") or ".." in suffix:
        raise ValueError("Invalid API path")
    headers = {"Authorization": "Bearer " + token, "Accept": "application/json",
               "OpenAI-Beta": "workspace_agent_runs=v1"}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
    if key:
        headers["Idempotency-Key"] = key
    request = urllib.request.Request(BASE + "/" + channel_id + suffix, data=data,
                                     headers=headers, method=method)
    open_fn = opener if opener is not None else urllib.request.urlopen
    with open_fn(request, timeout=20) as resp:
        status = resp.status
        raw = resp.read()
    payload = json.loads(raw.decode("utf-8")) if raw else {}
    return status, payload


def trigger(envelope, token, opener=None):
    if envelope.get("status") != "prepared_not_dispatched":
        raise ValueError("Only prepared tasks may be triggered")
    task_id = envelope["task_id"]
    channel_id = _match(CHANNEL_ID, envelope["api_trigger_id"], "api_trigger_id")
    _match(AGENT_ID, envelope["agent_id"], "agent_id")
    event_key = hashlib.sha256((channel_id + ":" + task_id).encode()).hexdigest()
    code, data = api_request(channel_id, token, "POST", body={
        "conversation_key": task_id,
        "input": envelope["input"] + ("\n\nTask ledger: " + envelope["issue_url"] if envelope.get("issue_url") else "")
    }, key=event_key, opener=opener)
    if code != 202:
        raise RuntimeError("API did not confirm acceptance (HTTP %s)" % code)
    url = data.get("conversation_url")
    run = data.get("agent_trigger_run_id")
    # API 202 may have an empty body; response links are optional.
    if url is not None and (not isinstance(url, str) or not url.startswith("https://chatgpt.com/")):
        raise RuntimeError("Invalid optional ChatGPT conversation URL")
    if run is not None:
        _match(RUN_ID, run, "run_id")
    return {"schema_version": 1, "task_id": task_id, "origin": envelope["origin"],
            "agent_id": envelope["agent_id"], "api_trigger_id": channel_id,
            "issue_url": envelope.get("issue_url"), "conversation_url": url,
            "agent_trigger_run_id": run, "status": "trigger_accepted", "accepted_at_utc": utcnow(),
            "result_retrieved": False, "verified": False}


def check_status(receipt, token, opener=None):
    channel_id = _match(CHANNEL_ID, receipt["api_trigger_id"], "api_trigger_id")
    if receipt.get("agent_trigger_run_id") is None:
        raise ValueError("No run ID was returned by the API; check the configured result destination")
    run_id = _match(RUN_ID, receipt.get("agent_trigger_run_id"), "run_id")
    code, data = api_request(channel_id, token, "GET", suffix="/runs/" + run_id, opener=opener)
    if code != 200:
        raise RuntimeError("Unexpected status response (HTTP %s)" % code)
    state = data.get("status")
    if state not in RUN_STATUSES:
        raise RuntimeError("Unexpected or missing run status")
    if data.get("id") != run_id:
        raise RuntimeError("Run ID mismatch")
    result = {k: v for k, v in receipt.items() if k not in ("access_token", "token")}
    result["agent_run_status"] = state
    result["status_checked_at_utc"] = utcnow()
    result["result_retrieved"] = False
    result["verified"] = False
    if state == "completed":
        result["status"] = "run_completed_result_not_retrieved"
    elif state == "failed":
        result["status"] = "run_failed"
        error = data.get("error")
        result["error_code"] = error.get("code") if isinstance(error, dict) else None
    else:
        result["status"] = "run_" + state
    return result


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="action", required=True)
    a = sub.add_parser("prepare")
    for field in ("task-id", "surface", "agent-id", "api-trigger-id", "input-file", "out"):
        a.add_argument("--" + field, required=True)
    a.add_argument("--issue-url", default=None)
    b = sub.add_parser("trigger")
    b.add_argument("--envelope", required=True)
    b.add_argument("--out", required=True)
    b.add_argument("--execute", action="store_true", help="Explicitly authorize one live Workspace Agent trigger")
    c = sub.add_parser("status")
    c.add_argument("--receipt", required=True)
    c.add_argument("--out", required=True)
    opts = p.parse_args(argv)
    try:
        if opts.action == "prepare":
            obj = prepare(opts.task_id, opts.surface, opts.agent_id, opts.api_trigger_id,
                          pathlib.Path(opts.input_file).read_text(encoding="utf-8"), opts.issue_url)
        elif opts.action == "trigger":
            if not opts.execute:
                raise ValueError("Not executed; pass --execute after checking entitlement and costs")
            obj = trigger(parse_json(opts.envelope), os.getenv("WORKSPACE_AGENT_ACCESS_TOKEN"))
        else:
            obj = check_status(parse_json(opts.receipt), os.getenv("WORKSPACE_AGENT_ACCESS_TOKEN"))
        save_json(opts.out, obj)
        print(json.dumps({"status": obj["status"], "saved_to": opts.out}))
        return 0
    except (ValueError, RuntimeError, OSError, urllib.error.URLError, json.JSONDecodeError, KeyError) as e:
        print("BRIDGE_ERROR: " + str(e), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
