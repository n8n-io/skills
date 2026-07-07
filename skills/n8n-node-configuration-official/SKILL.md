---
name: n8n-node-configuration-official
description: 'Use when configuring any n8n node: HTTP, webhooks, database, comms (Slack/Gmail/Discord), AI, triggers, Merge, anything. Triggers on any node-builder call (`node(...)`, `trigger(...)`, `tool(...)`, `memory(...)`, `languageModel(...)`, `ifElse(...)`, `merge(...)`, etc.), configuring a parameter, `useDataOfInput`, `numberOfInputs`, fan-in convergence, or any node-specific debugging.'
---

# n8n Node Configuration

Each n8n node has its own parameter shape, often with conditional fields (parameter X only matters when parameter Y has value Z). Shapes evolve between versions. Guessing produces cryptic validation errors.

Don't guess, use the `get_node_types` tool.

## Non-negotiable

**Call `get_node_types` with discriminators (resource, operation, mode) before configuring a node.** Without discriminators you get the generic shape, missing operation-specific parameters and required fields. Build against the exact shape. Don't guess from memory.

**The live `get_node_types` output is the canonical parameter shape.** The references in this skill cover patterns, gotchas, security rules, and decision-making (when to use which operation, why credentials over text fields, engine retry caps, etc.) not parameter names or field structures. If a reference example conflicts with what `get_node_types` returns, trust the tool. Markdown drifts; the type def is generated from the live source.

**Never guess resource-locator or load-options values.** When `get_node_types` shows a param with `@searchListMethod` or `@loadOptionsMethod` (Slack channels, Sheets tabs/docs, DB tables/columns, model lists, labels), resolve the real value with `explore_node_resources` (pass a `credentialId` from `list_credentials`) and use a returned `value`. If you already know the exact ID, use it; if several match and intent is ambiguous, ask the user. An invented ID validates but points at nothing. Exception: `toolWorkflow.workflowId` has no search method, resolve it via `search_workflows` and use `mode: 'id'`.

## Strong defaults

- **Configure operation-first.** Set `resource` and `operation` first, and conditional parameters become visible. Most "field doesn't exist" errors are really "you haven't set the parent operation yet."
- **Don't carry parameters across operations.** When changing `operation`, re-derive from the new shape. Stale parameters from the previous operation trip validation.

## The flow for any new node

```
1. search_nodes(['<capability keyword>'])
   → returns matching node IDs + discriminators
2. Pick the right (resource, operation) for the task.
3. get_node_types([{ name: '...', resource: '...', operation: '...' }])
   → returns exact parameter shape including conditional fields
4. For any RLC / load-options param in that shape, ground the real value:
   explore_node_resources({ nodeType, version, methodName, methodType, credentialType, credentialId, currentNodeParameters? })
   → use a returned `value`. Don't invent IDs.
5. Build the node config from that shape.
6. validate_workflow → fix errors.
7. get_workflow_details → inspect the saved config; confirm parameters landed.
8. test_workflow with pinned data → confirm runtime behavior.
```

Skipping any step compounds the next. The most common skip is step 3, leading to "Cannot read property X" errors that are really "you didn't pass the discriminators."

### `validate_node_config` as a side-channel

`validate_node_config([{ type, typeVersion, parameters, isToolNode? }])` runs the same Zod schema as `validate_workflow` on isolated node configs. Schema-level only; doesn't replace `validate_workflow` (still the publish gate). Cleaner signal for:

- **Iterating on a single node mid-build.** Faster than re-running `validate_workflow` per tweak.
- **Small edits to an existing workflow.** Wiring unchanged? Check the one node you touched; full validate before publish.
- **Debugging a misconfigured node.** Per-parameter errors with no graph noise.

For tool subnodes (wired via `ai_tool`), set `isToolNode: true` so the correct `displayOptions` branch evaluates.

## Operation-aware configuration

Most nodes have a top-level shape like:

```ts
{
  resource: '<thing being operated on>',   // 'message', 'spreadsheet', 'user', etc.
  operation: '<verb>',                      // 'send', 'append', 'lookup', etc.
  // ...operation-specific parameters
}
```

The `(resource, operation)` pair determines what other parameters exist (e.g., Slack `(message, send)` differs from `(user, info)`).

Pattern:

1. Set `resource` and `operation` first.
2. Re-fetch `get_node_types` with those discriminators if you didn't initially.
3. Configure the rest from the operation-specific shape.

## Property dependencies: the subtle trap

Some parameters depend on others in non-obvious ways:

- A field is required only when another field has a specific value.
- A field accepts different types depending on a mode.
- A field's options come from another field's value.

Examples:

- HTTP Request `authentication: 'genericCredentialType'` requires `genericAuthType` and `credentials`, but `'predefinedCredentialType'` requires a different shape.
- Postgres `operation: 'executeQuery'` requires `query`, while `operation: 'select'` requires `table` and `columns`.
- Slack `messageType: 'block'` enables block-builder fields absent from `messageType: 'text'`.

Always inspect via `get_node_types` for the specific operation. Don't reuse a config from a different operation and expect it to validate.

Options-from-another-field is a `@loadOptionsMethod`: resolve the live options with `explore_node_resources` (`methodType: 'loadOptions'`), passing prior selections via `currentNodeParameters` when the method depends on them (e.g. listing a spreadsheet's tabs needs `documentId`).

## Reference files

Per-category gotchas. Read the file for the node type you're configuring:

| File | When to read |
|---|---|
| `references/HTTP_NODES.md` | Configuring HTTP Request: auth, pagination, query/body parameters, retries |
| `references/WEBHOOK_NODES.md` | Configuring Webhook trigger or Respond to Webhook: body parsing, response shape, async patterns |
| `references/COMMS_NODES.md` | Slack, Gmail, Discord, email: credential types, message shapes, attachments |
| `references/DATABASE_NODES.md` | Postgres, MySQL, Mongo, Supabase: query vs operation, parameter binding, error handling |
| `references/AI_NODES.md` | AI Agent node config knobs: streaming, vision, `maxIterations`, retries on the model sub-node. Defers design (prompts, tools, memory, structured output) to `n8n-agents-official` |
| `references/TRIGGER_NODES.md` | Webhook, Schedule, Manual, Execute Workflow Trigger: input schemas, polling vs realtime |
| `references/SWITCH_FALLBACK.md` | Configuring a Switch node: unnamed outputs / missing fallback silently drop unmatched items |
| `references/MERGE_NODE.md` | Configuring a Merge node, or you see `useDataOfInput`, `numberOfInputs`, or branches converging |

## Anti-patterns

| Anti-pattern | What goes wrong | Fix |
|---|---|---|
| Building node config from memory of how the node looked last year | Parameter shape has drifted, validation fails with cryptic errors | Always `get_node_types` per session per node |
| Skipping discriminators in `get_node_types` | Get generic shape, miss operation-specific required fields | Always pass `resource` + `operation` (and `mode` where present) |
| Copying a node config from one operation to another and tweaking | Stale parameters trip validation, and conditional fields don't apply | Re-derive from the new operation's shape |
| Hardcoding tokens / credentials in node text fields | Leaks on export. See `n8n-credentials-and-security-official` | Always credentials |
| Not testing the node with `test_workflow` after configuring | Runtime errors only surface on real data | Always test with pinned data before publish |

