# Database nodes: Postgres, MySQL, MongoDB, Supabase

DB nodes share patterns around query construction, parameter binding, and error handling. Exact field shapes vary; `get_node_types` is canonical. This file covers security, decisions, and gotchas not in the type def.

## Always parameterize, never concatenate

**Critical.** Never interpolate user input into the query string. n8n substitutes `{{ ... }}` expressions into the query text *before* parameter binding, so anything in `{{ }}` becomes part of the SQL itself, not a bound value.

```ts
// ❌ DON'T: n8n substitutes the expression into the SQL string before binding.
//          $json.email = "x'; DROP TABLE users; --" → game over.
{
    operation: 'executeQuery',
    query: "=SELECT * FROM users WHERE email = '{{ $json.email }}'",
}

// ✅ DO: use $1, $2, ... placeholders + options.queryReplacement.
//        Values go through pg_promise's parameter binding, never touch the SQL text.
{
    operation: 'executeQuery',
    query: 'SELECT * FROM users WHERE email = $1',
    options: {
        queryReplacement: '={{ $json.email }}',
    },
}
```

`options.queryReplacement` accepts a comma-separated list (`value1,value2,value3`) or expressions that resolve to values (`={{ $json.email }},={{ $json.id }}`). Each comma-separated piece becomes one parameter, referenced as `$1, $2, ...` in the query. The `=` prefix on `queryReplacement` is just n8n's expression-mode marker. What matters is that the values flow via the option, not interpolated into the query.

Postgres and the n8n MySQL node both use `$1, $2, ...` via `options.queryReplacement`. Mongo uses object filters. Treat any pattern that puts user input into the query string as a critical injection vulnerability.

## Postgres

### `executeQuery` vs structured operations

- **`executeQuery`**: raw SQL with parameters. Most flexible. Use for joins, CTEs, window functions.
- **`select` / `insert` / `update` / `upsert` / `deleteTable`**: n8n builds the SQL. Less flexible but less footgun-prone for simple cases. Their `table` (and `schema`) are `@searchListMethod` lookups: resolve real names via `explore_node_resources`.

Note: "Delete" maps to `operation: 'deleteTable'` (display vs internal-value mismatch).

### Returning rows

`executeQuery` returns rows as items. Zero rows produces no items, downstream nodes may treat as "skip." Set `alwaysOutputData: true` to flow through a single empty item, or branch on the count.

## MySQL

Despite MySQL's native `?` placeholder syntax, **the n8n MySQL node uses `$1, $2, ...` and `options.queryReplacement`, same as Postgres**. The node normalizes to the driver. Same parameter-binding rules from "Always parameterize" at the top apply unchanged.

Beyond that, differences from Postgres are general MySQL behavior (operator availability, AUTO_INCREMENT semantics) and not n8n-specific. Inspect `get_node_types` for the operation set, which differs slightly.

## MongoDB

Filters are JSON objects, not SQL. The n8n MongoDB node has the usual operations (`find`, `insert`, `update`, `delete`, `aggregate`, plus `findOneAndUpdate` / `findOneAndReplace`) and most n8n-specific surface lives in `get_node_types`. For complex queries (aggregation pipelines, `$lookup` joins) use `aggregate`. For document writes, the node splits items into separate writes by default; bulk-write via the relevant batch option.

## Supabase

Wraps PostgREST. Uses Supabase's REST API, not direct DB connections.

### Power-user tip: prefer the Postgres node for non-trivial work

For anything beyond per-row CRUD (joins, CTEs, window functions, aggregations, RPC calls), the Postgres node connecting directly to your Supabase database is strictly more powerful than the Supabase REST node, full SQL surface against the same data. The tradeoff is auth: the Postgres node needs the direct DB connection details (host, port, database, user, password) from your Supabase project's database connection settings, not the project URL + anon key. One-time setup, then it's a normal Postgres workflow.

Same security rules apply: never interpolate user input into the query string, always use `$1, $2, ...` + `options.queryReplacement` (see "Always parameterize" at top). RLS doesn't apply to direct DB connections, so the `service_role` vs `anon` distinction goes away too. Your queries see all rows.

### Operation values: "Get Many" → `'getAll'`

Display vs internal-value mismatch (not `'getMany'`).

### Missing filter conditions

If you expect `isTrue` / `isFalse` / `isNull` / `in` as separate conditions, they don't exist. Use `condition: 'is'` with `keyValue: 'null' | 'true' | 'false' | 'unknown'`. Inspect `get_node_types` for the supported set.

### Default-value pattern for missing input

When a filter value comes from optional input, default it to a known-empty value:

```ts
keyValue: `={{ $json.id || "305f7106-6988-4651-b26a-18979641b7b5" }}`,
```

Avoids "filter on undefined" errors that produce empty result sets or 400s.

### RLS gotcha

Supabase uses Row-Level Security by default. Empty results when you expect data is usually:

- Wrong credential role: `anon` respects RLS, `service_role` bypasses it.
- Backend workflows usually want `service_role`. Public-facing APIs want `anon` with proper RLS.

## Common patterns across DB nodes

### Handle the "no rows" case

After `select` / `find`, zero matches yields zero items and downstream nodes silently skip. Either set `alwaysOutputData: true` to flow through an empty item, or branch on the lookup with an IF and feed defaults via Set on the no-match path.

### Upsert when you don't know if the row exists

Postgres' `INSERT ... ON CONFLICT DO UPDATE` (or n8n's `upsert` operation) is cleaner than:

```
SELECT → IF exists → UPDATE
                  └─→ INSERT
```

Two queries become one, race conditions disappear.

### Transactions

**Postgres and MySQL** support transactions natively via `options.queryBatching: 'transaction'` (default `'single'`, also `'independently'`) on `executeQuery`. All queries the node executes in that run go through one BEGIN/COMMIT; any failure rolls everything back. The canonical use is multiple input items each driving one query, executed atomically by a single Postgres / MySQL node.

```ts
{
    operation: 'executeQuery',
    query: 'INSERT INTO orders (customer_id, total) VALUES ($1, $2)',
    options: {
        queryBatching: 'transaction',
        queryReplacement: '={{ $json.customerId }},={{ $json.total }}',
    },
}
```

**Supabase** wraps PostgREST and has no transaction support at the REST layer. For atomic multi-step writes against Supabase, drop to the Postgres node connecting to the same database (see the "Power-user tip" above) and use `queryBatching: 'transaction'`.

**MongoDB** is a different story (see its own docs for session-based transactions); the n8n MongoDB node doesn't expose them directly.

**Across multiple n8n nodes**, there's still no transaction. Atomicity is bounded to one `executeQuery` invocation. If you find yourself wanting cross-node atomicity, redesign the workflow so the writes that must succeed or fail together live in a single `executeQuery` node with `queryBatching: 'transaction'`. Pre-compute everything you need upstream (lookups, validations, derived values) so the transactional node receives ready-to-write data, then express the multi-step write as multiple SQL statements (semicolon-separated, or one per input item) all going through the same node. The non-transactional work stays outside; the transactional work collapses inward.
