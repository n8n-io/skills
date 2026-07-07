# Data Table schema design

Day-one schema decisions stick for the table's life. Data Tables are forgiving (add columns later) but constrained (no foreign keys, modest scale, n8n-internal, no in-place column type changes). Once a column is `string`, it stays `string` until you create a new column and migrate. Pick types deliberately on day one.

## The system-managed columns

```
id          bigserial   primary key, auto-assigned, can't write to
createdAt   timestamp   set on insert
updatedAt   timestamp   refreshed on each update
```

Don't declare these in `create_data_table`. Build your schema as if they exist, because they do.

## Picking column types

Primitives only:

| Type | When |
|---|---|
| `string` | Text, IDs, enums, anything non-numeric/non-boolean |
| `number` | Counters, prices, scores, anything you'll do math on |
| `boolean` | True/false flags. Don't overload `string` with `'yes'/'no'`. |
| `date` | Timestamps you set explicitly (distinct from auto `createdAt`/`updatedAt`) |

**No JSON / object / array column types.** Only the four primitives above.

### The `_object` convention for nested data

When you need to store an object or array (e.g., the `keyInsights` array from an LLM, a parsed JSON response), use a `string` column and stringify on write. **Mark the column with an `_object` postfix** so future readers (humans and agents) know to parse it:

```ts
// On insert:
columns: {
    value: {
        arxivId: '={{ $json.arxivId }}',
        keyInsights_object: '={{ JSON.stringify($("Summarize").item.json.output.keyInsights) }}',
        topics_object: '={{ JSON.stringify($("Summarize").item.json.output.topics) }}',
    },
}

// On read:
{{ JSON.parse($("Get Paper").item.json.keyInsights_object) }}
```

The `_object` postfix is the contract: any column ending in `_object` holds a JSON-stringified value and must be `JSON.parse(...)`'d on read. Workflows reading the table know what to do without inspecting the data.

### Storage format ≠ interface format

The most important rule about `_object` columns: **stringify-on-write, parse-on-read, and never let the stringified shape leak past the storage boundary.** The string is the *storage* format, not the *interface* format.

What this means in practice:

- **Inside the sub-workflow that owns the table**, you stringify just before the Data Table Insert/Update. That's the storage-format boundary going in.
- **Inside the sub-workflow that owns the table**, you parse just after the Data Table Get. That's the storage-format boundary coming out.
- **When the sub-workflow returns data to a caller**, return arrays as arrays and objects as objects (the natural shape) even if those values came from `_object` columns. Do not return strings that the caller has to parse.

Why: the caller doesn't (and shouldn't) know that you store things as stringified strings. That's an internal implementation detail of the table-owning workflow. Forcing every caller to remember to `JSON.parse` is the same kind of API leak as exposing your DB schema directly to consumers.

#### The failure mode

Any sub-workflow that owns a Data Table with `_object` columns tends to develop two return paths: a "fresh" path (the data was just produced, still in natural shape) and a "cached" path (read back from the table, where `_object` fields are stringified). The wrong instinct: stringify the fresh path's output to "match" the cached shape. The right instinct: parse the cached path's output, so both paths return arrays as arrays and objects as objects.

Symptom of the wrong choice: every caller has to `JSON.parse(...)` the return values. Templates choke, downstream tools see strings where they expect arrays, and the whole system has a hidden coupling to your storage representation.

Fix: in the sub-workflow's final return node, parse any `_object` field back to its natural shape:

```ts
// Final return node (Set / Edit Fields):
{
    id:       '={{ $("Merge").item.json.id }}',
    name:     '={{ $("Merge").item.json.name }}',
    items:    '={{ JSON.parse($("Merge").item.json.items_object) }}',
    metadata: '={{ JSON.parse($("Merge").item.json.metadata_object) }}',
}
```

The return contract is: arrays as arrays, objects as objects. Storage representation stays inside the table-owning workflow.

### When NOT to use `_object` columns

- **You need to query the nested data** (filter `WHERE topics CONTAINS 'AI'`). String columns can't be queried structurally, so you'd be doing client-side filtering after a `get` of everything. For queryable nested data, denormalize into a child table with relational design (see "Designing relationally without foreign keys" below) or use a real DB.
- **The nested data is huge** (large arrays, deep trees, multi-MB objects). Data Tables can hold it, but performance and the n8n DB size both suffer. Use external storage and reference by URL.

## Naming

- **camelCase columns**: `arxivId`, `publishedAt`, `isProcessed`. Matches the auto-managed columns (`createdAt`, `updatedAt`), so a query reading both reads as one consistent table.
- **Title Case with spaces tables**: `Papers`, `Recent Events`, `Customer Dedup`. Tables are user-facing in the n8n UI (picker dropdowns, table list), so they read like proper nouns. Plural for sets, singular for one-row-per-global-thing (rare).
- **Domain prefixes for relational columns**: `paperId`, `customerId`, `episodeId`. Makes relationships obvious without FK enforcement.
- **`_object` postfix is a marker, not casing.** Stringified-blob columns keep the underscore: `keyInsights_object`, `topics_object`. The underscore signals "parse this on read" the same way `_v2` or `_legacy` would, so it stays even when the rest of the name is camelCase.

## Designing relationally without foreign keys

Data Tables don't enforce referential integrity, and they don't run multi-row transactions. You're responsible for both: integrity via workflow logic, atomicity via error handling.

### No transactions, plan for partial failure

If you Insert a parent then Insert a child and the child fails, the parent row is already written. There is no rollback. Any relational sequence that spans more than one write (parent + child Inserts, cascade-delete, multi-table updates) needs error handling, full stop. Pick one:

- **Compensating writes.** Catch the failure mid-sequence and undo what already succeeded (delete the parent if the child Insert errors).
- **Idempotent retry.** Design the sequence so re-running it is safe, usually with `upsert` and stable domain IDs, so a partial first run completes correctly on retry.
- **Soft state markers.** Add a `status` column to the parent (`pending`, `complete`), flip to `complete` only after all child writes land, and consumers ignore `pending`.

See `n8n-error-handling-official` for the error-output wiring.

### Reference rows by `id`

Child holds parent's `id`:

```
Papers              Papers.id is the key
  id (auto)
  arxivId (string)
  title (string)
  ...

Paper Summaries     paperId references Papers.id
  id (auto)
  paperId (number)
  summaryText (string)
  generatedAt (date)
```

When inserting a child, capture the parent's `id` from a prior `get` (or the `insert` response):

```ts
// After an insert into Papers, the response has { id, createdAt, updatedAt }.
// Use that id directly:
{
    operation: 'insert',
    dataTableId: { ..., value: '<Paper Summaries table id>' },
    columns: {
        mappingMode: 'defineBelow',
        value: {
            paperId: '={{ $('Insert Paper').item.json.id }}',
            summaryText: '={{ $('Summarize').item.json.output.tldr }}',
            generatedAt: '={{ $now.toISO() }}',
        },
    },
}
```

### Enforce integrity in the workflow

Before inserting a child, look up the parent. Before deleting a parent, decide:

- **Cascade-delete children**: a separate Data Table Delete on children, filtered by parent `id`.
- **Soft-delete parent**: add an `archived` boolean, and children filter on `archived = false`.
- **Orphan children**: leave them. Useful when the relationship is loose.

Pick one per relationship. Mixed strategies cause silent bugs.

### Watch for "child without parent"

Delete a parent and forget children, and they point at a non-existent `id`. n8n won't tell you. Symptoms surface later when joins return nothing.

Guards:

- **Don't delete parents without a child cleanup.**
- **Periodic audit workflow**: scheduled scan for child rows whose parent FK doesn't exist.
- **Soft-delete by default**: deletion becomes `archived=true`, and children stay valid.

## When Data Tables are the wrong tool

Reach for an external DB when:

- **Data is shared across apps.** Other systems read or write it, and n8n is one of many.
- **Volume is high.** Millions of rows, write-heavy.
- **You need ACID across tables.** Data Table operations are per-row.
- **You need foreign-key enforcement.** Data Tables won't enforce.
- **You need backup/restore independent of n8n.** Data Tables live in n8n's DB.

When Data Tables ARE the right tool:

- Workflow-local persistent state (dedup keys, idempotency markers, recent events for an in-n8n dashboard).
- Lookup tables that change rarely (country → tax rate, plan → feature flags).
- Per-session inventories (e.g., files uploaded in a conversation, keyed on `sessionId`).
- Counters / aggregates with bounded volume.

## Schema evolution

- **Add column**: `add_data_table_column` or UI. Existing rows get NULL, so backfill if needed.
- **Rename**: `rename_data_table_column`. Update workflows referencing the old name.
- **Drop**: `delete_data_table_column`. Permanent. Ensure no workflow still reads it.
- **Type change**: not in-place. Add new column, copy via workflow, drop old, rename new. Pre-design types to avoid.

## A healthy table

- 3 to 12 columns. Past that, consider splitting.
- Names obvious to a reader who hasn't seen the writing workflow.
- Every column referenced by at least one workflow. Audit periodically.
- Domain identifiers (`arxivId`, `customerId`) alongside auto-`id` when needed.

## Mapping mode on Insert/Update/Upsert

The `columns` parameter has two modes: `mappingMode: 'defineBelow'` (manual per-column expressions) and `mappingMode: 'autoMapInputData'` (n8n maps by upstream field name).

Default to `defineBelow`. Explicit, expressions sit at the consumer, refactors read clearly. Auto-map only when you have a stable 1:1 between upstream field names and column names. Drift in either side silently breaks the mapping.

For the `$json.x` vs `$('Node Name').item.json.x` discipline that prevents silent NULLs when intermediate nodes strip json, see `n8n-expressions-official`. For Merge convergence and same-shape branches, see `n8n-node-configuration-official` `references/MERGE_NODE.md`.

## Cross-references

- Querying / filtering: `OPERATIONS.md`.
- Dedup patterns: `DEDUP_PATTERNS.md`.
- Data Tables vs external storage: parent `SKILL.md`.
- Expression discipline (`$json` vs named references, Set-node antipattern): `n8n-expressions-official`.
- Branch / Merge wiring: `n8n-node-configuration-official` `references/MERGE_NODE.md`.
