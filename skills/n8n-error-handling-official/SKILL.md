---
name: n8n-error-handling-official
description: Use when building any webhook-triggered workflow, scheduled/production-bound workflow, wiring a per-node error output, or any workflow where silent failure would drop user-visible work. Triggers on "webhook", "respond to webhook", "API", "production", "error", "failure", "5xx", "try/catch", "error workflow", "onError", "continueErrorOutput", "error branch", "node error output", "output(1)", "main[1]", "scheduled", or any workflow that runs unattended.
---

# n8n Error Handling

Default n8n node behavior: error → workflow halts → caller gets nothing useful. For unattended workflows (webhook APIs, scheduled jobs, queue workers), that default is wrong. The symptom is "the integration just stopped working" with no log, no message, no clue.

This skill is about handling errors so failures are loud, structured, and recoverable. Or best case scenario, handled in a way where it self heals.

## Non-negotiables

For any **API-shaped workflow** (webhook trigger paired with `Respond to Webhook`):

1. **Every fallible node's error output is wired, and both paths end at a `Respond to Webhook`.** No hanging error branches, or the caller would see a timeout. "Fallible" = HTTP, DB, third-party API, file operation, anything that throws.
2. **Status code maps to cause.** Caller's fault → 4xx, your fault → 5xx. A 200 default on an error path produces silent failure: caller thinks success, processes empty data.

For any **unattended workflow** (scheduled, cron, queue-driven, agent tool):
3. **Set a workflow-level error workflow.** Catches what escapes per-node handling: timeouts, crashes between nodes, errors in unwired nodes. Set it via `update_workflow` `setWorkflowSettings.errorWorkflow` (n8n 2.29.0+); the target must be a published workflow containing an active Error Trigger, or the update is rejected. See `references/ERROR_WORKFLOWS.md`.

## Strong defaults

- **Error response bodies are structured.** Not just "Internal Server Error". Use `{ "error": "<short identifier>", "message": "<human-readable>" }`. See `references/RESPONSE_SHAPES.md`.
- **Network-calling nodes have `retryOnFail` configured.** Transient 429s and upstream blips get absorbed before reaching the error path. See "Self-healing on transient failures" below.

## When error handling can be looser

Internal one-off workflows where you're the only user, you watch each run, and the cost of failure is "I notice and re-run". Default `onError: 'stopWorkflow'` is fine. The line: if anyone other than you sees the output (downstream system, end user, on-call), the non-negotiables apply.

## API workflow shape

The canonical webhook-API workflow:

```
Webhook trigger
  ├── (success path)  → Process → Respond to Webhook (200, body)
  └── (any node's error output)
                       → Respond to Webhook (5xx, structured error body)
                       → Optional: log to error tracker / logger / notify channel
```

For a complete walkthrough including how to wire multiple fallible nodes to a single error responder, see `references/API_WORKFLOWS.md`.

## Schema validator (Set IIFE)

For any webhook API doing input validation, lift the Set-based schema validator pattern into the endpoint instead of writing IF/Switch chains per field. The two example files are the source of truth:

- `references/examples/validation-subworkflow.ts`: the bare pattern (Webhook → Set with the validation IIFE → Respond, expression-driven status code). Useful as a minimal demo.
- `references/examples/validation-subworkflow-usage.ts`: the endpoint pattern (Webhook → Set → If valid → your business logic → 200 success / 400 with the standard `{error: "validation_error", message, details, request_schema}` body). Lift this into your endpoint and replace the NoOp placeholder with real logic.

**The procedure for an agent using this:**

1. **Lift the usage-example structure into the new endpoint.** Webhook → Set (Validate Schema) → If Params Valid → your logic → success/400 Respond. Don't reinvent.
2. **Edit the IIFE for your schema.** Update `REQUIRED_SCHEMA` and the per-field checks inside the Set node's expression for your endpoint's input shape. The pattern below the schema constant is mechanical: presence check, type check, constraint check, push to `errors[]`.
3. **Leave the output shape alone.** `valid`, `validationError`, `details`, `requiredSchema` are the contract the Respond node consumes. Renaming them breaks the response body.

The full procedure, supported constraint patterns, schema design rules, and the `={{ ... }}` wrapping gotchas live in `references/API_WORKFLOWS.md` "Schema validator (Set IIFE)".

## Per-node error setup (recap)

Each fallible node needs two changes (see `references/NODE_ERROR_OUTPUTS.md`):

1. **Set `onError: 'continueErrorOutput'`** on the node config.
2. **Wire `output(1)`** to your error handler.

Both required. One without the other is the silent-failure mode.

## Self-healing on transient failures

Before wiring the error path, configure node-level retry on any node making a network call (HTTP Request, comms like Gmail/Slack/Discord, DB, AI, third-party API nodes). Transient 429s and brief upstream blips get absorbed, so the error output then only fires on real failures, and alerts and 5xx responses reflect actual problems instead of noise.

```ts
{
    retryOnFail: true,
    maxTries: 3,
    waitBetweenTries: 5000,    // ms; 5000 is the max and should be your default
}
```

Works on any node that calls a network service, not just HTTP Request. The engine retries on *any* error, with no per-status-code filter, and the engine caps `maxTries` at 5 and `waitBetweenTries` at 5000ms (`packages/core/src/execution-engine/workflow-execute.ts`). See `n8n-node-configuration-official` `HTTP_NODES.md` and `AI_NODES.md` for node-specific notes.

## Response shapes: map the cause to the status code

A 5xx response with `text/plain "Internal Server Error"` is technically 5xx but useless. And not every error is 5xx. Match the status code to *why* the request failed.

**Common mistake:** wiring every error path to a single `Respond to Webhook` returning 500 "internal_error". Every failure looks the same to the caller, even when they sent bad input. Breaks monitoring: you can't distinguish real outages from bad caller input.

**Default mapping by cause:**

| Cause | Status | Error code | Path |
|---|---|---|---|
| Required field missing or wrong type | 400 | `validation_error` | Validate up front with the Set-based schema validator (see `references/examples/validation-subworkflow.ts` for the bare pattern and `validation-subworkflow-usage.ts` for the endpoint template), or, for trivial cases, an inline IF/Switch + dedicated 400 Respond. Don't go through error outputs. Ideally echo the schema in the response so the caller can self-correct. |
| Auth missing or invalid | 401 | `unauthorized` | Same. Check up front, return 401 directly. |
| Authenticated but not allowed | 403 | `forbidden` | Same. |
| Resource ID exists in request, doesn't in your data | 404 | `not_found` | Branch off the lookup result, not the lookup error. |
| Operation conflicts with current state (duplicate, race) | 409 | `conflict` | Detect with logic, not error output. |
| Caller exceeded rate limit | 429 | `rate_limit_exceeded` | Set `Retry-After` header. |
| Node threw and you don't know why | 500 | `internal_error` | The error-output path. |
| Third-party API errored | 502 | `upstream_error` | Error output of the HTTP Request node. |
| Workflow can't currently process (downstream down, rate-limited upstream) | 503 | `service_unavailable` | Detect via specific error, return with hint. |
| Third-party API timed out | 504 | `upstream_timeout` | Error output filtered by error message. |

**Two distinct flows:**

- **Validation failures (4xx)** are checked *upstream* of the work, via IF/Switch branches, not error outputs. Use a dedicated Respond per shape (400 missing field, 401 no auth, etc.).
- **Execution failures (5xx)** come out of error outputs ("we tried, something broke"). A single error responder for all 5xx is fine. Differentiate the body's `error` code by inspecting the failed node where useful.

**One Respond, expression-driven status code.** When the error path differs only by status code and message text (same body shape, no header/content-type changes), don't fan out to N Respond nodes via a Switch. The Respond to Webhook node accepts expressions in its `Response Code` and body fields. Compute the code inline, so one Respond node carries the whole error path.

```ts
// Response Code on a single Respond to Webhook node:
{{ (() => {
    const msg = $json.error?.message || $json.message || ''
    if (msg.includes('INVALID_ID')) return 400
    if (/429|too many/i.test(msg)) return 429
    if (/openrouter|anthropic|llm/i.test(msg)) return 502
    return 500
})() }}
```

Switch + N Responds only earn their place when responses diverge *structurally*: different headers, different body shapes, redirects, different content types. Same shape with a different number is one expression-driven Respond.

For full conventions including correlation IDs, retryable-vs-fatal flags, validation details, and rate-limit shapes, see `references/RESPONSE_SHAPES.md`.

## Workflow-level error workflows

For unattended workflows, configure the instance's error workflow (or per-workflow override) to point at a workflow that:

1. Captures the failure (workflow name, execution ID, error, stack).
2. Notifies someone (Slack, email, on-call).
3. Optionally enqueues a retry (with backoff).

Catches what per-node handling misses: timeouts, crashes between nodes, errors in unwired nodes.

See `references/ERROR_WORKFLOWS.md`.

## Reference files

| File | Read when |
|---|---|
| `references/API_WORKFLOWS.md` | Building or reviewing a webhook-trigger / respond-to-webhook workflow |
| `references/ERROR_WORKFLOWS.md` | Setting up workflow-level error catching for production workflows |
| `references/RESPONSE_SHAPES.md` | Defining the response body conventions for your APIs |
| `references/NODE_ERROR_OUTPUTS.md` | Wiring a per-node error output on individual fallible nodes |

## Anti-patterns

| Anti-pattern | What goes wrong | Fix |
|---|---|---|
| Webhook → process → respond, no error branch | Caller gets timeout or empty 500 | Wire every fallible node's `output(1)` to a Respond to Webhook |
| Single Respond to Webhook for both paths | Body shape doesn't tell caller what happened | Two Respond nodes, one per path, with explicit codes and bodies |
| Error path returns 200 with `{ "error": ... }` body | Caller's HTTP client treats it as success, so error handling never fires | Always 4xx/5xx for error paths |
| Catching errors in Code node and returning them as data | Downstream sees error-shaped data, workflow continues | Let it throw, configure `onError: 'continueErrorOutput'` and wire the error path |
| Production workflow with no workflow-level error workflow | A genuine failure goes nowhere | Set up an error workflow. See `ERROR_WORKFLOWS.md` |
| Generic "Internal Server Error" on every failure | Can't distinguish caller bug from upstream from rate limit | Structured error codes. See `RESPONSE_SHAPES.md` |
| Production node calls a flaky or rate-limited API with no `retryOnFail` | Every transient 429 or upstream blip surfaces as a 5xx, and alerts fire on noise | Set `retryOnFail: true, maxTries: 3, waitBetweenTries: 5000` on the node. See "Self-healing on transient failures" |
| 500 for everything not a 200 | Caller can't separate their bad input from your outage, so their monitoring fires on your noise | Map cause → status code. Caller issues are 4xx. |
| Switch over the error message → N Respond nodes that differ only by status code | 5 nodes for what's one Respond with an expression-driven `Response Code` | Compute the code inline in a single Respond. See "One Respond, expression-driven status code" above. |

