# Magentic and native Kelion execution

The native host runs the original Microsoft Magentic workflow, reads its actual
manager requests, invokes the native manager and the selected Kelion role, and
imports their original outputs through `magentic_host.py`. The specialist can
use connectors actually exposed by the host. The demonstrated connector is
GitHub, with a fresh task-bound read and an identical durable readback.

This source tree is based on repository main at
`6d10a90ff28b8084764ca413d91a7eab63cd9574`, including the report-outbox fixes.
The earlier frozen candidate and proof are separate immutable evidence inputs;
their files were not changed. The framework integration module was copied
byte-for-byte into this source tree. Microsoft framework commit:
`2d58876e49d7569dafeac6b385a120514c1e6a12`.

## Host contract

1. Initialize a bounded native-host task with actual participant names from
   `native_roles.json`, an objective, and explicit authorization.
2. Advance the original framework. Export its pending request.
3. The conversation invokes its native collaboration tool. Transfer the actual
   request and profile instructions; Kelion supplies the chosen model and effort.
   Obtain a request-bound assessment before a participant executes work.
4. The native actor writes its original output, including `request_id`, `text`,
   and `source_actor`. Record the actual dispatch reference, then ingest it.
5. The bridge verifies the complete original request hash, binds the actor and
   output to the request, records the receipt and response, and reads them back.
6. Advance until the actual framework terminal event. Verify recovery in a new
   process and absence of duplicated responses or native dispatch.

The model plans and selects the speaker through StandardMagenticManager. This
bridge does not choose speakers through a lexical selector. All participant
names are resolved through the existing registry. Only the context-code role
has been exercised in the new connector demonstration; the existence of 22
profiles does not attest that all their specialist engines or connectors work.

The Python entry point does not possess the native conversation's delegation
tool. The host must invoke it through its supported tool surface. It cannot run
an unattended native conversation merely because this module is installed on a
Linux server. An unavailable host remains pending rather than receiving a fake
model response. The original framework extension used here is BaseChatClient;
the native host transport is Kelion integration code, not a built-in Microsoft
ChatGPT subscription provider.

## Invocation

Use the interpreter with the pinned framework dependencies. Supply paths from
the current executor; a materialized artifact does not share another executor's
absolute paths. Options precede the operation:

```text
python -m orchestration.magentic_host
  --source-root <this source tree>
  --framework-python <pinned-environment-python>
  --state-root <private native-host artifact directory>
  --run-dir <private durable run directory>
  --requested-model <Kelion's actual dispatch selection>
  --requested-effort <Kelion's actual dispatch selection>
  init --file <explicit authorized bounded config>
```

Operations are `init`, `advance`, `pending`, `ingest` and `status`. Ingest needs
the original actor output file, actual actor and dispatch reference; participant
ingest also requires its actual task-bound assessment. Defaults retain the
selection of the demonstrated task; specify the actual selection for other
tasks. Requested selection is not actual model, effort, or billing attestation.

No receipt is authenticated by a checksum. Source integrity, host-observed
native dispatch, and provider execution/cost attestation remain distinct. No
paid provider call, new key, account, subscription, top-up, deployment, or
production-controller replacement is performed by this entry point.

## Remaining dependencies

The separate Codex CLI app-server fails before `initialize` in this environment.
Moving SQLite state with the official `sqlite_home` setting succeeded, but
Codex still requires its installation identifier in the read-only managed home.
No writable-home/authentication substitution, mount change, or security bypass
was performed. The native conversation route is usable without that subprocess.

Roust is not exposed in this native session. This demonstration uses actual
read-only source inspection and GitHub; it does not attest Roust execution.
Cross-surface continuation through distinct ChatGPT, Work and Codex sessions,
published Agent Studio execution, and unattended host operation require actual
supported routes and separate acceptance evidence.

## Rollback

Stop issuing host advances or native dispatches for this run. Keep the journal
and original output artifacts for readback. The previous controller, held
personal skill, main branch, existing credentials and original frozen proof
remain unchanged. The source addition is removable without modifying those
components. Do not delete the journal to conceal incomplete dispatches.

## Official sources

- [Microsoft Agent Framework](https://github.com/microsoft/agent-framework/tree/2d58876e49d7569dafeac6b385a120514c1e6a12)
- [Codex App Server](https://learn.chatgpt.com/docs/app-server)
- [Codex configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference)
