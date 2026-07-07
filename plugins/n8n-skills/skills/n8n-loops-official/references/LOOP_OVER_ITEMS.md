# Loop Over Items node (formerly Split In Batches)

The explicit-batching loop. Use when default per-item iteration isn't enough: rate limiting, chunked API calls, per-batch error handling, polling, or stateful iteration.

See the parent `SKILL.md` decision tree for "should I use this." This file assumes yes.

## What it does

Splits the input array into batches of `batchSize` and exposes two outputs.

**Output indexes (typeVersion 3):**

- **`output(0)` (done):** fires *once* after all iterations complete, with the aggregated result. Wire your post-loop step here.
- **`output(1)` (loop):** fires *once per batch*. Wire per-batch processing here and route the tail back into the Loop Over Items node.

The index order trips people up: "done" is index 0 even though it fires last. Verify via `get_workflow_details` after wiring.

Wiring shape:

```
[Source]
   │
   ▼
[Loop Over Items] ──output(0) (done)──▶ [Final step]
   │
   └──output(1) (loop)──▶ [Process batch] ──▶ (back into Loop Over Items)
```

The "back into Loop Over Items" arrow makes it a loop. After per-batch processing runs, its tail flows back into the loop node, which either issues the next batch (loop output) or finishes (done output).

## Configuration

```ts
{
    name: 'Loop Over Customers',
    type: 'n8n-nodes-base.splitInBatches',
    parameters: {
        batchSize: 50,
        options: {
            reset: false,
        },
    },
}
```

Key parameters:

- **`batchSize`** (number): items per iteration. Default 1. Higher values trade granularity for fewer iterations.
- **`options.reset`** (boolean): when `true`, treats input as fresh on every iteration. For indeterminate-length loops (see below).

## Pattern 1: per-item processing with multi-branch convergence

The canonical "do several things to each item, then collect" pattern. Each iteration runs multiple things in parallel that converge before flowing back into the loop. The done output yields the aggregated result.

Example (a workflow-signing utility processing each input workflow's nodes, connections, and ID independently, then signing):

```
Sub-workflow Trigger
  → Split Out (expand input array into items)
  → Loop Over Items
        ├──output(0, done)──→ Sort by ID → Sign (executeOnce) → Set Output  (final result)
        └──output(1, loop)──┬──→ Extract Id ────────────→ Pass1 ──┐
                            ├──→ Split Out → Filter → Aggregate ──┼──→ Merge ──→ Merge1 ──→ back to Loop Over Items
                            └──→ Code: normalize connections ─→ Pass ──┘
```

Five things to notice:

1. **`Split Out` expands the input array into items before the loop.** Without it, Loop Over Items receives one mega-item and iterates once.
2. **The loop body fans out to parallel branches that converge via `Merge` nodes.** Branches recombine before the feedback edge.
3. **Named NoOp nodes (`Pass`, `Pass1`) anchor convergence points** so downstream Merges can reference them cleanly. Per `n8n-expressions-official` non-negotiables.
4. **The aggregate node on the done branch uses `executeOnce: true`.** Its `.all().map(...)` would otherwise execute per item, doing the aggregate N times.
5. **Per-iteration outputs feed `Merge` (combineAll).** The merged shape becomes one item flowing back into the loop, so the next iteration sees one well-formed item.

The structure scales to any "for each input, run a workflow internally, then aggregate" task: signing, validation, transforming, classifying, etc.

## Pattern 2: rate-limited / chunked processing

"Send these emails 5 at a time, with a 1-second pause between batches."

```ts
const loop = splitInBatches({
    config: {
        parameters: {
            batchSize: 5,
            options: {},
        },
    },
})

const send = node({ type: 'n8n-nodes-base.emailSend', config: { parameters: { /* ... */ } } })
const wait = node({ type: 'n8n-nodes-base.wait', config: { parameters: { amount: 1, unit: 'seconds' } } })
const summarize = node({
    type: 'n8n-nodes-base.set',
    config: {
        executeOnce: true,
        parameters: {
            values: { string: [{ name: 'message', value: '={{ $input.all().length }} emails sent' }] },
        },
    },
})

workflow
    .add(source.output(0).to(loop))
    .add(loop.output(1).to(send))     // loop output: process batch
    .add(send.output(0).to(wait))
    .add(wait.output(0).to(loop))     // back into Loop Over Items
    .add(loop.output(0).to(summarize)) // done output: final step
```

Three things to notice:

1. **The loop output (index 1) flows through processing then back into the loop node.** Feedback edge = iteration.
2. **The done output (index 0) wires to a different downstream.** Don't merge done and loop. They fire at different times.
3. **The summarize node uses `executeOnce: true`** since it reads `$input.all()`.

## Pattern 3: chunked bulk API call

"Send items to a `/bulk` endpoint accepting arrays up to 100."

```ts
const loop = splitInBatches({
    config: {
        parameters: {
            batchSize: 100,
            options: {},
        },
    },
})

const bulkPost = node({
    type: 'n8n-nodes-base.httpRequest',
    config: {
        executeOnce: true,  // run once per batch with the full batch as one body
        parameters: {
            method: 'POST',
            url: 'https://api.example.com/bulk',
            sendBody: true,
            bodyParameters: {
                parameters: [
                    { name: 'items', value: '={{ $input.all().map(item => item.json) }}' },
                ],
            },
        },
    },
})
```

`executeOnce: true` is critical: without it, the HTTP node fires once per item *within* the batch (100 individual POSTs), defeating the bulk endpoint. With it, one POST per batch carries all 100 items.

## Pattern 4: poll a long-running job (`reset: true`)

For jobs taking minutes or hours: start, poll status until done. `reset: true` makes the loop treat each iteration's input as fresh. Use the iteration index plus a status check to break out.

```
[Start long-running job]
   │
   ▼
[Loop Over Items, reset: true]
   │ output(0, done)──▶ (unused; reset:true means we never reach "done" naturally)
   │
   └─output(1, loop)──▶ [Wait 30s] ──▶ [Check job status]
                                          │
                                          ▼
                                     [IF: status.isDone OR $runIndex >= 10]
                                          │
                                          ├── true ──▶ [Continue workflow (NoOp)]
                                          └── false ──▶ (back to Loop Over Items)
```

Configuration:

```ts
const loop = splitInBatches({
    config: {
        parameters: {
            options: { reset: true },
        },
    },
})

const wait = node({ type: 'n8n-nodes-base.wait', config: { parameters: { amount: 30 } } })

const checkStatus = node({
    type: 'n8n-nodes-base.httpRequest',
    config: {
        parameters: {
            url: '=https://api.example.com/jobs/{{ $("Start Job").item.json.job_id }}',
        },
    },
})

const decide = ifElse({
    config: {
        parameters: {
            conditions: {
                combinator: 'or',
                conditions: [
                    {
                        leftValue: '={{ $("Check Job Status").item.json.isDone }}',
                        operator: { type: 'boolean', operation: 'true', singleValue: true },
                    },
                    {
                        leftValue: '={{ $runIndex }}',
                        rightValue: 10,
                        operator: { type: 'number', operation: 'gte' },
                    },
                ],
            },
        },
    },
})
```

Key points:

- **`$runIndex` (or `$('Loop Over Items').context.currentRunIndex`) is the iteration counter** and the safety fallback. Without it, a stuck job loops forever.
- **The IF combinator is `or`:** upstream reports done OR iteration cap hit.
- **"True" goes to the continue-workflow node, "false" feeds back** for the next poll cycle.
- **The done output (index 0) is unused** since `reset: true` never reaches the "ran out of items" state. Termination is the IF's job.

In practice, prefer a `Switch` over an IF, with a separate branch for "too many iterations" so a stuck upstream surfaces as an explicit error. See `n8n-error-handling-official`.

## Reset mode in general

`reset` is for indeterminate-length loops. The polling pattern above is one case. Others:

- Scraping pages until empty (though HTTP pagination is usually cleaner, see `HTTP_PAGINATION.md`).
- Recursive scraping/BFS where each iteration's input comes from the previous output.

```ts
{
    batchSize: 1,
    options: { reset: true },
}
```

With `reset: true`:

- Each iteration treats its input as the new "original" array.
- Usually feed the loop one item at a time (the next thing to process).
- Termination is your responsibility (an `IF` or `Switch` that breaks out).

Genuinely advanced. For paginated HTTP, use built-in pagination. For most "loop until done" cases, a self-calling sub-workflow or HTTP pagination is cleaner. Reach for `reset: true` only when those don't fit.

## Useful expressions inside the loop

- **`{{ $runIndex }}`**: current iteration (0-based). Short form. References the *current* node's run count, which inside a loop body equals the loop iteration.
- **`{{ $('Loop Over Items').context.currentRunIndex }}`**: explicit form for disambiguating multiple loops.
- **`{{ $('Loop Over Items').context.maxRunIndex }}`**: total iterations expected (`Math.ceil(items.length / batchSize)` at start). Useful for progress reporting.
- **`{{ $('Loop Over Items').context.noItemsLeft }}`**: boolean, true once the queue is drained. Becomes true on the iteration emitting the final batch, useful for "is this the last batch" branching inside the loop body.
- **`{{ $('Loop Over Items').item.json }}`**: current item from the current batch.

`context` answers "where are we?" without breaking per-item iteration.

## Common mistakes

### Wiring the wrong output index

Output 0 is **done**, output 1 is **loop**. Easy to flip. Symptoms: post-loop step never fires, or processing fires once with the full input.

Verify via `get_workflow_details` after wiring.

### Wiring the done output back into the loop

Done fires *once*, at the end. Wiring it back does nothing because the loop is finished. Done goes to the post-loop step.

### Forgetting the feedback edge

Without the per-batch tail connecting back to Loop Over Items, the loop fires the first batch and stops.

### Forgetting to `Split Out` before the loop

A single item containing an array (`{ items: [...] }`) makes the loop iterate once. Use `Split Out` (or `Set` with `=$json.items`) upstream.

### Using `Loop Over Items` for default iteration

To send 50 items through a sub-workflow, connect the source to `Execute Workflow`. Default iteration handles it.

### Per-batch HTTP without `executeOnce`

If the HTTP node should send the *whole batch* as one request, set `executeOnce: true`. Otherwise it fires once per item inside the batch.

### Reset loop with no termination

`reset: true` without a stop condition is an infinite loop. n8n eats memory until killed. Always have explicit termination (IF/Switch breaking out on stop) AND a `$runIndex` ceiling.

### Nesting Loop Over Items inside Loop Over Items

Doesn't work. Validation passes, breaks at runtime. Extract the inner loop into a sub-workflow and call it from the outer iteration via `Execute Workflow` with `mode: 'each'`.

## Verification before publishing

After wiring a `Loop Over Items` node, pull via `get_workflow_details` and verify:

1. **Loop output (index 1)** flows into per-batch processing AND back into the loop node.
2. **Done output (index 0)** flows into the post-loop step (or is unused for `reset: true` polling).
3. Aggregate nodes inside the loop or on the done branch have `executeOnce: true` if they should fire once.
4. Clear termination: bounded input array, or a stop branch with a `$runIndex` fallback.
