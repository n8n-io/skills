# Testing workflows

Two tools, used together. `prepare_test_pin_data` returns JSON Schemas (no actual data) for every node that needs pinning. You generate sample values matching the schemas and pass them to `test_workflow` as the `pinData` parameter. Inspect results via `get_execution`.

## What `test_workflow` actually pins

Three categories are pinned (return your supplied data instead of executing): **trigger nodes**, **nodes with credentials**, and **HTTP Request nodes**. Everything else runs.

| Node category | Behavior under `test_workflow` |
|---|---|
| Trigger node | Pinned, never fires |
| HTTP Request | Pinned, does NOT hit the URL |
| Slack / Gmail / Discord / SMTP / Telegram | Pinned (credentialed), does NOT send |
| Postgres / MySQL / Mongo / Supabase | Pinned (credentialed), does NOT read or write |
| LLM nodes (OpenAI, Anthropic, etc.) | Pinned (credentialed), no API call, no cost |
| Data Tables (built-in n8n storage) | Real reads AND writes (no credential, not pinned) |
| Code node | Executes as written |
| Edit Fields / Set / If / Switch / Merge / Filter | Execute normally |
| Wait node | Actually waits |
| Execute Workflow (sub-workflow call) | Runs the sub end-to-end, and the sub's pinning rules don't apply |

The auto-pin covers most of the obvious side-effect surface (sends, third-party writes, paid API calls). It does NOT cover:

- **Data Tables**, since they're n8n's built-in storage and have no credential. Insert / Update writes for real.
- **Execute Workflow** calling a sub. Test mode does not propagate into sub-workflows. The sub runs normally with all its credentialed nodes firing for real (it's its own execution).
- **Execute Command** and **File Read/Write** nodes, which are credential-free I/O.
- **Code nodes that touch external state** (filesystem, child processes, network via Node APIs on self-hosted Code nodes).

## Non-negotiable

**Ask the user before `test_workflow` if any of the not-auto-pinned categories would fire downstream.** A short message before the call:

> "This workflow writes to the `customers` Data Table and calls sub-workflow `process-payment` (which charges Stripe). Both will fire for real. Want me to run the test?"

Many users will say yes (sandbox table, test sub, trust the inputs). Some will pin or disable specific nodes first. The conversation costs nothing, but running an irreversible operation against the wrong account costs everything.

Skip the ask when EVERY non-pinned downstream is read-only or stateless: Get / Search / Lookup, pure compute (Set / If / Code shaping data), MCP-extension tools that only read.

If you're unsure whether a node has side effects, ask. False-positive asks waste a turn, but false-negative side effects waste real resources.

## Generating pin data

`prepare_test_pin_data` returns JSON Schemas describing the expected shape for each node that needs pinning. **It does not return actual data, you generate it.** Merge sample values into a single `pinData` object keyed by node name, with every item wrapped in `{ "json": { ... } }`:

```js
{
  "Webhook": [{ "json": { "headers": {...}, "body": {...} } }],
  "Postgres1": [{ "json": { "id": "123", "email": "a@b.com" } }],
  "OpenAI Chat": [{ "json": { "message": { "content": "..." } } }]
}
```

Pin every key the generator returns. Skipping a credentialed node leaves it without input data, and the test won't represent real behavior. For keys where the generator can't infer a schema (no past executions, no node-type hint), use an empty default or hand-build based on what the next node expects.

## Mocking trigger input by type

`prepare_test_pin_data` generates a representative trigger input. Hand-build when the generator's defaults don't match real callers.

| Trigger | Pin shape |
|---|---|
| Webhook | `{ headers, params, query, body, webhookUrl }` |
| Schedule | Empty or timestamp-shaped. Default usually fine. |
| Manual | Arbitrary, whatever the first downstream expects. |
| Chat (`chatTrigger`) | `{ chatInput, sessionId, files }`. Pin `files: []` unless testing file handling. |
| Execute Workflow Trigger | The typed inputs declared on the trigger node. |
| Polling | One item shaped like what polling normally yields. Polling logic is bypassed. |

For per-trigger config details, see `n8n-node-configuration-official` `references/TRIGGER_NODES.md`.

## Strategies when a non-pinned downstream isn't safe

In order of preference:

1. **Ask the user first** (the protocol above). Many concerns dissolve once the user explicitly OKs the test or names which nodes worry them.
2. **Pin individual node outputs.** Add the node to your `pinData` object even though it's not auto-pinned. The pinned response is returned and the node body never runs. Works on any node.
3. **Disable specific nodes** (`disabled: true`) for the test run. `test_workflow` skips disabled nodes. Useful when nothing meaningful would be pinned and you just want to skip the side effect.
4. **Sandbox credentials.** A separate credential pointing at staging (Stripe test mode, sandbox Slack workspace, dev DB). The user owns creating these, suggest, don't implement without permission.

Pinning and disabling are revertable. Sandbox credentials are infrastructure and persist.

## Inspection after testing

`test_workflow` returns an execution ID. `get_execution({ executionId, workflowId, includeData: true })` exposes per-node input/output. Walk through:

- Per-node output shape matches intent.
- Errors caught by error branches fired correctly, not silently.
- Webhook response shape (status, body, headers) matches the contract.

The full pre-publish checklist that includes testing is in `VALIDATION_CHECKLIST.md` §5.

<!-- TEMPORARY: n8n's execution viewer shows no visual indication that a node's output was pinned via test_workflow. May be fixed in a future n8n version. When fixed, this section can be removed. -->

## After test_workflow: announce what was pinned

Pin data passed to `test_workflow` is **per-execution only**. It is not written to the workflow definition, and the n8n execution viewer currently shows no visual indicator (no pin icon, no badge) on the nodes that were pinned. The only programmatic signals are:

- The `pinData` block in `get_execution`'s response, which lists the pinned node names.
- `executionTime: 0` on each pinned node.

Because the user has no canvas confirmation that a destructive-looking node was actually mocked, **always tell the user which nodes were pinned after the call.** Especially for nodes whose live execution would be destructive (Postgres `DELETE`, payment capture, file write, email send). A one-liner is enough:

> "Test ran. Pinned (did NOT execute): `Webhook`, `Delete inactive customers`. Ran for real: `Format report`, `Send summary`."

Without this, the user has to either trust the protocol or open the execution payload to verify. The reassurance costs one sentence, but the cost of the user assuming a destructive node fired (or of assuming it was pinned when it wasn't) is much higher.

## `test_workflow` vs `execute_workflow`

| Tool | Trigger | Credentialed / HTTP nodes | Other downstreams |
|---|---|---|---|
| `test_workflow` | Pinned via your data | Pinned via your data | Run for real |
| `execute_workflow` | Real (kicked off ad-hoc) | Run for real | Run for real |

`execute_workflow` is **not** a safer `test_workflow`. It's the opposite. `test_workflow` covers the credentialed surface automatically, but `execute_workflow` runs everything end-to-end with real auth and cost. "Run this once for me" means `execute_workflow`. "Test this" means `test_workflow` (and ask about the not-auto-pinned downstreams first).

Both want the same ask-before-running discipline when user-visible side effects are at stake.

## Re-test after iteration

After fixing something, re-run `test_workflow` on the SAME pin data before claiming the fix works. Same pin, same expected output, every iteration.

If a test passes but production fails, check whether the pin data covers the failing case. Usually it doesn't, and the pin needs updating to match the real-world shape that broke things.
