# Merge for keeping binary in context

Common: an item with both `json` and `binary` runs through a JSON-only operation (Edit Fields, Code, IF), binary disappears, but you need it downstream.

Fix: split the stream, do JSON work on one side, merge binary back.

## The pattern

```
[Source with binary] ─┬─→ [Edit Fields: transform JSON] ─┐
                      │                                    │
                      │   (binary stripped here)           ├─→ [Merge: byPosition] ─→ [Email with attachment]
                      │                                    │
                      └────────────────────────────────────┘
                          (passes binary through unchanged)
```

The Source feeds two branches:

- **Top branch:** the JSON transformation. Binary may be stripped.
- **Bottom branch:** original item with binary, unchanged. (No node needed, just route the connection.)

Merge produces a single item: JSON from top, binary from bottom.

## Configuring Merge

```ts
{
    type: 'n8n-nodes-base.merge',
    parameters: {
        mode: 'combineByPosition',    // or 'combineAll', 'append', etc.
        joinMode: 'enrichInput1',     // top branch's JSON wins
    },
}
```

Key choices:

- **`combineByPosition`**: item N from input 1 with item N from input 2.
- **`combineAll`**: Cartesian product.
- **`append`**: concatenate inputs.

For "combine JSON output with binary stream," `combineByPosition` is usually right.

## Why it works

Merge combines `json` and `binary` from its inputs. The side with binary preserves it, and combined with the side holding the JSON you want, the merged item has both.

## Alternative: pass-through in the transforming node

Some nodes preserve binary across the operation:

- Edit Fields: `includeOtherFields` parameter.
- Code: `return { json: ..., binary: item.binary }` explicitly.

If pass-through is available, use it. Fewer nodes than the Merge dance.

## When merge isn't enough

For complex workflows with many strip points:

- **Upload to storage early.** Pass URL/ID through the workflow, and fetch when needed.
- **Use a sub-workflow.** Pass binary in, sub-workflow returns final binary + JSON. Requires the Execute Workflow Trigger to use **passthrough input mode** (the default typed-input mode drops `$binary` at the boundary, since typed inputs only carry the named JSON fields). Set the trigger's input mode accordingly, otherwise the sub-workflow receives JSON-only items and the whole point is defeated. See `n8n-subworkflows-official` for input-mode setup and the broader sub-workflow pattern.

Threading binary through many JSON-transforming nodes means every node in the chain has to preserve it correctly, and any one of them silently dropping it forces another Merge. Past a couple of strip points, the storage or sub-workflow route is usually less work than keeping the chain honest.

## Verifying after merge

`test_workflow` and inspect via `get_execution`:

- Merged item's `json` matches the top branch.
- Merged item's `binary` matches the bottom branch.

If binary is missing, check the Merge mode (some don't combine binary) and that the source actually had binary.

## Common mistakes

### Stripping binary before noticing

By the time you notice, the original is gone. Test with `get_execution` after each node during development.

### "Merging" a single-source workflow

If only one branch had binary, there's nothing to merge with. The pattern requires splitting the stream so binary travels on one branch.

### Merge mode mismatch

`combineAll` when you wanted `combineByPosition` produces N×M items instead of N. Specify deliberately.
