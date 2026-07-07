# Data Table operations

The `dataTable` node has two resources: `row` and `table`. Most work is `row`. This covers row operations and the filter/sort surface.

## Row operations

### `insert`

Always-add. Creates a row, and n8n assigns `id`, `createdAt`, `updatedAt`.

Required: `dataTableId`, `columns`.

Returns: `{ id, createdAt, updatedAt }`.

Use when: row is known new (post-dedup, append-only).

### `upsert`

Update matching rows, insert if none match.

Required: `dataTableId`, `matchType`, `filters.conditions`, `columns`.

Use when: you have a domain identifier and want first-time and subsequent-time handled the same.

```ts
{
    operation: 'upsert',
    dataTableId: { __rl: true, value: '<table-id>', mode: 'list' }, // real ID from search_data_tables (or explore_node_resources tableSearch)
    matchType: 'allConditions',
    filters: {
        conditions: [
            { keyName: 'arxivId', condition: 'eq', keyValue: '={{ $("Source").item.json.arxivId }}' },
        ],
    },
    columns: {
        mappingMode: 'defineBelow',
        value: {
            arxivId: '={{ $("Source").item.json.arxivId }}',
            title: '={{ $("Source").item.json.title }}',
            // ... other columns
        },
    },
}
```

### `update`

Modify matching rows, no-op if none match (unlike upsert).

Required: `dataTableId`, `matchType`, `filters.conditions`, `columns`.

Use when: the row should exist, and you're modifying state.

### `get`

Fetch rows matching a filter. Returns 0+ rows.

Optional: `returnAll` (vs `limit`), `orderBy` + `orderByColumn` + `orderByDirection`.

```ts
{
    operation: 'get',
    dataTableId: { __rl: true, value: '<table-id>', mode: 'list' }, // real ID from search_data_tables (or explore_node_resources tableSearch)
    matchType: 'anyCondition',
    filters: {
        conditions: [
            { keyName: 'arxivId', condition: 'eq', keyValue: '={{ $json.arxivId }}' },
        ],
    },
    returnAll: false,
    limit: 1,
}
```

One item per row out. Empty filter = empty output (downstream may need `alwaysOutputData: true` to fire).

### `deleteRows`

Remove matching rows. Same filter shape. Returns deleted count (or per-row depending on version).

Use carefully. No cascade, so child rows referencing this `id` become orphans.

### `rowExists` / `rowNotExists`

Filter input into "has a matching row" vs "doesn't." Output is input items, filtered.

Use when: dedup logic is "skip already-in-table" (or vice versa) and you want one node instead of Get + IF.

```ts
{
    operation: 'rowNotExists',
    dataTableId: { __rl: true, value: '<table-id>', mode: 'list' }, // real ID from search_data_tables (or explore_node_resources tableSearch)
    matchType: 'allConditions',
    filters: {
        conditions: [
            { keyName: 'arxivId', condition: 'eq', keyValue: '={{ $json.arxivId }}' },
        ],
    },
}
```

Non-matches pass through, matches drop. Followed by Insert, this is dedup-as-a-pipeline.

## Filter syntax

`filters.conditions` applies to `get`, `update`, `upsert`, `deleteRows`, `rowExists`, `rowNotExists`.

Each condition:

```ts
{
    keyName: 'columnName',                      // or expression
    condition: 'eq',                            // operator
    keyValue: '={{ $json.value }}',             // or literal
}
```

Operators:

| Operator | Meaning |
|---|---|
| `eq` | equals |
| `neq` | not equals |
| `gt` / `gte` | greater than / greater-or-equal |
| `lt` / `lte` | less than / less-or-equal |
| `like` | string match |
| `notLike` | string mismatch |
| `isEmpty` / `isNotEmpty` | null/empty checks (no `keyValue` needed) |
| `isTrue` / `isFalse` | boolean checks (no `keyValue` needed) |

### `matchType`: AND vs OR

- `'allConditions'`: AND.
- `'anyCondition'`: OR.

Default in some versions is `anyCondition`, surprising for multi-column filters. For AND, set `matchType: 'allConditions'` explicitly.

## Sorting (`get` only)

```ts
{
    operation: 'get',
    // ...
    orderBy: true,
    orderByColumn: 'createdAt',
    orderByDirection: 'DESC',
}
```

Sort by any column (including system-managed). `id` ordering is insertion order. `createdAt` matches normally but can differ after table repair.

## Pagination

There's no native `offset` parameter on `get`. `limit` is per-call, so larger results need one of:

- `returnAll: true` (memory caution on large tables).
- `returnAll: false` + `limit` + repeated calls with a keyset filter (e.g., `id > <last seen>`). Keyset, not offset, because there's no offset to set.

For "process new since last sync," filter on `createdAt > <last sync>` + `orderBy createdAt ASC`, capture the new max, save for next sync.

## Common pitfalls

### Missing `matchType` on multi-column filters

Defaults to OR in some versions. For AND, set `matchType: 'allConditions'`.

### Filtering on a non-existent column

May error or silently match nothing depending on version. `keyName`/`orderByColumn` are `@loadOptionsMethod` columns: resolve real names via `explore_node_resources` (`getDataTableColumns`, `loadOptions`) rather than guessing spelling.

### Update with no match silently does nothing

No error. Follow with a `get` to confirm, or use `upsert` for create-or-update.

### Insert without dedup re-inserts on every run

Trigger retries (webhook retry, scheduled re-run) create duplicates. Use `upsert`, `rowNotExists` + Insert, or upstream dedup. See `DEDUP_PATTERNS.md`.

### `returnAll: false` with no `limit`

Defaults to `limit: 50` in many versions. Set `returnAll: true` or bump `limit` if downstream expects more.

## Cross-references

- Idempotency / dedup: `DEDUP_PATTERNS.md`.
- Schema design and mapping mode: `SCHEMA_DESIGN.md`.
- `$json.x` vs `$('Source').item.json.x`: `n8n-expressions-official`.
