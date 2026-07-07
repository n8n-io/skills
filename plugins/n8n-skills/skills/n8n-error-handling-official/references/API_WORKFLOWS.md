# API workflows

The canonical n8n pattern for "this workflow is an HTTP API":

```
Webhook trigger → [processing] → Respond to Webhook
```

This file covers wiring that pattern with proper error handling so the API behaves under failure, not just happy-path.

## The shape

A production webhook API:

```
                        ┌─→ Validate input ─→ ... ─→ Respond (200, success body)
Webhook trigger ───────┤
                        └─→ (any error output)
                              → Respond (5xx, structured error body)
                              → (optional) Log / notify
```

Variants:

- **Multiple processing branches**: each eventually flows to either success or error Respond.
- **Long-running work**: webhook responds 202 immediately, work continues async. See end of file.

## Wiring every fallible node

For each fallible node (HTTP, DB, third-party, validation):

1. Set `onError: 'continueErrorOutput'` in the node config.
2. Wire `output(1)` to your error Respond node, possibly via a logger or normalizer.

Concretely:

```ts
const fetchUser = node({
    type: 'n8n-nodes-base.postgres',
    config: {
        parameters: { /* ...query config... */ },
        onError: 'continueErrorOutput',
    },
})

const callExternal = node({
    type: 'n8n-nodes-base.httpRequest',
    config: {
        parameters: { /* ...config... */ },
        onError: 'continueErrorOutput',
    },
})

const respondError = node({
    type: 'n8n-nodes-base.respondToWebhook',
    config: {
        parameters: {
            responseCode: 502,
            responseBody: '={{ JSON.stringify({ error: "upstream_error", message: $json.error?.message ?? "External service failed" }) }}',
            options: { responseHeaders: { entries: [{ name: 'Content-Type', value: 'application/json' }] } },
        },
    },
})

workflow
    .add(webhook.output(0).to(fetchUser))
    .add(fetchUser.output(0).to(callExternal))
    .add(callExternal.output(0).to(respondSuccess))

    // Error paths: both go to the same responder
    .add(fetchUser.output(1).to(respondError))
    .add(callExternal.output(1).to(respondError))
```

Three things to notice:

1. **One `respondError` for many sources.** Fan-in keeps the workflow readable.
2. **Both fallible nodes have `onError: 'continueErrorOutput'`.** If either is missing, that node's failure halts the workflow instead of routing.
3. **The error body uses an expression to surface the actual error message.** Be careful what you leak. See "Don't leak internals" below.

## What "fallible" means

A node is fallible if any of these can happen:

- Network call (HTTP, third-party API, DB).
- Auth failure (credential expired, token rotated).
- Schema mismatch (DB column missing, JSON parse failure).
- Rate limit (429 from upstream).
- Logic error (Code node throws).
- File operation (missing path, permissions).

Nodes **not** typically fallible:

- Set / Edit Fields on pure data (can still fail on bad input, so validate upstream).
- IF / Switch with simple expressions (if it throws, it's a bug, not something to catch).
- Function nodes without I/O (pure transformations).

When in doubt, wire error handling. The cost is one extra connection.

## The "Validate input" stage: where most 4xx responses live

Validate webhook input before processing. Fail fast with 4xx, don't lump caller-side errors with real outages.

**Validation failures go through IF/Switch + dedicated Respond, not error outputs.** They're *expected failures with a known response*, not node failures.

```ts
const validate = ifElse({
    config: {
        parameters: {
            conditions: { /* check required fields */ },
        },
    },
})

const respondBadRequest = node({
    type: 'n8n-nodes-base.respondToWebhook',
    config: {
        parameters: {
            responseCode: 400,
            responseBody: '={{ JSON.stringify({ error: "validation_error", message: "Missing required field: customer_id" }) }}',
        },
    },
})

workflow
    .add(webhook.output(0).to(validate))
    .add(validate.onTrue(processing))             // valid → process
    .add(validate.onFalse(respondBadRequest))     // invalid → 400
```

### Schema validator (Set IIFE)

For any webhook needing structured input validation, lift the Set-based validator pattern, not a hand-rolled IF chain. Two example files are the source of truth:

- `examples/validation-subworkflow.ts`: the bare pattern (Webhook → Set → expression-driven Respond). Useful as a minimal reference.
- `examples/validation-subworkflow-usage.ts`: the endpoint pattern (Webhook → Set → If valid → your business logic → 200 success / 400 with structured body). Lift this into any new endpoint.

**The procedure for using these:**

1. **Lift the usage-example structure into your endpoint.** The node graph (Webhook → Validate Schema → If Params Valid → your logic → success/400 Respond) is already the right shape. Replace the `Your workflow logic here` NoOp with your real processing.
2. **Edit `REQUIRED_SCHEMA` and the per-field checks inside the IIFE.** The Set node's `result` assignment holds an inline IIFE. The `REQUIRED_SCHEMA` constant at the top is for echo-back; the actual checks live in the per-field `if`/`else if` block below it. Add, remove, or change checks to match your endpoint's input shape.
3. **Don't change the output keys.** The IIFE returns `{ valid, validationError, details, requiredSchema }`. The Respond nodes consume those names. Renaming any of them breaks the response body.

The 400 body shape (`{ error: "validation_error", message, details, request_schema }`) matches the default in `RESPONSE_SHAPES.md`. Don't deviate.

**Output contract.** The Set node's `result` field (an object) is what downstream nodes branch on:

- Valid: `{ valid: true, validationError: null }`
- Invalid: `{ valid: false, validationError: <human-readable summary string>, details: { <path>: <message>, ... }, requiredSchema: <the schema, echoed back> }`

The usage example maps these into the standard 400 body: `validationError` becomes `message`, `details` is forwarded as-is, and `requiredSchema` becomes `request_schema`. The schema is echoed back so the caller (or an LLM) can self-correct.

**Supported constraint patterns.** The hand-crafted IIFE covers the same subset of JSON Schema constraints as a generic validator, applied to your specific schema:

| Category | What to write inline |
|---|---|
| Required field present | `if (!("name" in body)) errors.push(...)` |
| Type check | `else if (typeof body.name !== "string") errors.push(...)` |
| String constraints | `body.name.length < N`, `/regex/.test(body.email)` |
| Number constraints | `body.seat_count < min`, `> max`, `Math.floor(v) !== v` for integer |
| Enum | `["a","b","c"].indexOf(body.plan) === -1` |
| Array | `Array.isArray(body.tags)`, `body.tags.length < N` |
| Conditional | nest the checks inside `if (body.type === "X") { ... }` |

**Schema design rules** (`REQUIRED_SCHEMA` constant is what gets echoed back to the caller):

- Every field SHOULD have a `description` in plain language. The IIFE appends them to error lines (`• name: Missing required field "name" - Customer full name`).
- Use `integer` type (with the `Math.floor(v) !== v` check) for whole numbers.
- Use a literal array for enums and `.indexOf(...) === -1` to check.
- Use `additionalProperties: false` semantically (echoed back) and add an explicit "Unknown field" check in the IIFE if you want to reject extras at runtime.

**Embedding gotcha: regex backslashes in the `REQUIRED_SCHEMA` literal.** Inside the SDK's TS template literal, regex `\S` written as a JS string needs four backslashes:

```ts
email: { type: "string", pattern: "^\\\\S+@\\\\S+\\\\.\\\\S+$", description: "Contact email" }
```

The chain: TS template literal `\\\\` → string `\\` → JS string `\\` (escape) → runtime char `\`. The regex literal in the IIFE itself uses the simpler form `/^\\S+@\\S+\\.\\S+$/` (two backslashes per `\S` in TS source).

**Example error output.** Given a schema requiring `name`, `email`, `plan`, `seat_count`, and a non-empty `tags` array, a malformed payload produces:

```
Validation failed (5 issues):
• name: Missing required field "name" - Customer full name
• email: "not-an-email" is not valid - Contact email address
• plan: "premium" is not an allowed value. Must be one of: starter, pro, enterprise - Subscription plan
• seat_count: Expected type "integer" but got "non-integer number" - Number of licensed seats
• tags: Must have at least 1 item(s), got 0 - At least one tag for categorization
```

The `description` from each field is pulled into the message, so callers and downstream LLMs get actionable hints, not just a `"validation failed"` opaque string.

Real APIs need more than one 4xx path. Common ones to wire *before* processing:

```
Webhook trigger
  → Auth check (header present + valid?)
      ├── No → Respond 401 unauthorized
      └── Yes ↓
  → Validate input (required fields, types, value ranges)
      ├── Invalid → Respond 400 validation_error (with `details` per field)
      └── Valid ↓
  → Authorization check (does this caller's auth allow this operation?)
      ├── Not allowed → Respond 403 forbidden
      └── Allowed ↓
  → Lookup target resource
      ├── Doesn't exist → Respond 404 not_found
      └── Exists ↓
  → Processing stage (HTTP calls, DB writes, etc.). This is where 5xx errors come from
```

Each upstream check is a separate IF/Switch + Respond pair. That's not over-engineering. It gives the caller a useful error code instead of a generic 500.

## 5xx error responses: the execution-failure path

Past validation, remaining errors are 5xx: nodes failing, upstream timing out, etc. Wire via per-node error outputs.

A single error responder for all 5xx is fine, *but* differentiate the body by inspecting which failure happened:

```ts
const respondError = node({
    type: 'n8n-nodes-base.respondToWebhook',
    config: {
        parameters: {
            responseBody: `={{ (() => {
                const err = $json.error ?? {}
                const node = err.node?.name ?? 'unknown'

                // Distinguish by failed node or error message
                if (err.message?.includes('timeout')) {
                    return JSON.stringify({ error: 'upstream_timeout', message: 'External service did not respond in time' })
                }
                if (err.message?.includes('rate limit')) {
                    return JSON.stringify({ error: 'service_unavailable', message: 'Rate limit hit on upstream service' })
                }
                return JSON.stringify({ error: 'internal_error', message: 'An internal error occurred' })
            })() }}`,
            options: {
                responseCode: `={{ $json.error?.message?.includes('timeout') ? 504 : ($json.error?.message?.includes('rate limit') ? 503 : 500) }}`,
                responseHeaders: { entries: [{ name: 'Content-Type', value: 'application/json' }] },
            },
        },
    },
})
```

## Don't leak internals in error responses

Tempting:

```ts
responseBody: '={{ JSON.stringify({ error: "internal_error", details: $json.error }) }}',
```

What `$json.error` actually contains: stack traces, internal node names, sometimes connection strings, sometimes upstream responses with embedded secrets.

Better: log the full error privately, return a sanitized message:

```ts
const respondError = node({
    type: 'n8n-nodes-base.respondToWebhook',
    config: {
        parameters: {
            responseCode: 502,
            responseBody: '={{ JSON.stringify({ error: "upstream_error", message: "External service failed" }) }}',
        },
    },
})

// Separately, log full details
const logError = node({
    type: 'n8n-nodes-base.httpRequest',
    config: {
        parameters: { /* ...send full error to your logging service / Sentry / Slack... */ },
    },
})

.add(callExternal.output(1).to(logError))
.add(logError.output(0).to(respondError))
```

The caller sees a clean message. Internal details stay internal. If you operate distributed tracing and want a correlation ID in the body, add `request_id` per the "When to add request IDs" section in `RESPONSE_SHAPES.md` (and add it consistently across success and error responses on every endpoint, not just here).

## Correlation IDs (optional, opt-in)

The default response shape doesn't include a `request_id`, see "When to add request IDs" in `RESPONSE_SHAPES.md` for when it's worth adding. If you do opt in (you're running distributed tracing or log correlation), two ways to source the ID:

1. **Caller-supplied:** check `X-Request-ID` header, pass through and include in responses.
2. **Generated:** use `$execution.id` or generate a UUID, include in responses and logs.

Either works. Generated is easier, caller-supplied is better for distributed tracing. Do it on **every** endpoint or none, partial coverage is worse than no coverage.

## Status code conventions

The status code is the caller's first signal. Be deliberate:

- **2xx**: success. 200 sync, 202 "accepted, processing".
- **4xx**: caller's fault. 400 (bad input), 401 (no auth), 403 (not allowed), 404 (not found), 429 (rate limited).
- **5xx**: your fault. 500 (unexpected internal), 502 (upstream broken), 503 (temporarily down), 504 (upstream timeout).

Distinguishing 4xx from 5xx matters because:

- Caller monitoring alerts on 5xx (your fault) but not 4xx (their fault).
- 5xx suggests retry, 4xx suggests don't.
- Aggregated error rates segment by class.

## Async / 202-Accepted pattern

If the work takes longer than the caller wants to wait:

```
Webhook trigger
  → Validate input
  → Respond to Webhook (202, { "job_id": "..." })  ← respond immediately
  → Continue processing in same workflow OR Execute Workflow (sub-workflow)
  → On completion: callback / queue / email
```

The webhook returns 202 with a `job_id` (the identifier the caller will use to poll status), and processing continues async. The caller polls a status endpoint or receives a callback to a webhook they provided. The `job_id` is intrinsic to the async pattern (it's how you find the work later), not the optional `request_id` correlation field discussed above.

Its own pattern with its own gotchas (idempotency, callback retries, status tracking). Build deliberately.

## Verifying the API workflow

Before publishing:

1. Test the success path with `test_workflow`. Confirm shape and code. **API workflows almost always have side-effecty downstreams (DB writes, third-party calls, comms), so ask the user before testing.** See `n8n-workflow-lifecycle-official` `references/TESTING.md`.
2. Trigger an error path. Use `prepare_test_pin_data` to inject a value that breaks a processing node, then `test_workflow`. Confirm the error Respond fires with the right code/body.
3. Verify connections via `get_workflow_details`. Every fallible node has `onError: 'continueErrorOutput'` AND `output(1)` wired. See `references/NODE_ERROR_OUTPUTS.md`.
4. Confirm no internal details leak in the error body.

If any are off, fix before publish.
