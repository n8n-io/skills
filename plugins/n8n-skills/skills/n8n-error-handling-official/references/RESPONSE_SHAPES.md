# Response shapes

Conventions for webhook API response bodies, both **success** and **error**. Pick a shape and stick to it across workflows on the same instance. Predictable responses make consumers (humans, dashboards, retry logic) easier.

This file is opinions. Adjust to your team's existing conventions. Consistency within a project beats consistency with this skill.

## Match what's already on the instance

Before adopting the shapes below, **search for existing API workflows on the instance and reuse their conventions.** Inconsistency across endpoints is worse than any specific choice, and a one-off custom shape is hard to undo once callers depend on it.

```
search_workflows({ query: 'webhook' })
search_workflows({ query: 'API' })
search_workflows({ query: '<your domain>: ' })   # if the project uses domain prefixes
```

For each result, open `get_workflow_details` and look at how its `Respond to Webhook` nodes are shaped:

- Top-level keys (envelope vs bare, presence of `error`/`message`, presence of `request_id`).
- Whether success bodies wrap the payload or return it bare.
- Error code strings already in use (`validation_error` vs `bad_request` vs `INVALID_INPUT`).
- Header conventions (`Content-Type`, `Retry-After`, `X-Request-Id`).

If results are sparse, mixed, or you're unsure whether a project convention exists, **ask the user** before locking in a shape. One quick "I see endpoints A and B use shape X but endpoint C uses shape Y, which is the house style?" saves a future migration. Don't invent a domain prefix or convention from nothing.

The same rule applies upward: if your repo or company has a documented public API style, that wins over both this file and the instance.

## The default success shape

Return the data bare. **For requests that create or update a resource, the strong preference is to return the full resource's fields with a 200 status, not a bare `{ "ok": true }` or just the new ID.** Returning the resource saves the caller a follow-up GET, lets them confirm what actually got persisted (server-set defaults, normalized values, generated timestamps), and makes the endpoint usable as a single round-trip in UIs that immediately render the result.

```json
{
  "customer_id": "cus_123",
  "balance": 4200,
  "currency": "USD",
  "created_at": "2026-04-25T12:34:00Z"
}
```

Only deviate from this when:

- The resource is genuinely large and the caller doesn't need it (then return only the ID, document why).
- The operation has no resource (event ingestion, fire-and-forget): `{}` or `204 No Content` is fine.

If a payload is genuinely list-shaped, return a top-level array or an explicit `{ "items": [...] }` (the second is friendlier to future pagination metadata).

## The default error shape

```json
{
  "error": "<machine-readable error code>",
  "message": "<human-readable explanation>"
}
```

- `error` is a stable string identifier (not a sentence). Clients can branch on it.
- `message` is the human version. Safe to log, safe to show users (after sanitization).
- The HTTP status code already separates success from failure, so no `ok: false` flag is needed.

Optional fields by case:

| Field | When to include |
|---|---|
| `details` | Validation errors with field-by-field problems |
| `retry_after` | Rate limits (`Retry-After` header should also be set) |
| `documentation_url` | Public APIs where you want callers to RTFM |

## Error codes

Pick from a small, stable set. Adding a new code is fine, but renaming an existing one breaks callers.

### 4xx (caller's fault)

| Code | Meaning |
|---|---|
| `validation_error` | Required field missing, type wrong, etc. |
| `invalid_input` | Field is present but value is invalid |
| `unauthorized` | No auth or expired auth |
| `forbidden` | Authenticated but not allowed |
| `not_found` | Resource doesn't exist |
| `conflict` | Operation conflicts with current state (duplicate key, etc.) |
| `rate_limit_exceeded` | Too many requests |
| `unsupported_media_type` | Content-Type wrong |

### 5xx (your fault)

| Code | Meaning |
|---|---|
| `internal_error` | Catch-all, something failed unexpectedly |
| `upstream_error` | Third-party API returned an error |
| `upstream_timeout` | Third-party API didn't respond |
| `service_unavailable` | Workflow temporarily can't process (you're down or rate-limited upstream) |
| `not_implemented` | Operation not supported in current version |

## Validation error details

For 400/`validation_error`, include per-field details. Real example produced by the Set-based schema validator pattern (see below):

```json
{
  "error": "validation_error",
  "message": "Validation failed (3 issues):\n• name: Missing required field \"name\"\n• email: \"not-an-email\" is not valid - Contact email address\n• plan: \"premium\" is not an allowed value. Must be one of: starter, pro, enterprise - Subscription plan",
  "request_schema": { /* the JSON Schema, echoed back for caller-side self-correction */ }
}
```

`message` is the human summary (safe to show users), `details` is the structured per-field map (safe to map to UI fields), and `request_schema` is an optional echo useful for LLM-driven retries. Don't roll this by hand: see [`examples/validation-subworkflow.ts`](./examples/validation-subworkflow.ts) and [`examples/validation-subworkflow-usage.ts`](./examples/validation-subworkflow-usage.ts), with the full procedure in [`API_WORKFLOWS.md`](./API_WORKFLOWS.md).

## Rate limit responses

For 429 / `rate_limit_exceeded`:

```json
{
  "error": "rate_limit_exceeded",
  "message": "Too many requests. Retry after 30s.",
  "retry_after": "2026-05-08T21:10:05.135Z"
}
```

Also set the HTTP `Retry-After` header. Well-behaved clients respect the header without parsing the body.

## What NOT to put in error responses

### Stack traces

```json
{ "error": "internal_error", "stack": "Error at line 42 of /opt/..." }
```

❌ Reveals server internals: paths, version info, library names. Useful for attackers, useless for callers. Log internally, return a generic message.

### Upstream errors verbatim

```json
{ "error": "upstream_error", "details": "<verbatim upstream response body>" }
```

❌ Upstream might embed their own internals: tokens, PII. Sanitize: surface "upstream service failed" with a request ID, and details go in your logs.

### SQL queries

```json
{ "error": "internal_error", "query": "SELECT * FROM users WHERE id = ..." }
```

❌ Same problem. Worse: exposes schema and access patterns.

### Tokens, credentials, or auth values

Even innocuous-looking fields (`headers`, `config`, `request`) can leak token values. Audit error responses carefully. Leaks are easier than expected.

## SDK shape for Respond to Webhook

```ts
const respondSuccess = node({
    type: 'n8n-nodes-base.respondToWebhook',
    config: {
        parameters: {
            responseCode: 200,
            responseBody: '={{ JSON.stringify($json) }}',
            options: {
                responseHeaders: {
                    entries: [
                        { name: 'Content-Type', value: 'application/json' },
                    ],
                },
            },
        },
    },
})

const respondError = node({
    type: 'n8n-nodes-base.respondToWebhook',
    config: {
        parameters: {
            responseCode: 502,
            responseBody: '={{ JSON.stringify({ error: "upstream_error", message: "External service failed" }) }}',
            options: {
                responseHeaders: {
                    entries: [
                        { name: 'Content-Type', value: 'application/json' },
                    ],
                },
            },
        },
    },
})
```

Always set `Content-Type: application/json` explicitly. Default behavior depends on `responseBody` shape and isn't reliable.
