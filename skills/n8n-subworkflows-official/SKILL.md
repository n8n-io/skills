---
name: n8n-subworkflows-official
description: Use when building anything multi-step, anything that looks repeatable, anything the user mentions reusing, or any workflow with more than ~10 nodes. Triggers on "reuse", "I do this in another workflow", "extract", "modular", "shared logic", "subworkflow", multi-step builds, or any task that mentions logic the user has built before.
---

# n8n Sub-workflows

Sub-workflows are reusable functions. The `Execute Workflow Trigger` declares input parameters, the body does work, the last node returns output. Callers invoke it like any other node.

That framing opens up the function-shaped wins: encapsulation, reuse, testability, replaceability. It's the primary reuse mechanism in n8n, and unfortunately underused.

Without sub-workflows, the same logic gets duplicated across workflows. Bug fixes happen in multiple places, one gets missed, and "identical" copies drift.

## Non-negotiables

1. **Search before you build.** Before writing logic that handles a generic problem, check if a sub-workflow already exists. Filter by tag (`search_workflows({ tags: ['subworkflow'] })`, a domain tag) and/or keyword (`query: '<keyword>'`). Tags are the discovery mechanism (n8n 2.27.0+).
2. **`Execute Workflow Trigger` uses "Define Below" with typed fields, not passthrough.** Define Below is the only mode that lets agent tools (`fromAi`) and structured callers pass values in. Two exceptions: (a) the sub-workflow specifically needs to receive binary (then it can't be wired as an agent tool directly), or (b) the sub-workflow takes no inputs at all (Define Below requires at least one field). See "Sub-workflow inputs and outputs" below.

## Strong defaults

- **Anything reusable becomes a sub-workflow.** If a logical chunk could plausibly be needed elsewhere, extract it. Exception: trivial wrappers (one HTTP call, no logic) and tightly-coupled-to-this-caller chunks.
- **Default to stateless for pure logic** (input → output, no external state). For state-touching logic, build *deliberately* stateful sub-workflows that abstract the operation behind a clean contract (the ORM / repository pattern). What to avoid is *accidental* state: a "validate" sub-workflow that quietly writes to a log table.
- **Tag for discovery**: every sub-workflow gets `subworkflow`, a domain tag (`customer`), and/or `tool`. Tags are what `search_workflows({ tags })` filters on; names stay plain and descriptive (`Parse RFC2822 date`). See `references/NAMING_AND_DISCOVERY.md`.
- **Description carries keywords.** Input/output shape + representative terms, so varied queries surface it.
- **Split when input contracts genuinely differ** (binary vs JSON, sync vs async, divergent auth schemes). Don't fit divergent contracts under one trigger via passthrough + internal branching. See `references/SUBWORKFLOW_PATTERNS.md` "Splitting by input shape".

## Decision tree: should this be a sub-workflow?

```
About to write a chunk of logic?
├── Could this plausibly be needed in another workflow?
│   ├── Yes → extract to sub-workflow
│   └── No → keep inline
│
├── Is this chunk >5 nodes and conceptually one thing?
│   └── Extract if you want testability, isolation, or reuse; if it's only for a cleaner canvas, group it inline instead (see below).
│
├── Is this chunk dealing with a generic concern (auth, retry, parsing, formatting)?
│   └── Almost certainly extract. These are the canonical reusable sub-workflows.
│
└── Is this chunk doing one HTTP call with no logic around it?
    └── Don't extract. Extra workflow boundary for nothing.
```

When the only motivation is a cleaner canvas (not reuse, isolation, testability, or an agent tool), a **canvas node group** is the default tool for readability-only sectioning: faster (no sub-execution per call) and simpler (no input/output contract), with the logic staying inline. Group it where the section forms a valid group (connected, single entry/exit), otherwise use a sticky note. Extract to a sub-workflow only when you genuinely need reuse, isolation, independent testing, or an agent tool. See `n8n-workflow-lifecycle-official` Readability.

## Stateless vs. stateful sub-workflows

Both are first-class. The choice is about intent and encapsulation.

### Stateless

Takes input, returns output. No I/O outside the inputs/outputs. Default for pure logic.

Examples:

- `Parse RFC2822 date` (tag `subworkflow`). Input: date string. Output: ISO date or error.
- `Compute MRR from subscription` (tag `subworkflow`). Input: subscription object. Output: MRR number.
- `Format invoice as HTML` (tag `subworkflow`). Input: invoice data. Output: HTML string.

When you need the logic again, call it without worrying about side effects firing.

### Stateful (deliberate)

Reads or writes external state behind a clean input/output contract. Comparable to a repository pattern: the sub-workflow abstracts the state operation so callers think in domain terms, not implementation.

Examples:

- `Get customer by id` (tag `customer`). Input: id. Output: customer object or `{ ok: false, error: 'not_found' }`. Reads the DB.
- `Write customer billing record` (tags `customer`, `billing`). Input: record. Output: `{ ok: true, id }`. Writes the DB.
- `Append audit event` (tag `audit`). Input: event. Output: `{ ok: true, eventId }`. Writes to a logging store.
- `Send to on-call` (tag `notification`). Input: channel, message. Output: `{ ok: true, messageId }`. Calls Slack/SMTP.

The point of building these as sub-workflows:

- Callers think in domain terms (`get customer by id`), not in storage (`SELECT * FROM customers ...`).
- Swap the underlying store/API behind it (Postgres → Supabase, native node → HTTP) without touching callers.
- Idempotency, retry, and validation become the sub-workflow's responsibility, centralized in one place.

What to avoid is *accidental* state: a sub-workflow named/described as pure that quietly writes to a log table. That ambushes callers who reasonably assumed it was safe to retry or compose. Either make the side effect part of the contract (rename, document, return its result) or move it out.

## When to extract

The two main signals:

### 1. Conceptual coherence

When a chunk of nodes does one logical thing, even unreused, extraction can be worth it for:

- **Testability.** Run the sub-workflow on its own with pinned data.
- **Replaceability.** Swapping implementations doesn't ripple to callers.

Readability alone is not a reason to extract: a node group collapses five nodes into one labeled box more cheaply (no sub-execution, no input/output contract). Extract when you also want testability, replaceability, or reuse.

### 1.5 The fire-and-forget audit-log pattern

> Audit logging is used here as a concrete illustration of the fire-and-forget stateful pattern. **Don't add audit logging to a workflow unless the user asked for it.** The pattern itself (fire a sub-workflow async, don't block on it) generalizes to any side observation: metrics, notifications, etc.

A deliberately stateful audit-log sub-workflow invoked with `Execute Workflow`'s `waitForSubWorkflow: false` so the caller doesn't block on the write.

```
Caller ──→ [Execute Workflow: DB audit log]
              { title: 'Email Confirmation Received',
                description: <serialized data> }
              waitForSubWorkflow: false
              ↓ (caller continues immediately)
        ──→ [Continue with next step]
```

The sub-workflow takes a title and description, writes to a logging table (or Slack, or both), returns. The caller doesn't wait. Audit log is a side observation, not the critical path.

When the user has asked for it, fire one at every meaningful state transition ("email confirmation received", "user verified", "processing started", "eligibility decision made") so the timeline reconstructs from logs.

Why it's valuable:

- **Observability for free.** Per-execution timeline when something goes wrong.
- **No coupling.** Implementation (DB, Slack, both) can change without touching callers.
- **Async by default.** `waitForSubWorkflow: false` means the audit doesn't slow the main workflow.

The audit-log workflow is the right kind of stateful sub-workflow. The side effect is the point.

### 1.7 The middleware pattern

When a webhook workflow is API-shaped, treat it like one. Sub-workflows become middleware: small stateless functions that run before the main handler and either pass through or short-circuit with a 4xx.

```
Webhook
  → [Verify JWT]    # decode + validate; 401 on failure
  → [Rate limit]    # check + bump counter; 429 on failure
  → IF (all middleware ok)
    → Main handler logic
    → Respond 200
  → ELSE → Respond with the 4xx the middleware returned
```

Canonical example: custom JWT auth rolled inside n8n. `Verify JWT` (tag `subworkflow`) takes the raw `Authorization` header, decodes, validates signature and expiry, returns `{ ok: true, user_id }` or `{ ok: false, status: 401, message }`. The caller IFs on `ok`, responds early on failure, continues on success.

Why a sub-workflow and not inline: every webhook that needs auth calls the same one. Swap the library, rotate the signing key, or add refresh-token logic in a single place. The reuse target is exact, the contract is small, and the failure response shape is consistent across every API endpoint.

Pairs with `n8n-error-handling-official` for 4xx/5xx response shapes and `n8n-credentials-and-security-official` for the underlying secret handling.

### 2. Repetition pattern

You're about to build something you've built before. Stop. Search.

```
search_workflows({ query: 'date' })
search_workflows({ tags: ['customer'] })
search_workflows({ tags: ['subworkflow'] })
```

If something matches, use it. If not, build it as a sub-workflow and tag it so the *next* search finds it. The tag convention (`subworkflow`, domain tags, `tool`) is what makes that work.

## Linear, long workflows are fine when most of the work is in sub-workflows

A workflow can have 20+ nodes and still be readable if it's mostly a linear orchestration of sub-workflow calls and decisions. The shape (audit-log nodes shown only because they're a vivid example of "side observation between real steps", include them only if the user asked for audit logging):

```
Webhook
  → Audit log (sub-workflow)
  → Validate
  → Audit log (sub-workflow)
  → IF auth ok
    → Look up user (or sub-workflow)
    → Audit log (sub-workflow)
    → Process step 1 (sub-workflow)
    → Audit log (sub-workflow)
    → Process step 2 (sub-workflow)
    → Audit log (sub-workflow)
    → Decide eligibility (sub-workflow)
    → Audit log (sub-workflow)
    → Send notification (sub-workflow)
    → Respond
```

Each "logical step" is a sub-workflow call. The caller is a long but linear narrative, easy to follow top-to-bottom. Logic lives in the sub-workflows.

This is *not* the same as a 20-node workflow with 20 inline transformations. That's hard to read. The pattern above is fine because:

- Each node has one purpose (call a specific sub-workflow).
- Sticky notes and node groups mark sections (per `n8n-workflow-lifecycle-official` "Readability").
- Inspecting a section means opening the sub-workflow it calls. That's encapsulation.
- Orchestration logic at the top level is visible without reading implementations.

If your workflow has 15+ nodes and isn't mostly Execute Workflow calls and branches, extract more where reuse or testing warrants it, and group the rest inline (node groups).

## When NOT to extract

- **One HTTP call with no logic.** A sub-workflow that's just `Execute Workflow → HTTP Request → return` adds a boundary for nothing. Inline it.
- **Tightly coupled to the caller's specific shape.** If the chunk takes a deeply nested input that only this caller produces, extracting it just relocates the coupling. Fix the data shape first.
- **Performance-critical hot paths.** Each sub-workflow call adds latency (small, but real). For high-throughput workflows, profile before adding boundaries.

## Search-before-build protocol

When the user describes something multi-step or generic-sounding:

```
1. search_workflows with relevant tags and/or query (e.g. `tags: ['subworkflow']`, a domain tag, the operation keyword)
2. If candidates appear, fetch get_workflow_details on the top 1-3
3. Confirm fit by reading the inputs/outputs and (briefly) the body
4. If a fit exists → use it. Tell the user "I found `<name>`. Using that."
5. If no fit exists → build new and tag it (`subworkflow`, domain, `tool`) so the next search finds it
```

The "tell the user" step matters. They benefit from knowing what's already in their library.

If a workflow you expect to find isn't appearing, the most common cause is per-workflow MCP access not being enabled. See `n8n-workflow-lifecycle-official` `references/MCP_ACCESS_PER_WORKFLOW.md`.

## Sub-workflow inputs and outputs

Sub-workflows are triggered by `Execute Workflow Trigger` nodes. The trigger declares the input schema. The caller passes data via `Execute Workflow`, and the sub-workflow returns whatever its last node outputs.

### Always use "Define Below" with explicit fields

The `Execute Workflow Trigger` has two input modes. **Default to "Define Below" (typed fields).** This is the only mode that lets agent tools (via `fromAi()`) and any structured caller pass values in. Without declared fields, the agent has no schema to fill and the sub-workflow can't be wired as a `toolWorkflow` cleanly.

Shape:

```ts
const subTrigger = trigger({
    type: 'n8n-nodes-base.executeWorkflowTrigger',
    config: {
        parameters: {
            workflowInputs: {
                values: [
                    { name: 'list_of_ids', type: 'array' },
                    { name: 'include_transcript', type: 'boolean' },
                    { name: 'session_id', type: 'string' },
                ],
            },
        },
    },
})
```

Each declared input becomes a typed parameter the caller can fill. Inside the workflow, access via `$json.list_of_ids`, etc., or `$('When Executed by Another Workflow').first().json.<field>` from anywhere downstream.

Pick types deliberately (`string`, `number`, `boolean`, `array`, `object`). The model uses these as the required types when filling agent tool parameters, and humans rely on them when wiring callers.

### Exception 1: passthrough mode for binary

If the sub-workflow needs to receive binary (image, file, PDF), `Define Below` doesn't work because typed fields are JSON only. Switch to passthrough:

```ts
const subTrigger = trigger({
    type: 'n8n-nodes-base.executeWorkflowTrigger',
    config: {
        parameters: {
            inputSource: 'passthrough',
        },
    },
})
```

In passthrough mode, the sub-workflow receives the caller's items as-is, including the `binary` slot. Cost: no typed input schema, so agent tools can't pass parameters through `fromAi()`. Use this mode for sub-workflows called by other workflows (not agents) where binary needs to flow through.

For sub-workflows that need binary AND are called by an agent, see `n8n-binary-and-data-official` `references/AGENT_TOOL_BINARY.md` (agent tools can't pass binary directly).

### Exception 2: passthrough for sub-workflows with no inputs

Define Below requires at least one declared field. A sub-workflow that genuinely takes no inputs (a "list active credentials" tool, a "current count" lookup, any zero-arg operation) has nowhere to put the empty schema, so passthrough is the only option.

When using passthrough specifically for the no-input case:

- **Start the body with a `Set` (Edit Fields) node in "Keep Only Set" mode with no fields.** This clears the caller's JSON so downstream nodes don't accidentally read fields from whatever shape the caller happened to pass. Without it, the body silently picks up whatever the caller forwarded.
- **Add a sticky note on the trigger documenting that no inputs are expected.** Future readers (and the agent re-wiring this as a tool) need to know passthrough isn't here for binary, it's here because the schema is empty by design.

Agent-tool wiring still works in the no-input case: `toolWorkflow` accepts a sub-workflow whose input mapping has no fields. The agent's only decision is whether to invoke. The pattern from `n8n-agents-official` `references/TOOLS.md` ("zero `fromAi` parameters") applies directly.

### Other conventions

- **Document inputs and outputs in the workflow `description`.** Field names, types, purpose. The description is what callers (humans and agents) read for the contract.
- **Return a consistent shape.** For expected failures (e.g., parse error), return `{ success: false, error: '...' }` rather than throwing. Callers can branch without wrapping error outputs.
- **Treat the input schema as a contract once it has callers.** Adding optional fields is safe. Renaming or removing fields can be done, but only carefully: enumerate every caller (`search_workflows` for the sub-workflow's name + manual scan), migrate them in the same change, and verify with `validate_workflow` + `get_workflow_details` before publishing. A silent break here is hard to detect because n8n won't error on an unrecognized input field. The sub-workflow just sees `undefined` and the caller has no idea.
- **Use a final Set / Edit Fields node to shape the return.** Optional, sometimes required (when the last computation node carries noise fields), and good practice for sub-workflows even when not strictly required. It makes the return contract explicit at the boundary, so readers see the API by reading one node. This is the legitimate exception to the Set-node antipattern from `n8n-expressions-official`: the implicit consumer of a sub-workflow's last node is *every caller*, so the Set earns its place as the explicit API boundary. Name it `Return` or `Return <thing>`.
- **Return natural shapes, not storage shapes.** A sub-workflow that owns a Data Table, a file in S3, or any storage layer should hide that representation from callers. Arrays return as arrays, objects as objects, dates as ISO strings, regardless of whether the underlying storage was JSON-stringified text or another internal format. The return contract is the *interface*. The storage layout is *implementation detail*.

  Common slip: a sub-workflow has a "fresh" path (data just produced, natural shape) and a "cached" path (data just read from a `_object` column, still stringified). Wrong instinct: stringify the fresh path "to match" the cached path. Right instinct: parse the cached path so both return the natural shape. Callers shouldn't have to know which they got.

For sub-workflows wired as agent tools specifically, see `n8n-agents-official` `references/SUBWORKFLOW_AS_TOOL.md`.

## Calling sub-workflows: `Execute Workflow` modes

Two settings on the caller-side `Execute Workflow` node beyond inputs/workflowId:

- **`mode`** defaults to `'all'`: the sub-workflow runs **once** with all N items as input. Items still flow through nodes per-item like any other workflow. Set `mode: 'each'` to run the sub-workflow N separate times, one item per execution. For sub-workflows whose body just processes items normally, the two are equivalent. The split matters when the sub-workflow's body assumes it sees exactly one item (per-run aggregation, "this is THE customer to operate on" logic, a final write that should fire once per input). `mode: 'each'` matches that assumption, `mode: 'all'` breaks it. When you DO need per-item iteration, prefer `mode: 'each'` over a Loop Over Items node inside the sub-workflow.
- **`waitForSubWorkflow`** defaults to `true`. Setting `options.waitForSubWorkflow: false` fires the call and immediately moves on, and the sub-workflow continues in the background. The caller's downstream sees no return data.

`mode: 'each'` + `waitForSubWorkflow: false` is **the only true parallelization n8n offers**: N sub-workflow executions dispatched without waiting, running concurrently (still bounded by per-instance concurrency limits and per-call overhead). Useful for "kick off N independent jobs, poll/aggregate later". For example: dispatch a long-running job per item, track each in a Data Table, then loop until all rows mark themselves complete or time out.

For the polling-after-fire-and-forget pattern, see `references/SUBWORKFLOW_PATTERNS.md` "Fire-and-forget parallelization".

## Reference files

| File | Read when |
|---|---|
| `references/SUBWORKFLOW_PATTERNS.md` | `mode: 'all'` vs `'each'` default, splitting by input shape (binary/passthrough vs Define Below), fire-and-forget parallelization with Data Table polling |
| `references/NAMING_AND_DISCOVERY.md` | Naming and tagging a new sub-workflow, searching for existing ones, the tag convention |

## Anti-patterns

| Anti-pattern | What goes wrong | Fix |
|---|---|---|
| Duplicating the same date-parsing nodes in three workflows | Bug fixes happen in two places, miss the third | Extract to a single `Parse <format> date` sub-workflow (tag `subworkflow`) once |
| Building a new sub-workflow without searching | Library grows duplicates, and future searches find both | Always `search_workflows` first |
| Sub-workflow named/described as pure that quietly writes to a log table | Callers can't reason about retry or idempotency, side effect ambushes them | Either make the side effect part of the contract (rename, document, return its result) or move it out |
| Sub-workflow with no `description` | Won't be found in future searches, nobody knows what it does | Set `description` with input/output shape and purpose |
| Sub-workflow named `Helper 3` | Name doesn't tell anyone what it does | Verb-first descriptive name (`Parse RFC2822 date`), see `n8n-workflow-lifecycle-official` `NAMING_CONVENTIONS.md` |
| Untagged sub-workflow | Won't show up under any `tags` filter, future you can't find it | Tag it (`subworkflow`, domain, `tool`) right after create via `update_workflow` `addTags` |
| `Execute Workflow Trigger` set to `passthrough` when not handling binary and not deliberately zero-input | No typed schema means agent tools can't fill parameters via `fromAi`, structured callers can't pass values cleanly | Use "Define Below" with declared `workflowInputs.values` (name + type per field). The exceptions are binary-receiving sub-workflows and sub-workflows that genuinely take no inputs (see "Exception 2") |
| Passthrough trigger for a zero-input sub-workflow without a Set-to-clear node and explanatory sticky | Body silently reads stray fields from whatever the caller forwarded; future readers think passthrough is for binary | Add a `Set` ("Keep Only Set", no fields) at the top of the body and a sticky on the trigger noting no inputs are expected |
| Sub-workflow called as an agent tool that expects binary input | Agent tools can't pass binary directly | See `n8n-binary-and-data-official` `AGENT_TOOL_BINARY.md` for the right pattern |
| 30-node workflow with no extraction | Hard to read, hard to test, hard to replace | Extract logical sections into sub-workflows |

