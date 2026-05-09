---
name: n8n-connections
description: Use when writing or reviewing n8n SDK code that wires IF, Switch, Merge, error outputs, or any multi-input/multi-output connection. Triggers on .add(), .to(), .input(n), .output(n), .onTrue, .onFalse, .onCase, .onError, useDataOfInput, merge, switch, IF nodes, error branches, fan-out, fan-in, or any review of the workflow's connections object.
---

# n8n Connections

n8n's SDK has a small connection grammar. Two of its shapes silently produce broken workflows that pass validation. This skill is mostly about not falling into those traps.

## The non-negotiable: the `.to()` trap

**`.to()` must go inside `.add()`, not after.**

```ts
.add(node.output(0)).to(target)      // ❌ connection silently dropped
.add(node.output(0).to(target))      // ✅
```

`validate_workflow` does **not** catch this. The workflow validates, publishes, and runs without the wire. The bug looks identical to a misconfigured or "not firing" node.

If you've written `.add(...).to(...)` outside the parens, you have a bug. No exceptions.

<!-- TEMPORARY: .to()-after-.add() silent drop -->

## The universal connection pattern

One shape covers IF/Switch branches, error outputs, merge inputs, and any generic multi-IO:

```ts
.add(source.output(n).to(target))
```

- `source.output(n)`: pick the output (0-indexed)
- `.to(target)`: pick the target (default input 0)
- `.to(target.input(m))`: pick a specific input on the target (0-indexed)

Call `.add()` once per wire. To fan out, repeat `.add()`.

## Decision tree

```
Wiring a connection?
├── Linear (one source → one target, single output, single input)?
│   └── .add(source).to(target). The simple case; .to() outside is fine here
│       because there's no .output(n) selector inside .add()
│
├── Selector involved (.output(n) or composite handlers)?
│   └── .to() MUST go inside .add(). See "the trap" above
│
├── Targeting a specific input slot on a multi-input node (Merge)?
│   └── .add(source.output(n).to(target.input(m)))
│       AND check useDataOfInput. See references/MERGE_INDEX_RULES.md
│
├── Error branch?
│   └── .add(node.output(1).to(handler))
│       AND set onError: 'continueErrorOutput' on the node config.
│       See references/ERROR_OUTPUTS.md
│
└── Fan-out (one source → many targets) or fan-in (many sources → one target)?
    └── See references/FAN_OUT_FAN_IN.md
```

## Composite handlers (`.onTrue`, `.onFalse`, `.onCase`, `.onError`)

The SDK provides convenience handlers on IF, Switch, and any node with an error output:

```ts
.add(ifNode.onTrue(targetA))     // same as .add(ifNode.output(0).to(targetA))
.add(ifNode.onFalse(targetB))    // same as .add(ifNode.output(1).to(targetB))
.add(sw.onCase(2, target))       // same as .add(sw.output(2).to(target))
.add(node.onError(handler))      // same as .add(node.output(1).to(handler))
```

These compose with `.output(n)` calls without conflict.

```ts
.add(ifNode.onTrue(targetA))
.add(ifNode.output(0).to(targetB))
// Result: BOTH targetA and targetB on IF's main[0]. Composite + .output(n) merge.
```

The only shape to avoid is the `.add(selector).to(target)` trap above. That's always wrong, regardless of whether a composite handler ran earlier.

## After every create or update: verify

`validate_workflow` reports valid even when wires are missing. After `create_workflow_from_code` or `update_workflow`, pull with `get_workflow_details` and check the `connections` object:

- Each `main[i]` has the expected **set** of targets (fan-outs preserved, not collapsed).
- Merge inputs land on the right indices, and `useDataOfInput` matches the wiring.
- Error-output nodes have `onError: 'continueErrorOutput'` AND `main[1]` wired to a handler.

If any check fails, the workflow is broken despite passing validation. Fix and re-update.

See `references/VERIFICATION.md` for the full post-create checklist.

## Reference files

Read the file that matches the situation. Don't read all of them:

| File | Read when |
|---|---|
| `references/FAN_OUT_FAN_IN.md` | One source → many targets, or many sources → one target |
| `references/MERGE_INDEX_RULES.md` | Wiring a Merge node, or you see `useDataOfInput` in node config |
| `references/ERROR_OUTPUTS.md` | Adding error handling on an individual node (not error workflow, that's `n8n-error-handling`) |
| `references/VERIFICATION.md` | Just created or updated a workflow with non-trivial connections |

## Anti-patterns

| Anti-pattern | What goes wrong | Fix |
|---|---|---|
| `.add(node.output(0)).to(target)` | Wire silently dropped, validation passes | Move `.to()` inside `.add()` |
| Mixing `useDataOfInput: "2"` with `.input(2)` | Off-by-one, wire feeds the wrong input | Use `.input(N - 1)` when `useDataOfInput: "N"`. See `MERGE_INDEX_RULES.md` |
| Error branch wired without `onError: 'continueErrorOutput'` | Branch is unreachable, and node fails the whole workflow on error | Set `onError: 'continueErrorOutput'` on the node config |
| Skipping `get_workflow_details` after create | Silently broken workflows ship | Always pull and inspect after create/update |
| Reading all four reference files before wiring one connection | Wasted context | Read only the file matching the situation |

