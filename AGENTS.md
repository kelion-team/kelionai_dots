# KelionAI agent orchestration rules (Codex / repository)

- First consult `orchestration/README.md` and GitHub issue #4 when the user asks to delegate to previously published ChatGPT workspace agents.
- Reuse the agent registry. Distinguish `agt_...` identity from `agtch_...` official published API trigger channel.
- Never claim delegation from route recommendations, a GitHub issue, or a Slack message. A confirmed API 202 is accepted dispatch, not agent completion.
- Use `orchestration/bridge.py`; perform no live trigger without authorization, exact agent and channel IDs, safe key handling, and cost check.
- Verify run state and retrieve the **actual output** through an authorized path such as a result attached by the agent to a GitHub issue. Readback is mandatory before setting verified.
- Work on one active user priority; don't start unrelated queued projects. Do not add subscriptions, API credits, or unsafe personal shared connector accounts.
