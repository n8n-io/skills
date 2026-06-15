# Merge node

Merge nodes have two configuration traps. Both fail silently:

1. **Wrong input count.** Merge defaults to **2 inputs**. If 3+ sources need to converge, you must explicitly set the input count on the node.
2. **Off-by-one between `useDataOfInput` and `.input(n)`** when porting from existing config. `useDataOfInput` is 1-indexed (matches UI labels); `.input(n)` is 0-indexed (matches every other array in code).

## Set the input count when you have 3+ sources

The Merge node's `numberOfInputs` parameter defaults to 2. If you're converging from 3 IF branches, or 4 parallel HTTP calls, or any source-count beyond 2, set it explicitly:

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

Then wire all 3 sources via `.input(0)`, `.input(1)`, `.input(2)`. Verify the parameter name on the user's n8n version via `get_node_types` for `merge` — the field name has shifted between versions.

Symptom of forgetting: the workflow validates and runs, but only the first 2 sources' items appear downstream. The third silently drops. Hard to spot in the canvas: the connection line is drawn, the node visually has 3 wires going in, but only 2 inputs exist on the node.

After wiring a Merge with 3+ sources, pull the workflow via `get_workflow_details` and confirm the `parameters.numberOfInputs` (or equivalent) matches your wire count.


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

## Composite handler shorthand for IF/Switch into Merge

```ts
.add(checkType.onTrue(merge.input(0)).onFalse(merge.input(1)))
```

Pre-2.21.4 this threw `MERGE_SINGLE_INPUT`: the branch handler hardcoded input index 0 and ignored the `.input(n)` selector. Since 2.21.4 ([n8n#29716](https://github.com/n8n-io/n8n/pull/29716)) the handler respects the selector and wires the branch to the named input. The universal pattern `.add(checkType.output(0).to(merge.input(0)))` still works; the shorthand is just shorter for IF/Switch-into-Merge.

## Why this exists

The Merge UI predates the SDK. 1-indexed labels match the user's mental model in the editor, and 0-indexed SDK matches every other array in code. Aligning would break one group.

On n8n's roadmap. Until then, use the translation rule.
