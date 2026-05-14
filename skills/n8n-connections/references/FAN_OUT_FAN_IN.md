# Fan-out and fan-in

One universal grammar covers both: `.add(source.output(n).to(target))`. The `.to()` trap from the parent SKILL.md applies to every example below.

## Fan-out: one source → many targets

Repeat `.add()` per wire.

### Fan-out branches run sequentially, not in parallel

Branches execute one at a time, top-to-bottom by Y-position (the order in `connections.<source>.main[0]`). Total runtime is the sum, not the max. Earlier branches' side effects are visible to later ones.

For real concurrency, dispatch via `Execute Workflow` with `mode: 'each'` + `options.waitForSubWorkflow: false`. See `n8n-subworkflows` `references/SUBWORKFLOW_PATTERNS.md` "Fire-and-forget parallelization".

### Same output, multiple targets

```ts
.add(source.output(0).to(targetA))
.add(source.output(0).to(targetB))
.add(source.output(0).to(targetC))
// All three targets land on source's main[0].
```

### Different outputs, multiple targets each (Switch)

```ts
.add(sw.output(0).to(caseA1))
.add(sw.output(0).to(caseA2))   // case 0 fans out
.add(sw.output(1).to(caseB))
.add(sw.output(2).to(caseC1))
.add(sw.output(2).to(caseC2))   // case 2 fans out
```

### Mixing composite handlers with `.output(n)`

Composite handlers (`.onTrue`, `.onFalse`, `.onCase`, `.onError`) compose cleanly with `.output(n)` on the same node:

```ts
.add(ifNode.onTrue(targetA))
.add(ifNode.output(0).to(targetB))
// Both end up on IF's main[0]. No conflict.
```

Don't avoid composites just because you also need a fan-out. They coexist.

## Fan-in: many sources → one target

Two flavors depending on whether the target has multiple inputs.

### Default input (most nodes)

For single-input nodes, just call `.add()` per source. All wire to `target`'s `main[0]`:

```ts
.add(sourceOne).to(receiver)
.add(sourceTwo).to(receiver)
.add(sourceThree).to(receiver)
// All three feed receiver.main[0].
```

This is the only place `.add(source).to(target)` is safe: no `.output(n)` selector inside `.add()`, so no trap. Equivalent to `.add(sourceOne.output(0).to(receiver))`, since n8n defaults to output 0 when no selector is given.

### Targeted input (Merge and other multi-input nodes)

Use `target.input(n)`. **0-indexed**:

```ts
.add(start).to(srcLeft).to(merge.input(0))    // input 0 (UI: "Input 1")
.add(start).to(srcRight).to(merge.input(1))   // input 1 (UI: "Input 2")
.add(merge).to(tail)
```

Indexing is the most common mistake here. See `MERGE_INDEX_RULES.md`.

## Things that look like fan-out/fan-in but aren't

### Linear chains with intermediate nodes

`.add(a).to(b).to(c).to(d)` is a linear chain (a → b → c → d), not a fan-out. Each `.to()` adds the next node downstream.

Fine: no `.output(n)` selector inside `.add()`, so no trap.

### Multiple `.add()` from the same node without selectors

```ts
.add(node).to(targetA)
.add(node).to(targetB)
```

Fan-out on default output, equivalent to repeated `.add(node.output(0).to(...))`. Safe and idiomatic.

## Verifying fan-out and fan-in landed

`validate_workflow` reports valid even when fan-outs are dropped or collapsed. Pull with `get_workflow_details` and check:

- Fan-out: each `connections[source].main[n]` is an array of expected length.
- Fan-in (default input): each source's `main[0]` includes the receiver.
- Fan-in (targeted input): each target connection's `index` matches the intended input.

Mismatches mean the workflow has the right shape on paper and the wrong shape in production.
