# Native Kelion orchestration

22 role profiles were derived from the canonical Library index v15 (SHA256 cac2a3e4fa71daa3149db8a61a89823444dff4c5808336f555e071e917a6ae0f). The published agent IDs are source provenance, not native runtime identities. These profiles preserve descriptions and scope limits; original cloud skills, dependencies, tools, OAuth attachments and memory are not migrated or certified.

Profiles under `.codex/agents/` omit both model and effort. Project `.codex/config.toml` enables native agents and limits concurrent specialist threads to one. Explicit spawn model/effort selected by Kelion therefore are not overridden by role-specific pins. Work cloud does not necessarily read these TOML files: `native_dispatch.py` includes the profile instructions in the message for the parent to pass to the native tool.

For each task: get a small task-bound native DOTS assessment; run `native_dispatch.py` with the exact role, task, assessment and current verified runtime model manifest; Kelion selects an eligible model/effort; the parent invokes the actual native spawn tool with both explicit settings and no full-history fork. Reuse the assessment thread only when its exact model/effort already match the decision. Read and verify the real result. A plan alone is not dispatch.

```bash
python orchestration/native_dispatch.py --request request.json --assessment assessment.json --manifest current-runtime-models.json
python -m unittest discover -s orchestration/tests -q
```

The model list is not limited to three hardcoded tiers. The caller provides all currently supported, verified models with their capabilities, supported efforts and relative cost ranks. Unknown or metered eligibility is refused. Cost ranks and capabilities are operational estimates, not measured cheapest-total-cost guarantees. Included usage can still consume subscription credits. No payment or API key provisioning happens here.

A real native probe in Work used an explicit gpt-6-luna/low assessment thread, received difficulty 1, ran the Kelion controller, and continued the same thread for read-only work. It returned 22 roles, 22 TOMLs, zero pinned model fields, zero pinned effort fields, exit 0. 40 orchestration tests passed. `native_probe_result.json` records the evidence and limits. This verifies one native task, not all specialist functions or the full ChatGPT–Work–Codex system.

No persistent gateway/listener was deployed by this change. Other sessions must open the updated project and have native delegation available. Plain Chat and the always-on Kelion dot remain unverified. The existing Workspace Agent bridge remains separate and requires a published binding matching its selection.
