# Webhook trigger and Respond to Webhook

Entry and exit of webhook-shaped API workflows. Param shapes are version-dependent; `get_node_types` is canonical. This file covers what's *not* in the type def: runtime behavior, gotchas, and patterns.

## Webhook trigger

### Path: globally unique

Webhook paths are global within the n8n instance, not per-workflow. Two webhooks on the same path conflict and n8n typically rejects activation. Use UUIDs or descriptive paths (`/customer-events`, `/payment-webhook`).

### Authentication: use the trigger's built-in auth, not hand-rolled checks

Use `parameters.authentication` (`'basicAuth'` or `'headerAuth'`) with the matching credential type. n8n rejects mismatched callers with 401 before the workflow runs.

Anti-pattern: `authentication: 'none'` plus an IF node comparing the `Authorization` header to a `$vars.token` or hardcoded string. Not encrypted, leaks in exports, no rotation. See `n8n-credentials-and-security-official`.

### `responseMode`: behavioral differences

| Mode | Behavior |
|---|---|
| `'onReceived'` (default) | Returns 200 immediately. Workflow continues asynchronously. Caller doesn't see workflow output. |
| `'lastNode'` | Returns the last node's output. Synchronous. |
| `'responseNode'` | Use `Respond to Webhook` nodes to control the response. Most flexible. |
| `'streaming'` | Stream data in real time from streaming-enabled nodes. |

For request/response API workflows, use `responseNode` paired with explicit Respond to Webhook nodes.

### Output structure (runtime)

The webhook trigger emits `{ headers, params, query, body, webhookUrl, executionMode }`, plus `binary` if `options.rawBody` is set, plus `jwtPayload` if JWT auth was used. `executionMode` is `'test'` or `'production'`.

## Respond to Webhook

### `responseBody` for `respondWith: 'json'`: pass the object, not a string

The type def accepts both `IDataObject` and `string`. If you pass `JSON.stringify(obj)`, n8n then JSON-serializes the *string*, producing an escaped, double-encoded body. Pass the object directly.

### `responseCode` defaults to 200, including on error paths

The most common Respond-to-Webhook bug: forgetting to change the response code on an error branch. Returning 200 with an error body is worst-of-both-worlds: the caller's HTTP client sees success while the body says failure.

Set the response code explicitly on every Respond branch. See `n8n-error-handling-official`'s `RESPONSE_SHAPES.md` for the success/4xx/5xx mapping.

### Multiple Respond nodes per workflow

A workflow can have multiple Respond nodes, one per response shape. n8n returns whichever fires first.

```
[Webhook] ─→ [Validate] ─→ [Process] ─→ [Respond 200 success]
            ├─→ [Respond 400 validation_error]
            ├─→ [Respond 401 unauthorized]
            └─→ (error outputs from process) ─→ [Respond 5xx]
```

For 202-Accepted-plus-callback and other async API patterns, see `n8n-error-handling-official`'s `API_WORKFLOWS.md`.
