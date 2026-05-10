# Verification

`validate_workflow` does not catch the connection bugs that matter most. After every create or update, pull via `get_workflow_details` and inspect the `connections` object.

## Why validation isn't enough

`validate_workflow` catches:

- Missing required parameters
- Type mismatches in node config
- References to non-existent node IDs

It does NOT catch:

- The `.to()`-inside-`.add()` trap (silent dropped wires)
- Fan-outs collapsed to a single connection
- Merge index off-by-one (`useDataOfInput` vs `.input(n)`)
- Error outputs wired without `onError: 'continueErrorOutput'` (or vice versa)
- Connections to non-existent inputs on multi-input nodes

A workflow can pass validation, publish, and run with any of these. Runtime symptoms look like "the node didn't fire" or "wrong data came through": diagnosable but not obviously a connection issue.

## The checklist

After every `create_workflow_from_code` and `update_workflow`:

### 1. Pull the workflow back

```
get_workflow_details(id: <id from create/update>)
```

Returns the full workflow JSON with `nodes`, `connections`, and `settings`.

### 2. Walk every connection in your code and verify it landed

For each `.add(...)` call you wrote:

| Wrote | Check in `connections` |
|---|---|
| `.add(a.output(0).to(b))` | `connections.a.main[0]` includes `{ node: b.id, type: "main", index: 0 }` |
| `.add(a.output(0).to(b.input(2)))` | `connections.a.main[0]` includes `{ node: b.id, type: "main", index: 2 }` |
| `.add(a).to(b)` (fan-in default input) | `connections.a.main[0]` includes `{ node: b.id, type: "main", index: 0 }` |

### 3. Count fan-outs

For each output that should have multiple targets:

```
connections.<sourceNode>.main[<outputIndex>].length === <expected target count>
```

If it's 1 where 2+ was expected, a fan-out got dropped, most often via the `.to()` trap.

### 4. Verify error outputs are wired both ways

For every node with `onError: 'continueErrorOutput'`:

- Config has `"onError": "continueErrorOutput"`.
- `connections.<node>.main[1]` has at least one target.

`onError` set with empty `main[1]` = silent error drop. `main[1]` wired without `onError: continueErrorOutput` = unreachable.

### 5. Verify Merge inputs match `useDataOfInput`

For every Merge node:

- Read `node.parameters.useDataOfInput` (1-indexed).
- Find the connection feeding that input: `index === useDataOfInput - 1`.
- Confirm the source matches the intended upstream branch.

A wire on the right index from the wrong upstream means runtime passes wrong data. See `MERGE_INDEX_RULES.md`.

### 6. Confirm orphans are intentional

Nodes unreachable from any trigger don't fire. Decide whether that's intentional (commented-out branches, WIP) or a bug.

## When to redo

If any check fails:

1. Identify the bad connection in your SDK code.
2. Fix it (most often: move `.to()` inside `.add()`).
3. `update_workflow` with the fix.
4. Re-run the checklist.

Don't add nodes to "work around" a missing wire. Fix the wire.
