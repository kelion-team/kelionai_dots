"""DOTS reports difficulty; Kelion chooses; dispatch must match that choice.

Offline preflight. No model inference, billing or platform setting changes.
The manifest must describe verified models of the exact published target agent.
"""
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "kelion_cost_route", Path(__file__).resolve().parents[1] /
    "skills/kelion-cost-guardian/scripts/route.py")
_router = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_router)


def decide(envelope, assessment, manifest):
    """Consume one target DOTS assessment without launching another AI agent."""
    if not isinstance(assessment, dict):
        raise ValueError("DOTS assessment required")
    if assessment.get("agent_id") != envelope.get("agent_id"):
        raise ValueError("Assessment is not from the target DOTS")
    if assessment.get("task_id") != envelope.get("task_id"):
        raise ValueError("Assessment is for a different task")
    if assessment.get("task_input") != envelope.get("input"):
        raise ValueError("Assessment input differs from the dispatched task")
    tier = assessment.get("difficulty")
    if type(tier) is not int or not 1 <= tier <= 4:
        raise ValueError("DOTS difficulty must be an integer 1..4")
    if not isinstance(assessment.get("reason"), str) or not assessment["reason"].strip():
        raise ValueError("DOTS must explain its difficulty assessment")
    # An available model on another agent is not available on this DOTS.
    eligible = dict(manifest)
    eligible["models"] = [m for m in manifest.get("models", [])
                          if m.get("agent_id") == envelope["agent_id"]]
    request = {"task": envelope["input"], "surface": "agent",
               "min_tier": tier, "risk_flags": assessment.get("risk_flags", [])}
    if "previous_attempt" in assessment:
        request["previous_attempt"] = assessment["previous_attempt"]
    result = _router.route(request, eligible)
    result.update({"decision_by": "Kelion", "assessment_by": envelope["agent_id"],
                   "task_id": envelope["task_id"], "dots_difficulty": tier,
                   "assessment_reason": assessment["reason"]})
    return result


def preflight(envelope, assessment, manifest):
    """Allow only a verified execution binding matching Kelion's selection.

    Workspace Agent trigger cannot override its published model/effort. Until
    an official adapter can configure and read back that setting, it must match
    an already verified binding. Never put invented model fields in API input.
    """
    decision = decide(envelope, assessment, manifest)
    if decision["status"] != "plan_only":
        raise ValueError("Kelion blocked dispatch: " + decision["status"])
    if decision["requires_action_approval"]:
        raise ValueError("Existing action approval required before dispatch")
    chosen = decision["host_model"]
    matches = [b for b in manifest.get("execution_bindings", [])
               if b.get("agent_id") == envelope["agent_id"]
               and b.get("api_trigger_id") == envelope["api_trigger_id"]]
    if len(matches) != 1:
        raise ValueError("No unique verified execution binding for this DOTS channel")
    binding = matches[0]
    if (binding.get("verified") is not True or
            binding.get("model_id") != chosen["id"] or
            binding.get("reasoning") != chosen["reasoning"]):
        raise ValueError("Selected model/effort not applied to target DOTS; no dispatch")
    # Included subscription usage still consumes credits. It is not free.
    if binding.get("usage_cost_verified") is not True:
        raise ValueError("Target DOTS usage cost is not verified; no dispatch")
    credits = binding.get("estimated_max_credits")
    remaining = binding.get("remaining_authorized_credits")
    import math
    if any(type(v) not in (int, float) or not math.isfinite(v) or v < 0
           for v in (credits, remaining)) or credits > remaining:
        raise ValueError("Verified credit budget missing or exceeded; no dispatch")
    decision["status"] = "execution_binding_verified"
    decision["estimated_max_credits"] = credits
    return decision
