# Merge index rules

Merge nodes have two traps. Both fail silently:

1. **Wrong input count.** Merge defaults to **2 inputs**. If 3+ sources need to converge, you must explicitly set the input count on the node. The third (and beyond) source connects to a slot that doesn't exist. The connection JSON has it, but at runtime the merge ignores it and passes through fewer items than expected.
2. **Off-by-one between `useDataOfInput` and `.input(n)`.** The two indexing systems disagree by one (covered below).

## Set the input count when you have 3+ sources

The Merge node's `numberOfInputs` parameter (or the equivalent on your n8n version) defaults to 2. If you're converging from 3 IF branches, or 4 parallel HTTP calls, or any source-count beyond 2, set it explicitly:

```ts
const mergeNode = merge({
    config: {
        parameters: {
            mode: 'append',           // or 'combine', etc.
            numberOfInputs: 3,        // <-- explicit count
        },
    },
})
```

Then wire all 3 sources via `.input(0)`, `.input(1)`, `.input(2)`. Verify the parameter name on the user's n8n version via `get_node_types` for `merge`. The field name has shifted between versions.

Symptom of forgetting: the workflow validates and runs, but only the first 2 sources' items appear downstream. The third silently drops. Hard to spot in the canvas: the connection line is drawn, the node visually has 3 wires going in, but only 2 inputs exist on the node.

After wiring a Merge with 3+ sources, pull the workflow via `get_workflow_details` and confirm the `parameters.numberOfInputs` (or equivalent) matches your wire count.

## The off-by-one

<!-- TEMPORARY: useDataOfInput 1-indexed vs .input(n) 0-indexed off-by-one -->

| Place | Indexing | Example |
|---|---|---|
| `.input(n)` (SDK target selector) | **0-indexed** | `merge.input(0)` = first input |
| Connection JSON `index` field | **0-indexed** | `"index": 0` = first input |
| `useDataOfInput` (Merge node parameter) | **1-indexed** | `"useDataOfInput": "1"` = first input |
| UI labels | **1-indexed** | "Input 1" = first input |

UI labels and `useDataOfInput` use 1-based numbering ("Input 1", "Input 2") to match what users see in the editor. The SDK and connection JSON use 0-based. They never match.

## The translation rule

When porting a workflow or reading `useDataOfInput` from existing config:

> If the source has `useDataOfInput: "N"`, the wire feeding that slot uses `.input(N - 1)`.

Examples:

| Merge config | Wire to use |
|---|---|
| `useDataOfInput: "1"` | `.input(0)` |
| `useDataOfInput: "2"` | `.input(1)` |
| `useDataOfInput: "3"` | `.input(2)` |

## Failure mode

Getting this backward (e.g., `.input(2)` for `useDataOfInput: "2"`) wires to input index 2 (the third input) instead of index 1 (the second). At runtime:

- The Merge passes through whatever sits at the 1-indexed `useDataOfInput` slot, now the wrong source.
- Downstream receives data from an unintended upstream branch.
- No error: both inputs are valid, but the contents are just wrong.

Looks identical to a "missing fan-out" because the shape is right but the contents are wrong. Symptoms: downstream conditional logic acts on stale data, and outputs reference real fields with values from a different code path.

## Worked example

A Merge with three inputs, configured to pass through Input 2:

**Config:**
```json
{ "useDataOfInput": "2" }
```

**Correct wiring (using the translation rule, N=2 → .input(1)):**
```ts
.add(start).to(srcA).to(merge.input(0))   // Input 1: ignored at runtime per useDataOfInput
.add(start).to(srcB).to(merge.input(1))   // Input 2: passed through
.add(start).to(srcC).to(merge.input(2))   // Input 3: ignored
```

**Wrong wiring (matching the numbers):**
```ts
.add(start).to(srcA).to(merge.input(1))   // ← wrong, srcA on Input 2
.add(start).to(srcB).to(merge.input(2))   // ← wrong, srcB on Input 3
.add(start).to(srcC).to(merge.input(3))   // ← wrong, srcC on (nonexistent) Input 4
```

At runtime, the wrong wiring passes through srcA's data (because `useDataOfInput: "2"` selects index 1 = `.input(1)`, now occupied by srcA), not srcB's. The user gets the wrong upstream branch with no clear signal why.

## Verification

After every create/update touching Merge:

1. Pull the workflow back via `get_workflow_details`.
2. For each connection feeding a Merge, find the connection's `index` field. That's the 0-indexed input.
3. Read the Merge node's `useDataOfInput` parameter.
4. Confirm `index === useDataOfInput - 1` for the wire that should be passed through.

If they don't line up, the workflow is silently broken.

## Why this exists

The Merge UI predates the SDK. 1-indexed labels match the user's mental model in the editor, and 0-indexed SDK matches every other array in code. Aligning would break one group.

On n8n's roadmap. Until then, use the translation rule.
