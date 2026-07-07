---
name: n8n-data-tables-official
description: Use when working with n8n's built-in Data Tables, designing schemas, inserting/updating/upserting rows, deduping, or querying. Triggers on "Data Table", "data table", `n8n-nodes-base.dataTable`, "dedup", "idempotency", "lookup", "persistent state", "store across executions", or any schema design discussion inside n8n.
---

# n8n Data Tables

Data Tables are n8n's **built-in tabular storage**: real tables inside the n8n instance with columns, types, rows, and CRUD via the `dataTable` node and data-table MCP tools.

Use them for local persistent state: lookup tables, recent events, per-session inventories, counters, idempotency tracking, dedup state when there's row-level logic or external visibility (plain "have I seen this value?" dedup belongs in the `Remove Duplicates` node). Small-to-moderate volume (tens of thousands of rows fine, millions belong in a real DB).

## Non-negotiables

1. **System-managed columns + external IDs.** Three columns auto-exist on every table: `id` (bigserial), `createdAt`, `updatedAt`. Don't declare them in `create_data_table` (errors or shadows the system column). Don't write them on insert. For domain identifiers from outside (arxivId, stripeCustomerId, requestId), add a separate column and key dedup/lookup on that.
2. **Only primitives in columns, nested data uses `string` + `_object` postfix.** No JSON/object/array column types exist. For nested data (arrays, parsed objects), use a `string` column with `JSON.stringify(...)` on write and `JSON.parse(...)` on read. Mark the column with `_object` (e.g., `keyInsights_object`). The postfix is the contract that tells readers to parse. See `references/SCHEMA_DESIGN.md`.

## Strong defaults

- **Don't add a Set node before a Data Table node to modify fields.** The Data Table node's per-column expression slots are just as powerful as Set fields, so the Set node is doing zero work the Data Table node can't do itself. (Same Set-node antipattern called out in `n8n-expressions-official`.)
- **Match n8n's column casing: camelCase.** The auto-managed columns are camelCase (`createdAt`, `updatedAt`), so user columns read more cleanly when they match: `arxivId`, `paperId`, `taxRate`. Mixed casing in the same query (`createdAt >= ... AND arxiv_id eq ...`) reads as a typo. Keep the `_object` postfix on stringified-blob columns regardless (`keyInsights_object`), the underscore is a contract marker, not casing.
<!-- TEMPORARY: remove when the data tables node quirk is fixed -->
- **Verify the `columns` parameter via `get_workflow_details` after create/update.** The UI has a display quirk in manual mapping mode ("Currently no items exist" with no actual data loss). Checking the JSON confirms what's persisted.
- **Relational design works when the shape calls for it.** For genuine parent-child data (papers → summaries, customers → orders), reference parents by `id`, name columns explicitly (`paperId`, `customerId`), and enforce integrity in workflow logic. Don't force it on flat use cases (dedup, lookup, audit) where there's no relationship to model.
- **Storage format is not interface format.** Parse `_object` fields *before* returning them from a sub-workflow. Callers should never receive stringified shells they have to parse themselves. See `references/SCHEMA_DESIGN.md` "Storage format ≠ interface format".

## The default columns

Every Data Table has these whether you declare them or not:

| Column | Type | Behavior |
|---|---|---|
| `id` | bigserial / number | Auto-incrementing primary key. n8n assigns on insert, and you can't write to it. Returned in the insert response. |
| `createdAt` | timestamp | Set automatically on insert. |
| `updatedAt` | timestamp | Refreshed automatically on each update. |

In practice:

- **Don't declare them** in `create_data_table`. Already there.
- **Use them in queries** without your own timestamp columns. "Created today": `createdAt >= '<today ISO>'`. "Updated since last sync": `updatedAt >= $('Last Sync').item.json.timestamp`.
- **Don't use them as cross-system identifiers.** Auto-`id` is internal, and resets on table recreate or instance migration. For domain identifiers, use your own column.

## Relational design when the shape calls for it

Data Tables don't enforce foreign keys, but you can still model parent-child data across tables when the data genuinely has that shape. The catch: integrity is your responsibility, not n8n's.

- **Reference parent rows by `id`.** A child table holds the parent's `id` in a column.
- **Document references in column names.** `paperId`, `customerId`, `eventId` make the relationship obvious.
- **Enforce integrity in workflow logic.** Before inserting a child, look up the parent. Before deleting a parent, decide what happens to children (delete, orphan, archive). n8n won't cascade.
- **Watch for stale references.** Children pointing at deleted parents are silent bugs. Soft-delete, or run cleanup workflows.

For complex relational structure (3+ tables with joins, transactional writes), reach for an actual SQL DB.

## Operations: which one for what

| Operation | When |
|---|---|
| `insert` | Always-add. New row, n8n assigns `id`. |
| `upsert` | "Add if new, update if exists." Needs a `matchType` and filter to decide existence. |
| `update` | "Modify rows matching this filter." No insert if no match. |
| `get` | Fetch rows matching a filter (returns 0+). Supports `orderBy`, `limit`, `returnAll`. |
| `deleteRows` | Remove rows matching a filter. |
| `rowExists` / `rowNotExists` | Boolean-style filter against incoming items. Common for dedup branching. |

For the full operation surface (filter syntax, matchType, sort patterns), see `references/OPERATIONS.md`.

<!-- TEMPORARY: remove when the data tables node quirk is fixed -->
## The "Currently no items exist" UI quirk

When the SDK saves manual-mode column mappings (`mappingMode: 'defineBelow'`), the n8n UI's "Values to insert" pane can render empty ("Currently no items exist") even though runtime persists data correctly. If the user reports the Insert node "looks broken" or "has no fields," tell them: it's a UI display issue, press the reload (refresh) button on the columns parameter, and it repopulates the schema and the mappings render. No data loss, safe to do anytime.

<!-- TEMPORARY: SDK-saved defineBelow column mappings can render as "Currently no items exist" in the n8n UI until the user clicks the reload button on the columns parameter. Runtime persistence unaffected. Remove this section once n8n auto-refreshes the schema on workflow load. -->

## Common patterns

### Dedup by external ID

Default to the `Remove Duplicates` node ("items seen in previous executions" mode) for plain "have I seen this value?" dedup. It's a one-node solution with an internal store, no schema to maintain. Data Tables only earn the slot when there's a reason for the dedup state to live in a real table:

- **You'll query or inspect the dedup state.** Dashboards, audit, "what have we processed in the last week?"
- **Row-level logic on hits.** Per-category TTL ("expire after 30 days for category A, 7 days for category B"), conditional re-process based on stored state, branching on a status column.
- **Per-tenant or per-user namespacing** that the `Remove Duplicates` history-store can't express.

When that bar is met:

```
[Source: { arxivId, ... }]
   ↓
[Data Table Get: filter arxivId eq $json.arxivId, limit 1]
   ↓
[IF: result has items?]
   ├── Yes → [Skip, or apply row-level logic from the stored row]
   └── No  → [Process] → [Data Table Insert: { arxivId, ...rest }]
```

For the full pattern surface (upsert, rowNotExists, Get+IF, idempotency keys), see `references/DEDUP_PATTERNS.md`.

### Lookup tables

Stable reference data (country → tax rate, plan → feature flags). Edited via n8n UI, and workflows read at execution:

```
[Data Table Get: filter country eq $json.country, limit 1]
   ↓
[Use the looked-up row's taxRate, etc.]
```

### Recent events / audit trail

Append-only insert, queried later:

```
[Workflow event] → [Data Table Insert: { userId, eventType, payloadSummary }]
```

`createdAt` makes "recent events in the last hour" trivial without your own timestamp.

## Reference files

| File | Read when |
|---|---|
| `references/SCHEMA_DESIGN.md` | Designing columns/types, the no-FK relational pattern, mapping mode (`defineBelow` vs `autoMapInputData`), when Data Tables are the wrong tool |
| `references/OPERATIONS.md` | Operation surface (insert/upsert/update/get/delete/rowExists), filter syntax, matchType, orderBy |
| `references/DEDUP_PATTERNS.md` | Idempotency keys, RemoveDuplicates node vs Data Table dedup, search-then-insert vs upsert |

For expression discipline (`$json` vs `$('Node Name').item.json`, the Set-node antipattern), see `n8n-expressions-official`. For Merge convergence and same-shape branches, see `n8n-node-configuration-official` `references/MERGE_NODE.md`.

## Anti-patterns

| Anti-pattern | What goes wrong | Fix |
|---|---|---|
| Set node upstream of Insert "to shape the input" | Extra node for nothing, classic Set antipattern, field shape drifts when you add columns | Map directly in the Insert node's per-column slots, OR rename upstream fields to enable auto-map |
| Declaring `id`, `createdAt`, `updatedAt` in `create_data_table` | Errors, or shadows the system column with a user column that doesn't auto-update | Don't declare them, they're already there |
| Storing application-critical data in Data Tables | If n8n breaks, you lose access | Use a real DB for data you can't lose |
| Cross-app system-of-record in Data Tables | Hard to share with non-n8n consumers, awkward query surface | Use a real DB |
| Treating auto-`id` as a stable cross-instance identifier | Resets if the table is recreated, not portable | Use a domain ID column (`arxivId`, `requestId`) for cross-system references |
| Foreign-key cascade assumptions | n8n doesn't cascade, deleted parents leave orphan children | Soft-delete, or run cleanup workflows that maintain referential integrity |
| Referencing an immediately-prior node when an intermediate stripped json | Insert silently writes NULLs for fields that "should be there" | Reference a stable upstream node by name, or use a NoOp/Merge convergence anchor (see `n8n-expressions-official` and `n8n-node-configuration-official` `references/MERGE_NODE.md`) |
| Manual-map mode + Set node to fix "Currently no items exist" | Doesn't fix anything, that's a UI quirk, you've added a useless Set node | Verify via `get_workflow_details` that `columns.value` has your mappings, runtime is fine. Tell the user to press the reload button on the columns parameter to make the UI render the fields. |

## Verification before publishing

After creating or updating a workflow that uses Data Tables:

1. `validate_workflow` passes.
2. `get_workflow_details` and inspect each Data Table node's `columns`. Both `value` and (for manual map) `schema` populated.
3. `test_workflow` with pinned data. Insert response should include `id`, `createdAt`, `updatedAt`.
4. Inspect actual Data Table contents via UI or follow-up Get to confirm columns aren't silently NULL.

Step 4 especially the first time you wire a new Insert. Context-stripping intermediates + manual map + UI quirk silently produce NULL columns.
