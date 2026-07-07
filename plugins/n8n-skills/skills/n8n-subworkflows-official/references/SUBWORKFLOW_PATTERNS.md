# Sub-workflow patterns

Three distinctive n8n patterns that aren't derivable from the SKILL.md decision tree.

## `mode: 'all'` vs `'each'`

| `mode` | Sub-workflow executions | Items per execution |
|---|---|---|
| `'all'` (default) | 1 | All N items, flowing through normally (per-item like any workflow) |
| `'each'` | N | 1 item per execution |

For most sub-workflows whose body just processes items normally, the two are equivalent, since n8n nodes default to per-item processing either way.

The split matters when **the sub-workflow's body assumes it sees exactly one item** (per-run aggregations, "this is THE customer to operate on" logic, a final write that should fire once per input). With `mode: 'all'`, that body sees all N items at once and the assumption breaks. With `mode: 'each'`, each invocation gets exactly one item, matching the assumption.

## Splitting by input shape

**Principle: when a sub-workflow has multiple input paths whose contracts genuinely differ, split into one outer sub-workflow per contract, all calling a shared downstream sub-workflow for the common work.**

The forcing function in n8n: passthrough (required for binary, also required when the sub-workflow takes no inputs since Define Below needs at least one field) and Define Below (required for typed inputs agent tools and structured callers can fill) are mutually exclusive on one trigger. Common cases:

- **Binary vs non-binary input** (canonical).
- **Sync vs async paths** with different return contracts.
- **Different auth schemes per path.**

If the body has a top-level IF/Switch on which input shape arrived, that branch is the seam where two sub-workflows want to be separated.

### The reflexive mistake

The reflex when faced with two divergent input shapes:

- Pick passthrough (most permissive, supports binary).
- Branch internally on a flag.
- Live with the loss of typed inputs.

Why it's wrong:

- The workflow can't be exposed as a clean agent tool (passthrough has no `fromAi` schema).
- Body-shape branches accumulate ("in case A this field is set, in case B it's empty...").
- A future third input shape means more branching, not a clean third sub-workflow.

### The fix: N+1 sub-workflows

For N divergent input shapes, build N+1 sub-workflows: one outer per input contract, plus one shared downstream for the common work.

Each outer sub-workflow does its input-specific prep (validation, fetching, normalization, hashing, extraction) and calls the shared downstream with a normalized shape. The shared core has a single typed input contract and knows nothing about which outer called it.

#### Worked example

A "process this paper" capability that can come from either an external ID or a user-uploaded PDF:

```
Process Paper from External ID            (tag subworkflow)
  Trigger: Define Below { arxivId: string, source: string }
    → [Validate ID, dedup, fetch metadata, download PDF, extract text]
    → [Execute Workflow: Summarize and Store Paper]
        with { arxivId, title, authors, body, source, ... }

Process Paper from Uploaded PDF           (tag subworkflow)
  Trigger: Passthrough  (required: binary flows through)
    → [Hash binary for synthetic ID, dedup, extract text]
    → [Execute Workflow: Summarize and Store Paper]
        with { arxivId: '<synthetic>', title, body, source: 'upload', ... }

Summarize and Store Paper                 (the shared core, tag subworkflow)
  Trigger: Define Below { arxivId, title, body, source, ... }
    → [LLM with structured output, Data Table Insert, return result]
```

The pattern generalizes: any time a capability has both a "pull" path (look up by ID) AND a "push" path (data already in hand, including binary or template), the split applies.

## Fire-and-forget parallelization

`mode: 'each'` + `options.waitForSubWorkflow: false` is the only way to get genuine concurrent sub-workflow execution in n8n. N input items dispatch N sub-workflow runs that execute in parallel.

The catch: the caller doesn't know when (or whether) any of them finished. So this is only useful with **a separate completion-tracking mechanism**, typically a Data Table the sub-workflow writes to as it progresses.

### The pattern

1. **Stage:** insert one "in progress" row per parallel job, keyed by run ID + per-job sub-key.
2. **Dispatch:** call `Execute Workflow` with `mode: 'each'` and `options.waitForSubWorkflow: false`. Caller continues immediately.
3. **Each sub-workflow:** does its work, then updates ITS row (status `completed` / `error`, plus output).
4. **Poll:** caller enters a loop:
   - Get all rows for this run ID.
   - IF all rows in a terminal status → exit, aggregate.
   - ELSE IF runtime cap exceeded → mark remaining as `timeout`, exit.
   - ELSE → Wait, loop back to the Get.

```
[Source: N items]
  → [Data Table Insert: N rows, status='inProgress']
  → [Execute Workflow]                   # mode: 'each', waitForSubWorkflow: false
  → [Data Table Get: rows for this run]
  → [IF all terminal?]
      ├── Yes → continue
      └── No  → [IF under runtime cap?]
                 ├── Yes → [Wait Ns] → loop back to Data Table Get
                 └── No  → [Update remaining rows to 'timeout'] → continue
```

If a sub-workflow crashes without updating its row, the polling loop sees `inProgress` past the runtime cap and times it out.


### When this earns its place

- **Long per-item work** (LLM calls, large media, slow APIs) where serial would take hours.
- **Independent jobs** that can complete or fail without affecting others.
- **You can afford eventual consistency.** The polling loop adds latency.

When wrong:
- Short per-item work (under a second or two): default per-item iteration is simpler.
- Taking long doesn't matter. Then the complexity and added fragility isn't worth it
- Jobs that depend on each other's output: use sequential `mode: 'each'` with `waitForSubWorkflow: true`.
- Strict ordering requirements: parallelization gives up ordering.
