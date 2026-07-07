---
name: n8n-loops-official
description: Use when working with multi-item data, batches, paginated APIs, rate-limited APIs, fan-out across multiple branches, anything that needs to "do this for each", or any time the user mentions looping, iterating, batching, paging, parallelism, or "loop over items". Triggers on "loop", "iterate", "for each", "batch", "page through", "paginate", "rate limit", "process all", "fan-out", "parallel branches", "concurrency", or any node that should run once vs once-per-item.
---

# n8n Loops

Three meanings of "loop" map to three mechanisms:

1. **"Run this node for every item."** Default. Most nodes loop automatically, so do nothing.
2. **"Run this node *once* with all items, not once per item."** The `executeOnce` setting (single boolean).
3. **"Process items in explicit batches with control flow between iterations."** The `Loop Over Items` node (formerly `Split In Batches`).

For paginated APIs, the HTTP Request node has built-in pagination. Almost always preferable to a hand-built page-counting loop.

## The model: items are an array

Data flows between nodes as an array of items, each `{ json: {...}, binary?: {...} }`. 50 items = 50-entry array.

Default: a node runs once *per item*. An HTTP Request with 50 input items fires 50 requests and outputs 50 result items. This is the implicit loop most workflows rely on.

**The input array is the loop.** Control iteration by controlling the array.

## Non-negotiable

**`executeOnce: true` whenever a node should fire once-per-run, not once-per-item.** Includes any expression *aggregating across the dataset* via `$input.all()` / `$('Node').all()` plus `.map()` / `.filter()` / `.reduce()` (without it, the aggregate computes N times for N upstream items, often producing N duplicates downstream). Also includes single notifications, aggregate writes, summary messages.

**Counter-case:** `.all()` combined with another node's `.item` (a per-item lookup, e.g., `$('Get Tags').all().filter(tag => $('Search Posts').item.json.tag_ids.includes(tag.json.id))`) is real per-item work and should keep `executeOnce` off. See the `n8n-expressions-official` skill's executeOnce section for the full distinction.

## Strong defaults

- **Don't build a loop when default iteration suffices.** Most nodes (HTTP Request, native service nodes, Set, IF/Switch) run once per input item automatically: N items in, N runs. To make N HTTP calls or create N records, just connect the source to the node. Don't reach for `Loop Over Items` unless you need per-iteration control. (Note: `Execute Workflow` is the exception. It defaults to a single all-items batch. See `n8n-subworkflows-official` for `mode: 'each'`.)
- **For paginated APIs, use HTTP Request's built-in pagination.** Don't reinvent with `Loop Over Items` + manual `$pageCount` unless the API is genuinely odd. See `references/HTTP_PAGINATION.md`.
- **`Loop Over Items` is for explicit batching or per-iteration control** (rate limiting, per-batch error recovery, stateful chunks, polling). See `references/LOOP_OVER_ITEMS.md`.
- **Per-item iteration is sequential, not parallel.** Each item completes before the next starts, even on parallel _looking_ branches. For a real concurrency pattern, see `n8n-subworkflows-official`. 

## Decision tree: which mechanism do I need?

```
Need to do something for each item?
├── Default per-item iteration is enough
│   └── Just connect the node. Done.
│
├── The node should run once total, not once per item?
│   └── Set executeOnce: true on the node
│
├── Paginated API (multiple HTTP calls to fetch all pages)?
│   └── Use HTTP Request's Pagination option (see references/HTTP_PAGINATION.md)
│
├── Need explicit batching (rate limit, chunk size, per-batch error handling)?
│   └── Use Loop Over Items node (see references/LOOP_OVER_ITEMS.md)
│
└── Need to recurse / repeat with state until a condition is met?
    └── Loop Over Items with Reset, OR a sub-workflow that calls itself.
        Both are advanced patterns; see references/LOOP_OVER_ITEMS.md.
```

## `executeOnce`: the single-fire setting

Every node's Settings tab has an **Execute Once** toggle. When on, the node runs once using only the first input item. In SDK code, set `executeOnce: true` as shown; on an existing workflow, apply it via `update_workflow` `setNodeSettings` (n8n 2.24.0+).

```ts
{
    name: 'Aggregate Slack',
    type: 'n8n-nodes-base.slack',
    parameters: { /* ... */ },
    executeOnce: true,
}
```

When to use it:

- **Notifications and aggregate writes.** A "summary message" shouldn't fire 100 times because 100 items came in.
- **Counters, totals, reports.** Anything computing `$input.all().length` etc. should run once.
- **Expressions aggregating across the full array via `$input.all()` / `$('Node').all()`.** Otherwise the aggregate runs per upstream item. (Per-item *lookups* using `.all()` filtered by another node's `.item` are the counter-case, see `n8n-expressions-official`.)

When NOT to use it:

- **Per-item operations.** One notification *per* item is the default and usually correct.
- **HTTP requests fanning out per item.** You want one call per item.

Most common mistake: forgetting `executeOnce` on an aggregate node, then seeing the same message fire 50 times after a fan-out.

## When the implicit loop bites you

Default per-item iteration is great until it isn't. Common surprises:

### A "single" config node fires per item

A `Set` node after a fan-out runs once per item, producing N copies of the same constants. Usually fine, but expensive expressions (long `JSON.stringify`, Luxon parse) run N times. Move the Set above the fan-out, or set `executeOnce: true`.

### An aggregate Code node runs N times

A Code node reading `$input.all()` to compute a sum runs once per upstream item without `executeOnce: true`, producing N identical items. Set `executeOnce: true`.

### A respond-to-webhook fires twice

Most painful version. Respond-to-Webhook fires per input item, and two branches converging without a merge fire it twice: first response wins, the rest log errors. Merge first, or ensure only one branch reaches the responder. See `n8n-node-configuration-official` `references/MERGE_NODE.md`.

### An LLM call fires N times when you wanted one summary

Same shape as the aggregate Code node. An LLM node with `$input.all()` in its prompt makes N identical calls, costs N tokens, returns N identical answers without `executeOnce: true`.

## When to reach for `Loop Over Items`

Default iteration handles most cases. Use `Loop Over Items` for:

- **Rate limiting.** "Process 10 at a time, 1s wait between batches."
- **Batched API calls with array bodies.** "Send 50-item chunks to /bulk."
- **Per-batch error handling.** "If a batch fails, log and continue."
- **Stateful iteration.** "Each iteration depends on the previous output."
- **Polling a long-running job.** "Start, check status every 30s until done or capped." Uses `reset: true` plus a `$runIndex` ceiling.
- **Per-item multi-branch with aggregation.** "For each input, run transforms in parallel, merge, then aggregate." The done output (index 0) carries the result.

For wiring details, the output-index gotcha (output 0 = **done**, output 1 = **loop**), and worked examples, see `references/LOOP_OVER_ITEMS.md`.

## When NOT to reach for `Loop Over Items`

The most common rationalization: "I need to wait for all items to finish before the next step, so I'll add Loop Over Items and use the `done` output." **You don't need Loop Over Items for that.** Default per-item iteration already waits: each item flows through the full downstream chain before the next item starts, and the post-loop node never fires "early."

The cure for that mistake is almost always: **delete the Loop Over Items node, change nothing else, ship**. That is Scenario 1 below, and it covers the majority of cases.

The four scenarios are independent. Read them as separate decisions, not as alternatives that all "replace" Loop Over Items. Most builds hit Scenario 1 and are done. Scenarios 2 and 3 only enter the picture when their specific goal applies. Scenario 4 is the narrow case where Loop Over Items actually earns its place.

### Scenario 1: default per-item iteration (the default, most common)

Source emits N items, per-item processor runs N times, downstream chain follows. **No Loop Over Items, no `executeOnce`, no Aggregate.** Just connect the nodes.

```
[Source: 20 items]
  → [Per-item processor]   # default iter, runs 20 times
  → [Next step]            # runs after each item, in order
```

If a `Loop Over Items + done` was added here "to wait for all items" or "to make the next node run for each item," delete the Loop Over Items node and wire source straight to processor. **Do not replace it with anything.** Default iteration already does the job. The exception is `Execute Workflow` (sub-workflow): it defaults to a single all-items batch, so per-item invocation needs `mode: 'each'` on that node, not a Loop. See `n8n-subworkflows-official`.

### Scenario 2: a downstream node should fire once total (`executeOnce: true`)

Independent of Scenario 1. Triggered only when there is a SPECIFIC downstream node whose job is once-per-run, not once-per-item: one digest email after 20 papers process, one summary write after the loop, one final Slack notification.

Set `executeOnce: true` on that node. The node receives all upstream items but runs once. This is a per-node setting, not a Loop replacement: the per-item processor in Scenario 1 still runs N times, and only this one downstream node collapses.

### Scenario 3: a node needs the items as a single array (Aggregate)

Independent of Scenario 1. Triggered only when a downstream node's input contract is a list, not per-item invocations (e.g., a node taking a JSON array body, an LLM prompt that needs the whole list).

Use the Aggregate node to collapse the per-item stream into one item containing the array. Again, not a Loop replacement.

### Scenario 4: genuine batching (the only time Loop Over Items earns its place)

Rate limiting (process N at a time with a Wait between batches), chunked bulk API calls (POST 50-item arrays to `/bulk`), per-batch error handling, polling a long-running job with `reset: true` and a `$runIndex` ceiling, stateful iteration where each batch depends on the previous output.

"Wait for items to finish" does not qualify. Default iteration already does that.

### Quick disambiguation

If your only reason for the Loop is "wait for items / run for each item," you are in Scenario 1. Delete the Loop. Do not add `executeOnce` or Aggregate as a substitute. They solve different problems and are only added when their own scenario applies.

## When to reach for HTTP pagination

Three common page shapes:

- **Next-URL in response.** Each response includes a `next` link.
- **Page number/cursor parameter.** Bump `?page=N` or `?cursor=...` each call.
- **Stop on empty page** or specific status.

HTTP Request handles all natively via its **Pagination** option: set the mode, give a next-page expression, and the node loops internally, returning a single output array of all pages' items.

Don't reinvent with `Loop Over Items` + manual `$pageCount` unless the API does something the built-in modes can't express.

See `references/HTTP_PAGINATION.md`.

## Sub-workflow recursion

For genuinely recursive work (tree walking, retry-with-backoff, "process this and its children"), a self-calling sub-workflow is cleaner than `Loop Over Items` with `Reset`. Input parameters carry recursion state.

```
Sub-workflow: Walk Tree
  inputs: { node_id, depth }
  body: process node, look up children, for each child call self with depth+1
```

Watch recursion depth. n8n has nested-execution limits. For deep recursion, a queue + flat loop beats true recursion.

## Reference files

| File | Read when |
|---|---|
| `references/LOOP_OVER_ITEMS.md` | Configuring the Loop Over Items node, batching, rate limiting, stateful iteration |
| `references/HTTP_PAGINATION.md` | Calling a paginated API, configuring HTTP Request pagination modes |

## Anti-patterns

| Anti-pattern | What goes wrong | Fix |
|---|---|---|
| Adding `Loop Over Items` to "make it loop" when default iteration already does | Workflow harder to read for no benefit, and loop output vs done output gets miswired | Just connect the node directly and let default iteration handle it |
| Aggregate Code node without `executeOnce` | Same aggregate computed N times, output has N identical items | Set `executeOnce: true` |
| Manual pagination loop with `Loop Over Items` + `$pageCount` | Reinvents what HTTP Request does natively, with brittle stop conditions | Use HTTP Request's `Pagination` option |
| Sending one Slack message per item when you wanted a summary | Slack channel floods, rate limits hit, embarrassment | `executeOnce: true` on the Slack node, build the summary upstream |
| Two branches both reach `Respond to Webhook` | Responds twice, downstream callers see errors | Merge before the responder, or ensure only one branch reaches it |
| `Loop Over Items` with `Reset` and no clear termination | Infinite loop, n8n eats memory until the execution is killed | Always have a clear termination condition. Prefer HTTP pagination for paged APIs |
| Nesting one `Loop Over Items` inside another in the same workflow | Broken at runtime, validation passes | Move the inner loop into a sub-workflow called per outer iteration. See `n8n-subworkflows-official` `mode: 'each'` |

