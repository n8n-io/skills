# Parameter verification

The most common cause of "this isn't working" is a misconfigured parameter.

## The four checks

### 1. Is the parameter present?

```
get_workflow_details({ workflowId: <id> })
```

Look at the failing node's `parameters`. Is the field actually there?

Common mistake: a parameter set via UI then dropped when the workflow is regenerated from SDK code.

### 2. Is the value the right type?

Some nodes are strict:

- **Numbers as numbers**, not `"100"`.
- **Booleans as booleans**, not `"true"`.
- **Arrays as arrays**, even for single values.

Wrap expressions in `{{ }}` to force evaluation:

```
field: 100              # might be string
field: {{ 100 }}        # definitely number
```

### 3. Is the parameter conditional on another?

Many parameters only apply when a parent has a specific value:

- HTTP Request `credentials` requires `authentication !== 'none'`.
- Postgres `query` requires `operation === 'executeQuery'`.
- Slack `channelId` requires `select === 'channel'`.

If parent Y is wrong, X is ignored.

### 4. Does the shape match the current node version?

```
get_node_types([{ name: '<node>', resource: '<r>', operation: '<o>' }])
```

Compare returned shape vs. workflow parameters. Renames, restructuring, or major-version changes can leave the workflow on an old shape.

## Operation-aware checks

Most nodes have `(resource, operation)` pairs that change parameter shape. **Always pass discriminators** to `get_node_types`. Otherwise the generic shape may miss operation-specific fields.

## Shortcut: run all four checks at once

`validate_node_config([{ type, typeVersion, parameters, isToolNode? }])` runs the same Zod schema as `validate_workflow` on a single node config. Returns `{ path, message }` per failure: missing required fields, wrong types, dependent params without their parent. Useful when shape-vs-config diffing is slow (deep params, nested displayOptions, AI tool subnodes). For tool subnodes, set `isToolNode: true`.

Schema-level only: doesn't catch connection bugs, missing credentials, or runtime data issues.

## Credential checks

For auth errors:

```
get_workflow_details → failing node's `credentials` reference
```

What MCP can see on the node:

- `id` matches an expected credential reference.
- Credential type matches what the node expects (e.g., Slack expects `slackOAuth2Api`, not `slackApi`).

What MCP **can** see (via `list_credentials`): id, name, type, scopes, project. Use it to confirm a referenced credential still exists.

What MCP **can't** see: credential contents and live OAuth token state. Credential **creation** is still UI-only (no MCP tool, no public API). Ask the user when those are needed.

OAuth note: n8n auto-refreshes OAuth tokens. The user does not need to re-authenticate periodically. Persistent token errors usually mean the auth setup is wrong (incorrect type, missing scopes, app revoked on the upstream) or the upstream is rejecting the token, not that n8n forgot to refresh.

## Connection (wiring) checks

`validate_workflow` doesn't catch wiring traps. Manual checks via `get_workflow_details`:

- Is a Merge `numberOfInputs` left at the default 2 when 3+ sources converge? → `n8n-node-configuration-official` `references/MERGE_NODE.md`
- Is `useDataOfInput` set to a value that doesn't match the wire feeding that input? → `n8n-node-configuration-official` `references/MERGE_NODE.md`
- Is `onError: 'continueErrorOutput'` set on the node but `main[1]` empty, or vice versa? → `n8n-error-handling-official` `references/NODE_ERROR_OUTPUTS.md`

These don't surface as parameter errors. The node runs with bad input. Always inspect connections after a failed update.

## Input data checks

```
get_execution({ executionId: <execution_id>, workflowId: <workflow_id>, includeData: true })
```

Inspect the failing node's input. If it's wrong:

- Trace upstream: which node produced it?
- Was upstream's expression correct? Did `$json` resolve as expected?
- Did a conditional branch send the wrong path?

"Node broken" often means "node given garbage."

## Authentication-specific debugging

- **401**: missing, expired, or wrong-type credential.
- **403**: valid credential without permission. Check scopes on the upstream service.
- **400 with auth message**: wrong header format or auth mode. Re-fetch HTTP Request shape, verify `authentication` and `genericAuthType`.
- **No error, no data**: silently authenticated as a different user (e.g., `anon` instead of `service_role`).

## Pagination check

If a query "doesn't return enough":

- Round-number result count (10, 50, 100): pagination.
- Look for `next_cursor` / `next_page` / `has_more` in the response.
- Is the node configured to follow pagination?

## Type-specific gotchas

- **Big integers**: IDs above `Number.MAX_SAFE_INTEGER` lose precision as numbers. Use strings.
- **Date strings**: confirm format matches what the node expects.
- **JSON-in-string**: some APIs return JSON-encoded strings, so `JSON.parse` to use.
- **Empty vs null vs missing**: different things, and nodes treat them inconsistently. Check the actual value.

## Worked example

User: "the Postgres query returns nothing but I know there are matching rows."

1. `get_execution({ executionId, workflowId, includeData: true })` → Postgres ran successfully, returned 0 rows.
2. `get_workflow_details({ workflowId })` → query `SELECT * FROM users WHERE email = $1`, parameter `$1 = '={{ $json.email }}'`.
3. Execution input: `email = "User@Example.com"` (capital U).
4. DB stores lowercase: `user@example.com`.
5. **Fix:** `={{ $json.email.toLowerCase() }}`.

Not workflow logic, but input not matching data. Without inspecting actual input, this would've taken much longer.

## Don't skip the basics

The user's instinct is to look at the most-recently-changed thing. Often right, not always. The diagnostic order (execution, workflow details, node types, input) covers most-common to least-common systematically.
