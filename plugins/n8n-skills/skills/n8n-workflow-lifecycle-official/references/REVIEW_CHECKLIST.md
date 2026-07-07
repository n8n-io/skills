# Workflow review checklist

Severity-tiered audit for any existing n8n workflow or n8n build (group of workflows). Different from `VALIDATION_CHECKLIST.md` (which is pre-publish gates for *your own* in-progress build): this file is for reviewing arbitrary workflows, including ones built by anyone, from anywhere.

## How to use

Walk the list top to bottom. For each item, inspect the workflow (`get_workflow_details`) and decide if the issue applies. Report findings grouped by severity. Each item links to the canonical skill reference for the *why* and the *how to fix*. Be a very thourough reviewer and air on the side of reading references to ensure full context. 

**You're reviewing JSON, not SDK source.** `get_workflow_details` returns the n8n workflow JSON (nodes with `parameters`, `connections` graph, credential references, node `type` strings like `n8n-nodes-base.httpRequest`). Phrase findings in JSON terms: "node `Foo` has `parameters.onError` set to `'continueErrorOutput'` but `connections.Foo.main[1]` is empty,".

| Severity | Meaning | Action |
|---|---|---|
| **MUST FIX** | Ship-blocker. Security hole, broken connection, or production-breaking bug. | Stop the workflow if active, fix before re-enabling. |
| **SHOULD FIX** | Real issue. Antipattern, missing error handling on production paths, broken contracts. | Plan a follow-up, fix in the next change. |
| **NICE TO HAVE** | Polish. Naming, descriptions, conventions. | Clean up opportunistically. |

## Cross-cutting first

Before walking the per-domain list:

- [ ] **Pull the workflow(s).** `get_workflow_details({ workflowId })`, required so subsequent checks operate on the actual JSON, not assumptions.
- [ ] **High-level intent / logic smell test.** Read the workflow's `description` (if it exists), then trace the happy path once top to bottom. Does the structure match what the description says it does? Anything obviously dead, missing, contradictory, or not fitting (a write node in a workflow described as read-only, a fan-out with one terminal branch that should be wired further, an HTTP call to a domain unrelated to the stated integration)? Catches whole classes of issues the per-domain checks won't surface.
- [ ] **Note the trigger type.** Webhook, schedule, manual, sub-workflow, chat trigger. Severity of issues changes by trigger (a webhook-API workflow needs error paths; a manual run does not).
- [ ] **Note whether the workflow is active.** Active/published workflows with broken connections are higher severity.

---

## MUST FIX

### Credentials and secrets

- [ ] **Tokens, API keys, or secrets in node text fields.** Any node parameter holding `Bearer xxx`, `sk-...`, an API key, or a password as plain text. The credential system is the only correct home. → [n8n-credentials-and-security-official](../../n8n-credentials-and-security-official/SKILL.md)
- [ ] **Tokens stored in Set node values** for later `{{$json.token}}` referencing. The token is in workflow JSON regardless of how it's read. → [n8n-credentials-and-security-official](../../n8n-credentials-and-security-official/SKILL.md)
- [ ] **Hardcoded credentials in Code nodes.** Same leak surface as text fields. → [n8n-code-nodes-official anti-patterns](../../n8n-code-nodes-official/SKILL.md)
- [ ] **HTTP Request nodes with `Authorization` header values typed in directly** instead of using a credential. For `Authorization: Bearer <token>`, use `Bearer Auth` (`httpBearerAuth`) so the token is stored without the prefix. For other custom auth headers, use `Header Auth` (`httpHeaderAuth`). → [HTTP_REQUEST_WITH_AUTH.md](../../n8n-credentials-and-security-official/references/HTTP_REQUEST_WITH_AUTH.md)
- [ ] **Secret read from `$vars.X` and used as an auth value.** Use a credential instead. → [n8n-credentials-and-security-official](../../n8n-credentials-and-security-official/SKILL.md)

### SQL / query injection

- [ ] **User input interpolated into a query string.** Any DB node with `parameters.query` containing `{{ $json.something }}` (or any `{{ ... }}` expression that resolves from caller input) inside the SQL itself is a SQL injection: n8n substitutes the expression into the query *before* parameter binding. Use parameter binding instead (Postgres / MySQL: `$1, $2` placeholders + `parameters.options.queryReplacement`; Mongo: object filters). → [DATABASE_NODES.md](../../n8n-node-configuration-official/references/DATABASE_NODES.md)

### Connection bugs (silent breakage)

- [ ] **Merge index off-by-one.** `parameters.useDataOfInput` is 1-indexed but the corresponding entry in `connections.<source>.main[index]` is 0-indexed. If the merge node's expected primary input doesn't match the wiring, the wrong source is picked silently. → [MERGE_NODE.md](../../n8n-node-configuration-official/references/MERGE_NODE.md)
- [ ] **Merge with 3+ sources but `numberOfInputs` left at default 2.** Third source silently drops. → [MERGE_NODE.md](../../n8n-node-configuration-official/references/MERGE_NODE.md)
- [ ] **Error output wired without `onError: 'continueErrorOutput'`** on the node config. Error branch is unreachable; node failure halts the workflow. → [NODE_ERROR_OUTPUTS.md](../../n8n-error-handling-official/references/NODE_ERROR_OUTPUTS.md)
- [ ] **`onError: 'continueErrorOutput'` set but `main[1]` not wired.** Error path is enabled but goes nowhere. → [NODE_ERROR_OUTPUTS.md](../../n8n-error-handling-official/references/NODE_ERROR_OUTPUTS.md)

### Webhook API workflows (Webhook + Respond to Webhook)

- [ ] **Webhook performs a sensitive action with `parameters.authentication: 'none'`.** "Sensitive" = mutates state, sends external messages, hits production data, exposes private info, triggers paid actions. Anyone with the URL can fire it. Set `parameters.authentication` to `'basicAuth'` or `'headerAuth'` and use the matching credential. → [n8n-credentials-and-security-official](../../n8n-credentials-and-security-official/SKILL.md)

### Sub-workflow contracts

- [ ] **`Execute Workflow Trigger` set to `passthrough` when it shouldn't be.** Passthrough loses the typed-input contract that agent tools (`fromAi()`) and structured callers need. Only correct when (a) the sub-workflow specifically receives binary AND isn't an agent tool, or (b) the sub-workflow takes no inputs (Define Below requires at least one field). For (b), the body should open with a `Set` ("Keep Only Set", no fields) and the trigger should carry a sticky noting no inputs are expected. → [n8n-subworkflows-official non-negotiables](../../n8n-subworkflows-official/SKILL.md) and [SUBWORKFLOW_PATTERNS.md "Splitting by input shape"](../../n8n-subworkflows-official/references/SUBWORKFLOW_PATTERNS.md)

### Chat-triggered agents (Slack / Discord / Teams / Telegram)

- [ ] **Bot's own user ID not filtered out**, either via the trigger's own filter option (preferred: Slack's `options.userIds` exclusion list) or as the first node after the trigger. The bot's reply re-triggers the workflow → infinite loop. Watch out for surface-specific semantics: Telegram's `userIds` is an allowlist, not an exclusion list. → [CHAT_AGENT_PATTERNS.md](../../n8n-agents-official/references/CHAT_AGENT_PATTERNS.md)

---

## SHOULD FIX

### Naming

- [ ] **Generic node names** (`HTTP Request1`, `Set2`, `Postgres1`). Debugging-hostile: a failure on `node "HTTP Request3"` tells the operator nothing, but `node "Fetch order details"` localizes the break instantly. Rename every node to describe what it *does in this workflow*. → [NAMING_CONVENTIONS.md](NAMING_CONVENTIONS.md)

### Comms nodes (Slack, Gmail, Discord, SMTP, Telegram)

- [ ] **n8n attribution still appended** on Slack / Gmail / Email / Discord nodes. Most comms nodes have "Append n8n Attribution" enabled by default. Users typically want it removed in production. → [COMMS_NODES.md](../../n8n-node-configuration-official/references/COMMS_NODES.md)
- [ ] **Slack thread reply posting as top-level message.** `thread_ts` not set, or set in the wrong nested location. → [COMMS_NODES.md](../../n8n-node-configuration-official/references/COMMS_NODES.md)

### Set node antipattern

- [ ] **Set node feeding only 0 or 1 downstream consumer.** Most common antipattern in the pack. Delete + inline the expression at the consumer. → [n8n-expressions-official "The Set-node antipattern"](../../n8n-expressions-official/SKILL.md)
- [ ] **Set node before a Data Table Insert/Update mapping fields to schema.** Map directly in the Data Table node's per-column expression slots. → [n8n-data-tables-official strong defaults](../../n8n-data-tables-official/SKILL.md)
- [ ] **Set node building an email/Slack body.** Build the body inline in the comms node's body field with an expression. → [COMMS_NODES.md](../../n8n-node-configuration-official/references/COMMS_NODES.md)
- [ ] **Multiple consecutive Set nodes each defining one field.** Collapse, or eliminate. → [n8n-expressions-official](../../n8n-expressions-official/SKILL.md)

### Code node antipattern

- [ ] **Code node doing pure data shaping** (`.map`, `.filter`, `.find`, field rename, optional chaining). Use an expression or Edit Fields with arrow function. → [n8n-code-nodes-official decision tree](../../n8n-code-nodes-official/SKILL.md)
- [ ] **Code node using `crypto.createHash` / `crypto.createHmac`.** Use the native Crypto node (`n8n-nodes-base.crypto`). Recurring AI slip. → [n8n-code-nodes-official "Cryptographic operations"](../../n8n-code-nodes-official/SKILL.md)
- [ ] **Code node parsing XML / SOAP / RSS.** Use the native XML node + Edit Fields with arrow function for extraction. → [n8n-code-nodes-official "XML / SOAP / RSS parsing"](../../n8n-code-nodes-official/SKILL.md)
- [ ] **Code node + Set node combo** (Set builds inputs, Code transforms). One Edit Fields with arrow function does both. → [ARROW_FUNCTIONS_IN_EDIT_FIELDS.md](../../n8n-code-nodes-official/references/ARROW_FUNCTIONS_IN_EDIT_FIELDS.md)

### Expression discipline

- [ ] **`$json.x` references deep in workflows with branches/intermediates.** Switch to `$('Source Node').item.json.x` for refactor stability. → [n8n-expressions-official non-negotiable](../../n8n-expressions-official/SKILL.md)
- [ ] **DateTime nodes used for date math/formatting.** Use Luxon expressions (`DateTime.fromISO(...)`) inline. → [n8n-expressions-official strong defaults](../../n8n-expressions-official/SKILL.md)
- [ ] **`$env.X` referenced in any expression.** Doesn't work, throws at runtime. Replace with `$vars.X` (paid plans), a Data Table, or a credential for secrets. → [n8n-expressions-official anti-patterns](../../n8n-expressions-official/SKILL.md)
- [ ] **Aggregate node + per-item execution mismatch.** Expressions using `$input.all()` / `$('Node').all()` *without* combining with another node's `.item` should set `executeOnce: true` on the node. → [n8n-loops-official non-negotiable](../../n8n-loops-official/SKILL.md) and [n8n-expressions-official ".all().map() triggers an executeOnce question"](../../n8n-expressions-official/SKILL.md)

### Execution model

- [ ] **Workflow assumes fan-out branches execute in parallel.** They don't, n8n runs them sequentially top-to-bottom by Y-position. Real concurrency needs sub-workflow dispatch with `mode: 'each'` + `waitForSubWorkflow: false`. → [n8n-workflow-lifecycle-official "Execution model"](../SKILL.md)

### Loops

- [ ] **`Loop Over Items` added "to make it loop"** when default per-item iteration handles it. Default per-item iteration already waits for each item before the next, so a Loop Over Items added "to wait for all items" is unnecessary. → [n8n-loops-official "When NOT to reach for Loop Over Items"](../../n8n-loops-official/SKILL.md)
- [ ] **Custom pagination implementation** (Loop Over Items + `$pageCount`, hand-rolled `while` in a Code node, Set + IF cycle, etc.) instead of HTTP Request's built-in `Pagination` option. → [HTTP_PAGINATION.md](../../n8n-loops-official/references/HTTP_PAGINATION.md)
- [ ] **Reset-mode loop with no clear termination.** `reset: true` without an explicit stop condition + `$runIndex` ceiling = infinite loop, n8n eats memory until killed. → [LOOP_OVER_ITEMS.md "Reset mode"](../../n8n-loops-official/references/LOOP_OVER_ITEMS.md)
- [ ] **One `Loop Over Items` nested inside another in the same workflow.** Doesn't work; breaks at runtime. Move the inner loop into a sub-workflow called per outer iteration (`mode: 'each'`). → [LOOP_OVER_ITEMS.md "Nesting Loop Over Items"](../../n8n-loops-official/references/LOOP_OVER_ITEMS.md)

### Self-healing on transient failures

- [ ] **Network-calling nodes (HTTP, comms, DB, AI) without `retryOnFail` configured.** Transient 429s and upstream blips surface as 5xx, alerts fire on noise. → [n8n-error-handling-official "Self-healing on transient failures"](../../n8n-error-handling-official/SKILL.md)

### Switch nodes

- [ ] **Switch with no fallback output configured.** Unmatched items silently drop. Set `options.fallbackOutput: 'extra'` and `options.renameFallbackOutput: '<name>'`. → [SWITCH_FALLBACK.md](../../n8n-node-configuration-official/references/SWITCH_FALLBACK.md)
- [ ] **Switch outputs unnamed.** Set `renameOutput: true` + `outputKey: '<name>'` per rule for self-documenting branches. → [SWITCH_FALLBACK.md](../../n8n-node-configuration-official/references/SWITCH_FALLBACK.md)

### Sub-workflows

- [ ] **Duplicated logic across workflows** that would be a sub-workflow. → [n8n-subworkflows-official decision tree](../../n8n-subworkflows-official/SKILL.md)
- [ ] **Sub-workflow with no `description`.** Won't be found in future searches; nobody (or AI) knows what it does. → [n8n-subworkflows-official anti-patterns](../../n8n-subworkflows-official/SKILL.md)
- [ ] **Sub-workflow has hidden side effects.** The name and `description` describe pure logic (parse, validate, format, compute, transform), but the body contains write / send nodes (Data Table Insert/Update, Slack/Gmail/Discord send, HTTP POST, file write, audit log, etc.). Callers reasonably assume the sub-workflow is safe to retry; doing so creates duplicate writes or sends. Either declare the side effect (rename to e.g. `Audit:` or `<Domain>:`, document it in `description`, return a result the caller can branch on) or move the side effect out of this sub-workflow. → [n8n-subworkflows-official "Stateless vs stateful"](../../n8n-subworkflows-official/SKILL.md)
- [ ] **~30-node workflow with no extraction.** Extract logical sections into sub-workflows. → [n8n-subworkflows-official](../../n8n-subworkflows-official/SKILL.md)

### AI Agents and tools

- [ ] **`options.maxIterations` left at default 10 on a multi-tool agent.** Likely too low for modern agents with flexible tool sets; throws "Max iterations reached" workflow error. Raise to 30-50+. → [AI_NODES.md "Iteration cap"](../../n8n-node-configuration-official/references/AI_NODES.md)
- [ ] **Generic tool names (`doStuff`, `runQuery`).** Model can't tell which tool to pick, skips them or hallucinates parameters. Use verb-first specific names. → [TOOLS.md](../../n8n-agents-official/references/TOOLS.md)
- [ ] **Default, Empty, or one-line tool descriptions.** Model has no clue when to invoke. Tool descriptions are part of the prompt. → [TOOLS.md](../../n8n-agents-official/references/TOOLS.md)
- [ ] **`outputParserStructured` without `autoFix: true`.** One bad model output and the workflow fails. Set `autoFix: true` with a coding-capable fixer model. → [STRUCTURED_OUTPUT.md](../../n8n-agents-official/references/STRUCTURED_OUTPUT.md)
- [ ] **Tools with user-visible side effects (send, pay, refund) without human review.** Wrap with `slackHitlTool` / `discordHitlTool` / `telegramHitlTool` / `gmailHitlTool` / etc. → [HUMAN_REVIEW.md](../../n8n-agents-official/references/HUMAN_REVIEW.md)
- [ ] **Approval message via `fromAi()` instead of `$tool.parameters.<name>`.** Model paraphrases; you approve text not values. → [HUMAN_REVIEW.md](../../n8n-agents-official/references/HUMAN_REVIEW.md)
- [ ] **Hardcoded `sessionId: 'default'` or no sessionId** on memory. All conversations share one session or sessions won't be used properly. → [MEMORY.md](../../n8n-agents-official/references/MEMORY.md)
- [ ] **Image / audio / video generation wrapped in an Agent.** Binary doesn't flow through tools or the Agent's output formatter. Use the provider's native single-call node directly. → [n8n-agents-official anti-patterns](../../n8n-agents-official/SKILL.md)
- [ ] **Agent + Switch to route on natural-language input** when Text Classifier (`@n8n/n8n-nodes-langchain.textClassifier`) is one node with N built-in branches. → [n8n-agents-official](../../n8n-agents-official/SKILL.md)
- [ ] **Agent (or Basic LLM Chain + structured output parser) used to pull fields out of a blob of text** when Information Extractor (`@n8n/n8n-nodes-langchain.informationExtractor`) is one node with a typed schema, no tools, no system prompt. Use the Agent only when the extraction needs tool calls or multi-turn reasoning. → [n8n-agents-official](../../n8n-agents-official/SKILL.md)

### System prompts (AI Agents)

The system prompt is the load-bearing config of an agent. Severity ranges by how badly the issue degrades behavior.

- [ ] **Hardcoded date / missing date in the system prompt.** Stale immediately. Agents making time-sensitive decisions (deadlines, eligibility windows, "is X expired?") get wrong answers. Use `Current date: {{ $now }}`. → [SYSTEM_PROMPT.md "Always include the current date"](../../n8n-agents-official/references/SYSTEM_PROMPT.md)
- [ ] **Long system prompt with per-tool usage instructions buried inside.** Modular split violation. Brittle to edit, and tools become unreusable across agents. Move tool-specific instructions into each tool's description. → [SYSTEM_PROMPT.md "The modular split"](../../n8n-agents-official/references/SYSTEM_PROMPT.md) and [n8n-agents-official "What goes in the system prompt vs the tool description"](../../n8n-agents-official/SKILL.md)
- [ ] **"You are a helpful assistant" preamble with no role specifics.** Generic responses, agent has no identity. Replace with a specific role and scope. → [SYSTEM_PROMPT.md "What it's for"](../../n8n-agents-official/references/SYSTEM_PROMPT.md)
- [ ] **No refusal/safety boundary** when one is needed (the agent has tools that touch user-visible state, sends, payments). Define explicit boundaries: "only answer questions about X, redirect otherwise". → [SYSTEM_PROMPT.md](../../n8n-agents-official/references/SYSTEM_PROMPT.md)

### Data Tables

**System columns and identifiers**

- [ ] **Set node before Data Table Insert/Update.** Map directly in per-column slots. → [n8n-data-tables-official strong defaults](../../n8n-data-tables-official/SKILL.md)
- [ ] **`id`, `createdAt`, or `updatedAt` declared in `create_data_table`.** System-managed; declaring them errors or shadows. → [n8n-data-tables-official non-negotiable](../../n8n-data-tables-official/SKILL.md)
- [ ] **Auto-`id` used as a cross-system identifier.** Resets on table recreate / instance migration. Add a domain ID column (`arxivId`, `customerId`, `requestId`). → [SCHEMA_DESIGN.md "system-managed columns"](../../n8n-data-tables-official/references/SCHEMA_DESIGN.md)

**`_object` postfix discipline (the most error-prone area)**

- [ ] **Column holds stringified JSON (array, object) without the `_object` postfix.** Readers have no contract telling them to parse. → [SCHEMA_DESIGN.md "the `_object` convention"](../../n8n-data-tables-official/references/SCHEMA_DESIGN.md)
- [ ] **Column has `_object` postfix but is `string` type holding native (non-stringified) values.** Contract violation: postfix promises stringified content. → [SCHEMA_DESIGN.md](../../n8n-data-tables-official/references/SCHEMA_DESIGN.md)
- [ ] **Insert/Update writes to an `_object` column without `JSON.stringify(...)`.** A `[object Object]` literal lands in the row. → [SCHEMA_DESIGN.md](../../n8n-data-tables-official/references/SCHEMA_DESIGN.md)
- [ ] **Read from an `_object` column without `JSON.parse(...)`.** Downstream gets a string where it expects array/object; templates and tools choke. → [SCHEMA_DESIGN.md](../../n8n-data-tables-official/references/SCHEMA_DESIGN.md)
- [ ] **Sub-workflow returns `_object` columns as strings to callers.** Storage format leaking through the interface. Parse before returning so callers receive arrays as arrays and objects as objects. → [SCHEMA_DESIGN.md "Storage format ≠ interface format"](../../n8n-data-tables-official/references/SCHEMA_DESIGN.md)
- [ ] **Sub-workflow's "fresh" path stringifies to "match" the cached path.** Wrong instinct. Parse the cached path so both branches return natural shapes. → [SCHEMA_DESIGN.md](../../n8n-data-tables-official/references/SCHEMA_DESIGN.md)
- [ ] **`_object` column holds data that needs to be queried** (filter on `topics` content, find rows by tag). Strings can't be queried structurally. Refactor to a relational child table or move to a real DB. → [SCHEMA_DESIGN.md "When NOT to use `_object`"](../../n8n-data-tables-official/references/SCHEMA_DESIGN.md)

**Schema design**

- [ ] **String column acting as boolean** (`'yes'/'no'`, `'true'/'false'`). Use the `boolean` type. → [SCHEMA_DESIGN.md "Picking column types"](../../n8n-data-tables-official/references/SCHEMA_DESIGN.md)
- [ ] **Mixed casing within one table or query** (`createdAt` AND `arxiv_id` together). Match camelCase to the system columns. → [n8n-data-tables-official strong defaults](../../n8n-data-tables-official/SKILL.md)
- [ ] **Table named with snake_case, lowercase, or in singular for a set.** Title Case with spaces (`Papers`, `Recent Events`). Plural for sets, singular for one-row-per-global-thing only. → [SCHEMA_DESIGN.md "Naming"](../../n8n-data-tables-official/references/SCHEMA_DESIGN.md)
- [ ] **Boolean column not named affirmatively** (`completed` instead of `isCompleted`). Affirmative names read better in filters and IFs. → [SCHEMA_DESIGN.md](../../n8n-data-tables-official/references/SCHEMA_DESIGN.md)
- [ ] **Table with more than ~17 columns.** Consider splitting; the table is probably trying to be multiple things. → [SCHEMA_DESIGN.md "A healthy table"](../../n8n-data-tables-official/references/SCHEMA_DESIGN.md)
- [ ] **User-declared `date` column duplicates `createdAt` / `updatedAt`.** Use the system columns where they fit; only add explicit `date` columns when the timestamp's meaning differs from "row created" or "row updated". → [SCHEMA_DESIGN.md](../../n8n-data-tables-official/references/SCHEMA_DESIGN.md)

**Relational design (when the data has shape)**

- [ ] **Genuine parent-child data crammed into one wide table** (papers + summaries in one `Papers` table, customers + orders in one `Customers` table). Split into parent + child tables, reference parent by `id` (`paperId`, `customerId`). → [SCHEMA_DESIGN.md "Designing relationally"](../../n8n-data-tables-official/references/SCHEMA_DESIGN.md) and [n8n-data-tables-official "Relational design"](../../n8n-data-tables-official/SKILL.md)
- [ ] **Child arrays stored in `_object` columns when they need to be queried or filtered individually.** Refactor to a relational child table. → [SCHEMA_DESIGN.md "When NOT to use `_object`"](../../n8n-data-tables-official/references/SCHEMA_DESIGN.md)
- [ ] **Cascade strategy unclear** (no defined behavior on parent delete). Pick one per relationship: cascade-delete via a separate Delete on children, soft-delete (`archived` flag), or orphan. Mixed strategies cause silent bugs. → [SCHEMA_DESIGN.md "Enforce integrity in the workflow"](../../n8n-data-tables-official/references/SCHEMA_DESIGN.md)
- [ ] **Multi-table write sequence (parent Insert + child Insert) without partial-failure handling.** No transactions exist; a child failure leaves the parent orphaned. Pick: compensating writes, idempotent retry with `upsert` + stable domain IDs, or soft state marker (`status: 'pending' → 'complete'`). → [SCHEMA_DESIGN.md "No transactions, plan for partial failure"](../../n8n-data-tables-official/references/SCHEMA_DESIGN.md)
- [ ] **Child rows pointing at deleted parents** (orphan detection missing). Either soft-delete by default, or run a periodic cleanup workflow. → [SCHEMA_DESIGN.md "Watch for child without parent"](../../n8n-data-tables-official/references/SCHEMA_DESIGN.md)
- [ ] **3+ joined tables with transactional writes.** Past Data Tables' wheelhouse. Use a real SQL DB. → [SCHEMA_DESIGN.md "When Data Tables are the wrong tool"](../../n8n-data-tables-official/references/SCHEMA_DESIGN.md)

**Operation gotchas**

- [ ] **Multi-column filter without explicit `matchType: 'allConditions'`.** Defaults to `anyCondition` (OR) in some versions; surprising when intent is AND. → [OPERATIONS.md "matchType"](../../n8n-data-tables-official/references/OPERATIONS.md)
- [ ] **`Get` without `alwaysOutputData: true` followed by an IF** that branches on result presence. No-match produces zero items, the IF doesn't fire at all. → [DEDUP_PATTERNS.md "Pattern 3: Get + IF"](../../n8n-data-tables-official/references/DEDUP_PATTERNS.md)
- [ ] **Get + IF branches produce different JSON shapes** (cached path vs. freshly-processed path). Downstream `$json.x` resolves to the wrong field depending on which fired. Insert a Set/NoOp anchor to normalize. → [n8n-expressions-official "Combine Inputs convergence"](../../n8n-expressions-official/SKILL.md)
- [ ] **`Update` with no match silently does nothing.** No error. Either follow with a `Get` to confirm, or use `upsert` for create-or-update. → [OPERATIONS.md "Update with no match"](../../n8n-data-tables-official/references/OPERATIONS.md)
- [ ] **`Insert` with no dedup in a workflow that can re-fire** (webhook retry, scheduled re-run). Creates duplicates. Use `upsert`, `rowNotExists` + Insert, or upstream dedup. → [DEDUP_PATTERNS.md](../../n8n-data-tables-official/references/DEDUP_PATTERNS.md)
- [ ] **`returnAll: false` without explicit `limit`.** Defaults to 50 in many versions; downstream may expect more and silently truncate. → [OPERATIONS.md "returnAll"](../../n8n-data-tables-official/references/OPERATIONS.md)
- [ ] **Plain "have I seen this value?" dedup using a Data Table.** The `Remove Duplicates` node ("items seen in previous executions" mode) handles this with no schema. Reach for Data Tables only when the dedup state needs to be queryable, has row-level logic, or has TTL/per-tenant scoping. → [DEDUP_PATTERNS.md](../../n8n-data-tables-official/references/DEDUP_PATTERNS.md)
- [ ] **Idempotency-key workflow without TTL cleanup.** Markers shouldn't live forever; run a daily cleanup. → [DEDUP_PATTERNS.md "Idempotency keys"](../../n8n-data-tables-official/references/DEDUP_PATTERNS.md)

**Mapping mode and evolution**

- [ ] **`autoMapInputData` mode without a stable 1:1 between upstream field names and column names.** Drift on either side silently breaks the mapping. Default to `defineBelow`. → [SCHEMA_DESIGN.md "Mapping mode"](../../n8n-data-tables-official/references/SCHEMA_DESIGN.md)
- [ ] **Workflow attempts an in-place column type change.** Not supported. Add a new column, copy via workflow, drop the old, rename the new. → [SCHEMA_DESIGN.md "Schema evolution"](../../n8n-data-tables-official/references/SCHEMA_DESIGN.md)

**Wrong tool for the job**

- [ ] **Cross-app shared data in Data Tables.** Awkward to query from outside n8n. Use a real DB. → [SCHEMA_DESIGN.md "When Data Tables are the wrong tool"](../../n8n-data-tables-official/references/SCHEMA_DESIGN.md)
- [ ] **Millions of rows or write-heavy volume in a Data Table.** Performance degrades; use a real DB. → [SCHEMA_DESIGN.md](../../n8n-data-tables-official/references/SCHEMA_DESIGN.md)

### Binary handling

- [ ] **Reading file content from `$json` instead of `$binary`.** → [BINARY_BASICS.md](../../n8n-binary-and-data-official/references/BINARY_BASICS.md)
- [ ] **Agent tool returning raw binary directly.** Tool output is JSON-only. Upload to storage, return key/URL in JSON. → [AGENT_TOOL_BINARY.md](../../n8n-binary-and-data-official/references/AGENT_TOOL_BINARY.md)
- [ ] **Uploaded chat files passed to a tool via `fromAi`.** `fromAi` doesn't carry binary. Pre-stage to storage, inject keys in the system prompt. → [AGENT_TOOL_BINARY.md](../../n8n-binary-and-data-official/references/AGENT_TOOL_BINARY.md)
- [ ] **Binary lost after a JSON transform.** Use Merge to combine the JSON output with the binary stream. → [MERGE_FOR_CONTEXT.md](../../n8n-binary-and-data-official/references/MERGE_FOR_CONTEXT.md)
- [ ] **Image sent to a chat surface from raw `$binary`.** Chat surfaces need a URL-referenced image (or platform-native file upload). → [CDN_REQUIREMENT.md](../../n8n-binary-and-data-official/references/CDN_REQUIREMENT.md)

### Public trigger auth

- [ ] **Webhook trigger with `parameters.authentication: 'none'`** even on read-only / lookup paths. The URL is publicly callable; no auth invites abuse (rate-limit exhaustion, scanning, scraping). Use Basic / Header / JWT auth unless the workflow is genuinely meant to be public. (If the action is sensitive, this is a MUST FIX, see above.) → [n8n-credentials-and-security-official](../../n8n-credentials-and-security-official/SKILL.md)
- [ ] **Form Trigger fronting a sensitive action with no auth gate.** Forms that create accounts, mutate data, send external messages, or trigger paid operations should require real auth at the trigger. An obscure URL is not auth. → [n8n-credentials-and-security-official](../../n8n-credentials-and-security-official/SKILL.md)

### Webhook / Respond to Webhook

- [ ] **Fallible nodes with no error path.** HTTP / DB / API / file nodes need `output(1)` wired to a 5xx Respond. Without it, the failure is unhandled: the workflow halts and the caller gets whatever n8n's generic error response is (no controlled status code, no useful body), and the operator only learns about it if a workflow-level error workflow is configured separately. → [n8n-error-handling-official non-negotiables](../../n8n-error-handling-official/SKILL.md) and [API_WORKFLOWS.md](../../n8n-error-handling-official/references/API_WORKFLOWS.md)
- [ ] **Error response returns 200.** Caller's HTTP client treats it as success; downstream error handling never fires. Always 4xx (caller error) or 5xx (server error). → [RESPONSE_SHAPES.md](../../n8n-error-handling-official/references/RESPONSE_SHAPES.md)
- [ ] **Generic 500 for every failure.** Validation errors should be 400, auth issues 401/403, conflicts 409, rate limits 429. Caller can't distinguish their bug from your outage. → [RESPONSE_SHAPES.md](../../n8n-error-handling-official/references/RESPONSE_SHAPES.md)
- [ ] **`respondWith: 'json'` body using `JSON.stringify(...)`** instead of an object literal (produces double-encoded body). → [WEBHOOK_NODES.md](../../n8n-node-configuration-official/references/WEBHOOK_NODES.md)

### HTTP Request

- [ ] **Headers set both via `headerParameters` and a credential's `httpHeaderAuth`.** They conflict. → [HTTP_NODES.md](../../n8n-node-configuration-official/references/HTTP_NODES.md)
- [ ] **Untrusted external API call without `options.timeout` set.** Runtime default is 5 minutes; a hung request stalls the workflow. → [HTTP_NODES.md](../../n8n-node-configuration-official/references/HTTP_NODES.md)

### Schedule trigger

- [ ] **Business-critical schedule with no explicit timezone** at the workflow level. DST and instance moves cause timing shifts. → [TRIGGER_NODES.md](../../n8n-node-configuration-official/references/TRIGGER_NODES.md)
- [ ] **Schedule-triggered workflow not idempotent** for missed-run scenarios. Restarts or downtime can miss runs. → [TRIGGER_NODES.md](../../n8n-node-configuration-official/references/TRIGGER_NODES.md)

---

## NICE TO HAVE

### Naming

- [ ] **Workflow name doesn't follow verb-first pattern** (`Send weekly customer report` vs. `Customer report sender`). → [NAMING_CONVENTIONS.md](NAMING_CONVENTIONS.md)
- [ ] **Untagged sub-workflow** (missing `subworkflow`, a domain tag, or `tool`). Tags are the discovery mechanism; an untagged sub-workflow won't surface under any `tags` filter. → [NAMING_AND_DISCOVERY.md](../../n8n-subworkflows-official/references/NAMING_AND_DISCOVERY.md)

### Readability

- [ ] **Workflow over ~5 nodes with no sticky notes.** Reader has to read every node to find what they want. → [SKILL.md "Readability"](../SKILL.md)
- [ ] **Workflow over ~10 nodes (n8n 2.28+) whose logical steps aren't grouped into node groups.** Collapsed groups make the canvas read as steps, not nodes. Skip on older instances, where node groups don't exist. → [SKILL.md "Readability"](../SKILL.md)
- [ ] **Sticky title re-states what's visible** (`Set, If, Set` vs. `Validate input`). Title with the *purpose*. → [SKILL.md "Readability"](../SKILL.md)
- [ ] **Sticky colors used inconsistently.** One color per category (processing / errors / TODOs); otherwise color is noise. → [SKILL.md "Readability"](../SKILL.md)
- [ ] **Workflow `description` is empty, one sentence, or doesn't capture the *why*.** Two sentences: what it does, why it exists. → [SKILL.md "Readability"](../SKILL.md)
- [ ] **Code node without a one-line note** explaining its purpose. → [SKILL.md "Readability"](../SKILL.md)
- [ ] **Workflow ignores existing house style** (sticky palette, naming convention used in nearby workflows). Match what's there. → [SKILL.md "Readability"](../SKILL.md)

### Sub-workflow conventions

- [ ] **Sub-workflow without a final `Return` Set / Edit Fields node** shaping the return contract. The legitimate exception to the Set-node antipattern. → [n8n-subworkflows-official "Other conventions"](../../n8n-subworkflows-official/SKILL.md)
- [ ] **Inputs / outputs not documented in the sub-workflow's `description`.** Field names, types, purpose. → [n8n-subworkflows-official "Sub-workflow inputs and outputs"](../../n8n-subworkflows-official/SKILL.md)

### Conventions

- [ ] **Per-execution context (user identity, files, current task) buried in a static system prompt** instead of injected via expressions or piecing. Hard to update. → [SYSTEM_PROMPT.md "Storing the prompt"](../../n8n-agents-official/references/SYSTEM_PROMPT.md)
- [ ] **Generic safety boilerplate language** in the system prompt for risks the model already handles. Reinforcement adds tokens without changing behavior. Reserve safety language for specific, named risks. → [SYSTEM_PROMPT.md anti-patterns](../../n8n-agents-official/references/SYSTEM_PROMPT.md)

---

## Reporting findings

When reporting, group by severity, then within severity by domain. For each finding include:

- The specific node(s) or section affected.
- A one-sentence description of the issue.
- The link to the canonical skill ref for the fix.

```
MUST FIX
  Security
  - Node `Send Webhook`: bearer token in headerParameters value field. → n8n-credentials-and-security-official
  - Node `Lookup user`: SQL string concat with $json.email. → DATABASE_NODES.md

  Connections
  - Node `Validate input`: `connections.Validate input.main[0]` has only 1 entry, but the workflow's logic expects fan-out to 3 downstreams. → check the SDK code (likely a missed `.add(...)` call)

SHOULD FIX
  ...
```

A review agent should not auto-fix MUST FIX items without user confirmation: security and connection fixes have blast radius and the user should know what's changing.
