# Dedup patterns

"Have we processed this before?" is one of the most common workflow needs, and most of the time the answer doesn't need a Data Table. The `Remove Duplicates` node has a built-in mode for it: a one-node solution with an internal store. Data Tables earn the slot only when the dedup state needs to do more than answer "seen / not seen."

## Default: `Remove Duplicates` node

For plain "seen this exact value before?" with no associated data:

```ts
{
    type: 'n8n-nodes-base.removeDuplicates',
    parameters: {
        operation: 'removeItemsSeenInPreviousExecutions',
        dedupeValue: '={{ $json.entryId }}',
        options: {
            historySize: 10000,
        },
    },
}
```

Fits when:

- Dedup is JUST about the value, no metadata to attach.
- History size limit (~10k default) is enough.
- You don't need to inspect or query "what have we seen?"

## When Data Tables earn the slot

Reach for a Data Table when you need any of:

- **Queryable dedup state.** Dashboards, audit, "what have we processed in the last week?"
- **Row-level logic on hits.** Per-category TTL ("expire after 30 days for category A, 7 days for B"), conditional re-process based on stored state, branching on a status column.
- **Per-tenant / per-user namespacing** beyond what the history-store can express.
- **TTL with cleanup.** Daily cleanup of stale markers.
- **Volume past ~10k history items.**

When that bar is met, pick one of three Data-Table patterns by the branch behavior you want.

## Pattern 1: `upsert` (cleanest)

For "first time → insert, subsequent → update" with no branching:

```
[Source: { arxivId, ... }]
   ↓
[Data Table Upsert: matchType allConditions, filter arxivId eq <id>, columns ...]
   ↓
[Continue with the inserted/updated row's id]
```

Upsert returns `id`, `createdAt`, `updatedAt` whether insert or update, so downstream doesn't need to know which.

When wrong:

- You need to skip work on duplicates. Upsert always touches the row, wastes compute. Use Pattern 2.
- You need a "first time only" side effect. Upsert can't distinguish without an extra `get` to compare timestamps.

## Pattern 2: `rowNotExists` + Insert (skip duplicates)

To **skip processing for existing rows**:

```
[Source: { arxivId, ... }]
   ↓
[Data Table rowNotExists: filter arxivId eq <id>]
   ↓ (only new items pass through)
[Process: download, summarize, etc.]
   ↓
[Data Table Insert: { arxivId, ... }]
```

`rowNotExists` filters input, and existing rows drop silently.

When wrong:

- You also need to handle existing items (return cached result). Use Pattern 3.

## Pattern 3: Get + IF (full control)

For both branches, "process new" AND "return existing":

```
[Source: { arxivId, ... }]
   ↓
[Data Table Get: filter arxivId eq <id>, limit 1, alwaysOutputData=true]
   ↓
[IF: $json.id exists?]
   ├── Yes (already processed) → [Return existing row's data]
   └── No (new) → [Process] → [Data Table Insert] → [Return new row's data]
```

Two notes:

- **`alwaysOutputData: true` on Get.** Without it, no-match produces zero items and the pipeline silently does nothing. With it, Get always emits one item (possibly empty), and the IF can branch.
- **Both branches must produce the same JSON shape.** Otherwise downstream `$json.x` breaks depending on which branch fired. See `n8n-node-configuration-official` `references/MERGE_NODE.md` for the Merge convergence anchor.

## Pattern decision tree

```
Need to dedup?
├── Plain "seen this value?" with no metadata, no TTL, fits in ~10k history?
│   └── Default: Remove Duplicates node, no Data Table
│
└── Need queryable state, row-level logic, TTL, or per-tenant namespacing?
    ├── Want "skip duplicates" (no work on existing)?     → Pattern 2: rowNotExists + Insert
    ├── Want "first-time insert, subsequent update"?      → Pattern 1: upsert
    └── Want both branches (process new, return cached)?  → Pattern 3: Get + IF + same-shape branches
```

## Idempotency keys

For webhook workflows safe under retries:

```
[Webhook receives X-Request-Id header]
   ↓
[Data Table Get: filter requestId eq <id>, limit 1, alwaysOutputData=true]
   ↓
[IF: row exists?]
   ├── Yes → [Respond with cached response stored on the row]
   └── No  → [Process]
              ↓
            [Data Table Insert: { requestId, responseBody, ... }]
              ↓
            [Respond with the response]
```

Two design choices:

1. **Store response or just marker?** Storing lets you serve the same answer on retry (full idempotency). Marker-only suffices when clients retry only to confirm receipt.
2. **TTL?** Markers shouldn't live forever. Run a daily cleanup deleting rows where `createdAt < now - <retry window>`.

## Volume notes

- Data Tables handle tens of thousands of rows. Past that, dedup queries get slow.
- For millions of keys, use a real cache (Redis, DynamoDB).
- For hundreds of rows with no metadata, the `Remove Duplicates` default is simplest.

## Cross-references

- Filter syntax: `OPERATIONS.md`.
- Where dedup fits in API workflows: `n8n-error-handling-official` `references/API_WORKFLOWS.md`.
- `alwaysOutputData: true` rule: `n8n-node-configuration-official` and the SDK reference's "Handle empty outputs."
