# Kelion decides for each DOTS

DOTS supplies `agent_id`, `task_id`, exact `task_input`, `difficulty` (1..4), `reason`, and optional `risk_flags`. These are input assertions; this module does not authenticate the producer or run a DOTS to generate them. Kelion validates task correspondence and selects the lowest ordinal cost-ranked eligible model and its required supported effort. Cost ranks are administrator estimates, not measured optimality or prices.

Each model in the verified manifest must be on surface `agent` and carry the exact `agent_id`. `execution_bindings` must describe the exact `agent_id` and `api_trigger_id`, `verified: true`, selected `model_id` and `reasoning`, `usage_cost_verified: true`, finite nonnegative `estimated_max_credits` and `remaining_authorized_credits`. Unknown cost or mismatching configuration blocks dispatch. These inputs must come from a trusted, current configuration source; the module does not verify telemetry remotely or reserve budget across processes.

```bash
python orchestration/bridge.py trigger --execute --envelope task.json --dots-assessment assessment.json --cost-manifest verified-manifest.json --out receipt.json
```

The public Python trigger performs the same preflight. No additional AI call is made for classification. No subscription changes, credit purchases, model overrides or live test are performed by installation.

Workspace Agent trigger does not receive invented model/effort fields. A pre-existing verified published binding must match Kelion's choice; otherwise the run is blocked until an authorized official configuration adapter applies and reads back that choice. The configuration adapter, automatic DOTS assessment production, authenticated manifest and ChatGPT/Work/Codex activation remain unimplemented. This change enforces routing before dispatch; it does not demonstrate full automatic operation.

Validation: `python -m unittest discover -s orchestration/tests -q` — 33 offline tests pass, including difficulty-dependent selection, task/agent isolation, budget refusal, model mismatch refusal and mandatory preflight before transport.
