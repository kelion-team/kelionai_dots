# KelionAI shared delegation bridge (Chat / Work / Codex)

**Scope:** Prepare tasks from any surface, start an existing published Workspace Agent through the **official** ChatGPT Workspace Agents API (when authorized), record a run receipt, and check run state without pretending to retrieve the answer. The common project task ledger is [GitHub issue #4](https://github.com/kelion-team/kelionai_dots/issues/4) and associated issues. No paid services or new identities are provisioned by these files. This bridge does **not** itself make an agent run in Codex or install any Workspace Agent into Work.

## What is proven

- ChatGPT's Slack connector sent a message to existing `#kelion-bridge` and read back the identical message. This is a **transport test**, not a successful Workspace Agent delegation.
- The official Workspace Agents API supports `POST /v1/workspace_agents/{agtch_ID}/trigger` and a **beta** read-only status endpoint `GET /v1/workspace_agents/{agtch_ID}/runs/{apirun_ID}`. A 202 response can include a ChatGPT conversation URL and beta run ID. It **does not include the agent's answer**.
- Codex's Workspace Agents plugin is a **builder/admin** integration, not a way to execute a Workspace Agent.

## Configuration still required before a live test

1. In Agent Studio, **on an already published agent**, enable an API channel and record the resulting `agtch_...` identifier. An `agt_...` agent ID is not an API trigger channel ID.
2. An authorized workspace admin creates a **Workspace Agent access token with only the Workspace Agents scope** and makes it available as `WORKSPACE_AGENT_ACCESS_TOKEN` in a secure environment. Never commit or paste it into a conversation. Confirm no unapproved usage charges before a live call.
3. Ensure the target agent has appropriate permissions and an authorized path to **write its result and provenance to the corresponding GitHub issue** (or another genuine readable shared artifact). App-level write approvals remain in force; avoid personal shared credentials.
4. Each caller in **Chat, Work and Codex** needs access to the same GitHub repo/issues and the supported trigger mechanism. A GitHub issue or manifest alone does not grant cross-surface access.

## Example, offline preparation (no network, no paid call)

```bash
printf 'Return a one-line diagnostics result only.' > /tmp/kelion-task.txt
python orchestration/bridge.py prepare \
  --task-id kelion-demo-0001 --surface codex --agent-id agt_EXAMPLE \
  --api-trigger-id agtch_EXAMPLE --input-file /tmp/kelion-task.txt \
  --issue-url https://github.com/kelion-team/kelionai_dots/issues/4 \
  --out /tmp/kelion-task.json
```

**Real trigger only after the above setup and explicit approval** (initiates an agent run):

```bash
python orchestration/bridge.py trigger --envelope /tmp/kelion-task.json --execute --out /tmp/kelion-receipt.json
python orchestration/bridge.py status --receipt /tmp/kelion-receipt.json --out /tmp/kelion-status.json
```

Use the **same `task_id` / conversation key** when handing the task between media. An idempotency header prevents duplicate trigger requests for the same task/channel; this is not a user-facing progress notification. The bridge does not poll continuously.

## Acceptance (all required, not claimed)

For **Chat, Work, and Codex independently** record: origin, exact existing `agt_...` agent, trigger-channel ID, real conversation URL, real run ID, final run status, immutable input reference, actual result reference, and verification by a different actor or test. The read-only status `completed` is **not** evidence that the response was retrieved. A test is **not complete** without the actual result. Then test a task created on one surface and read/continued on another.

Security: no tokens in repo/issue/Slack, no retries or timers that can increase usage, no disabled MFA, and no elevated/shared connector privileges without review. Only work already covered by the user's authorization may be triggered.

Official docs:
- https://developers.openai.com/workspace-agents/trigger-runs
- https://help.openai.com/en/articles/20001143-chatgpt-workspace-agents-for-enterprise-and-business
- https://help.openai.com/en/articles/20001236-deploy-chatgpt-workspace-agents-to-slack-admin-setup
