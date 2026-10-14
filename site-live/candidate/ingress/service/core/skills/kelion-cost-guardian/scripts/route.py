#!/usr/bin/env python3
"""Deterministic, offline, fail-closed planning for Kelion Cost Guardian.

No API calls, ChatGPT setting changes, autonomous dispatch, or payments happen here.
A returned route is a recommendation, not proof a model actually ran.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

TIERS = {1: "economic", 2: "standard", 3: "advanced", 4: "critical"}
REASONING = {1: "low", 2: "medium", 3: "high", 4: "high"}
REASONING_ORDER = {"minimal": 0, "low": 1, "medium": 2, "high": 3, "extra_high": 4}
VALID_SURFACES = {"work", "codex", "chat", "agent"}
HIGH_RISK = {"security", "production", "privacy", "payments", "financial", "medical", "legal", "destructive", "safety"}
ACTION_APPROVAL = {"payments", "destructive", "production", "security", "privacy"}
KEYWORDS = {
    1: ("tradu", "translate", "rezuma", "sumar", "sort", "clasifica", "format", "extrage", "extract", "listeaza", "spell"),
    2: ("program", "cod ", "code", "debug", "script", "test", "formula", "raport", "report", "integreaza", "integration"),
    3: ("arhitect", "architecture", "migrare", "migration", "complex", "distribuit", "multi-agent", "multistep", "multi-step", "audit", "optimizare completa"),
    4: ("securitate critica", "incident de securitate", "security incident", "stergere productie", "delete production", "safety critical"),
}


def normalized(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.casefold())
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise ValueError(reason)


def classify(request: dict) -> tuple[int, list[str]]:
    task = request.get("task")
    require(isinstance(task, str) and bool(task.strip()), "task must be a nonempty string")
    flags = request.get("risk_flags", [])
    require(isinstance(flags, list) and all(isinstance(f, str) for f in flags), "risk_flags must be a string list")
    require(set(flags).issubset(HIGH_RISK), "unsupported risk_flags")
    level, explanations = 2, ["Default standard when complexity is uncertain"]
    t = normalized(task)
    for candidate in (1, 2, 3, 4):
        hits = [word for word in KEYWORDS[candidate] if word in t]
        if not hits:
            continue
        # A simple signal can lower only the baseline. A difficult signal wins.
        if candidate == 1 and level == 2:
            level = 1
        elif candidate > level:
            # A document noun alone must not turn a simple summary into a complex job.
            if not (candidate == 2 and level == 1 and set(hits).issubset({"raport", "report", "test"})):
                level = candidate
        explanations.append("Task indicators for level %s: %s" % (candidate, ", ".join(hits[:3])))
    if flags:
        level = 4
        explanations.append("Sensitive/high-impact risk flags: " + ", ".join(sorted(set(flags))))
    minimum = request.get("min_tier")
    if minimum is not None:
        require(type(minimum) is int and 1 <= minimum <= 4, "min_tier must be an integer 1..4")
        if minimum > level:
            level = minimum
            explanations.append("Explicit minimum quality tier requested")
    return level, explanations


def _validated_models(manifest: dict) -> list[dict]:
    require(type(manifest) is dict and manifest.get("schema_version") == 1, "manifest requires schema_version=1")
    models = manifest.get("models")
    require(type(models) is list, "manifest models must be a list")
    ids = set()
    for m in models:
        require(type(m) is dict and type(m.get("id")) is str and bool(m["id"]), "model requires id")
        require(m["id"] not in ids, "duplicate model id")
        ids.add(m["id"])
        require(type(m.get("capability_tier")) is int and 1 <= m["capability_tier"] <= 4, "invalid capability_tier")
        require(type(m.get("enabled")) is bool and type(m.get("verified")) is bool, "enabled/verified must be explicit booleans")
        require(m.get("surface") in VALID_SURFACES or str(m.get("surface", "")).startswith("connector:"), "invalid model surface")
        require(m.get("billing_mode") in {"included", "metered", "unknown"}, "invalid billing_mode")
        require(type(m.get("cost_rank")) is int and 1 <= m["cost_rank"] <= 100, "cost_rank must be ordinal 1..100")
        levels = m.get("reasoning_levels")
        require(type(levels) is list and bool(levels) and all(v in REASONING_ORDER for v in levels), "invalid reasoning_levels")
    require(type(manifest.get("connectors", [])) is list, "connectors must be a list")
    return models


def select_model(models: list[dict], surface: str, tier: int) -> dict | None:
    required_effort = REASONING[tier]
    choices = []
    for model in models:
        if model["surface"] != surface or not model["enabled"] or not model["verified"]:
            continue
        if model["billing_mode"] != "included" or model["capability_tier"] < tier:
            continue
        supported = [level for level in model["reasoning_levels"] if REASONING_ORDER[level] >= REASONING_ORDER[required_effort]]
        if supported:
            selected_effort = min(supported, key=lambda item: REASONING_ORDER[item])
            choices.append((model["cost_rank"], model["capability_tier"], REASONING_ORDER[selected_effort], model["id"], selected_effort))
    if not choices:
        return None
    cost, capability, _, model_id, reasoning = sorted(choices)[0]
    return {"id": model_id, "reasoning": reasoning, "capability_tier": capability,
            "cost_rank": cost, "cost_rank_type": "ordinal proxy, NOT a measured price or credit saving"}


def route(request: dict, manifest: dict) -> dict:
    require(type(request) is dict, "request must be a JSON object")
    models = _validated_models(manifest)
    surface = request.get("surface", "work")
    require(surface in VALID_SURFACES, "invalid surface")
    tier, why = classify(request)
    previous = request.get("previous_attempt")
    escalation = False
    if previous is not None:
        require(type(previous) is dict, "previous_attempt must be object")
        prev_tier = previous.get("tier")
        require(type(prev_tier) is int and 1 <= prev_tier <= 4, "invalid previous_attempt tier")
        failure_verified = previous.get("failure_verified") is True
        if failure_verified and previous.get("result") == "failed":
            tier = max(tier, min(4, prev_tier + 1))
            escalation = tier > prev_tier
            why.append("Verified failure; increase capability without redoing successful work")
        else:
            why.append("No verified failure: no automatic escalation")
    flags = set(request.get("risk_flags", []))
    connector_id = request.get("connector")
    model = select_model(models, surface, tier)
    connector_status = "not_requested"
    connector_model = None
    allow_connector_call = connector_id is None
    if connector_id is not None:
        require(type(connector_id) is str and bool(connector_id), "connector must be a nonempty string")
        matches = [c for c in manifest.get("connectors", []) if c.get("id") == connector_id]
        if len(matches) != 1:
            connector_status = "unknown_or_duplicate_connector"
            allow_connector_call = False
        else:
            c = matches[0]
            # Explicit verified agent attachment and authorization are required.
            allow_connector_call = (c.get("enabled") is True and c.get("authenticated") is True
                                    and c.get("attached_to_agent") is True)
            control = c.get("model_control", "unknown")
            require(control in {"host", "internal", "none", "unknown"}, "invalid connector model_control")
            if not allow_connector_call:
                connector_status = "not_verified_for_target_agent"
            elif control == "internal":
                if c.get("model_switch_verified") is True:
                    connector_model = select_model(models, "connector:" + connector_id, tier)
                    connector_status = "internal_model_selected" if connector_model else "internal_model_unavailable"
                else:
                    connector_status = "internal_model_switch_unverified"
            elif control == "host":
                connector_status = "host_model_only"
            elif control == "none":
                connector_status = "connector_has_no_model_switch"
            else:
                connector_status = "connector_control_unknown"
    requires_approval = bool(flags & ACTION_APPROVAL)
    if request.get("action") in {"purchase", "modify_subscription", "change_permissions", "delete", "deploy"}:
        requires_approval = True
        why.append("Potentially consequential action requires the existing approval flow")
    status = "plan_only"
    if not model:
        status = "blocked_no_verified_included_model"
    elif connector_id and not allow_connector_call:
        status = "blocked_connector_not_usable"
    elif connector_status in {"internal_model_unavailable", "internal_model_switch_unverified"}:
        status = "blocked_connector_internal_model_selection"
    return {
        "status": status, "policy_tier": tier, "policy_level": TIERS[tier],
        "surface": surface, "host_model": model, "connector": connector_id,
        "connector_model": connector_model, "connector_status": connector_status,
        "requires_action_approval": requires_approval,
        "requires_paid_credit_purchase": False,
        "auto_escalated": escalation,
        "reuse_successful_work": bool(previous is not None),
        "rationale": why,
        "actual_credit_cost": None, "measured_savings": None,
        "dispatch_performed": False, "settings_changed": False,
        "connector_call_performed": False,
        "note": "Recommendations only; do not claim model changes, connector execution, account quotas or financial savings without real confirmation.",
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Kelion offline, fail-closed cost route planner")
    p.add_argument("--manifest", type=Path, required=True, help="verified local model/connector availability JSON")
    p.add_argument("--request", type=Path, help="request JSON file (default stdin)")
    args = p.parse_args()
    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        req = json.loads(args.request.read_text(encoding="utf-8") if args.request else sys.stdin.read())
        print(json.dumps(route(req, manifest), ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
