---
name: n8n-debugging-official
description: Use when an n8n workflow isn't working, errors appear, results don't match what was expected, or the user says "this isn't working." Triggers on errors, unexpected output, "it's not working", "why is this happening", "the workflow stopped", failure investigation, or any debugging context.
---

# n8n Debugging

When something breaks, the cause is almost always:

1. **Parameter misconfiguration** (wrong value, wrong type, missing field).
2. **Stale assumptions** (different version, different behavior than you remember).
3. **Paths misconfigured or misconnected** (wrong output index, wrong merge input, missing wire, IF/Switch wired to the wrong branch).
4. **Upstream data stripped** (an intermediate node replaced `$json` with its own output, so downstream `$json.x` resolves to null even though "it should be there"). Fix: reference the stable upstream node by name (`$('Earlier Node').item.json.x`).
5. **Item context lost** (after Aggregate, Execute Once, or Split Out flows, n8n can't pair `.item` references deterministically, error reads like "The expression is referencing... multiple matching items"). Fix: Merge node to re-establish context, `$input.all().find(...)` for explicit lookup, or redesign to keep item correspondence stable (e.g., split into stateless sub-workflows).
6. **Logical errors** (the wires are right and the parameters are right, but the workflow does the wrong thing, same as a logic bug in code).
7. **Genuine bug** (rare but real).

Diagnose systematically: cheap checks first, deeper investigation only when those fail.

## Non-negotiable

**Believe the user.** "This isn't working" means something isn't behaving as they expect, even if they describe the symptom imprecisely. Don't dismiss with "it should work" or "are you sure you're doing X?". Investigate first: the user is truth about what *should* happen, execution data and source are truth about what *is* happening. When you can't find the cause, "I don't know yet" beats a plausible-sounding fabrication.

## Strong defaults (cause to cheap check)

Match cause to cheap check, in order of likelihood:

1. **Parameter misconfiguration** → re-fetch via `get_node_types`, compare against `get_workflow_details`, look for type/value/missing-field mismatches. `validate_node_config` on the failing node alone returns per-parameter errors directly; faster than eyeballing the diff for nodes with deep / conditional shapes.
<!-- TEMPORARY: when instance metadata tool is added, change asking user to just using the tool -->
2. **Stale assumptions** → ask the n8n version, ask when the user last updated the skills plugin, suspect drift if behavior contradicts the skill.
3. **Paths misconfigured or misconnected** → inspect the `connections` object via `get_workflow_details`. For Merge input mismatches, see `n8n-node-configuration-official` `references/MERGE_NODE.md`.
4. **Upstream data stripped** → trace `$json.x` references back through the chain, look for any node that replaces the json with its own output. Common offenders: Aggregate, HTTP-binary, Extract from File, Code in "Run for All Items" mode, branching Merge. Not exhaustive: any node can do this if its output shape doesn't include the upstream fields.
5. **Item context lost** → check downstream of any Aggregate / Execute Once / Split Out for `.item` references, switch to `$input.all().find(...)` or a Merge anchor.
6. **Logical errors** → trace data through `get_execution` step by step, compare each node's output vs. expected.
7. **Genuine bug** → fall through to reading the n8n source, then GitHub issues, then a workaround.

For external API problems, the upstream service's API docs (not n8n's wrapper) are the truth. Fetch API docs and n8n's source code to debug if required.

## Step-by-step walkthrough

When the cheap checks above don't immediately pinpoint the cause, work through these in order.

### Step 1: confirm the symptom

Ask:

- What did they expect?
- What actually happened?
- Error message text?
- When did it last work? What changed since?

Vague ("it's broken") becomes tractable when concrete ("email sends to wrong address" or "workflow returns 500 with empty body").

### Step 2: check the execution

```
get_execution({ executionId: <execution_id>, workflowId: <workflow_id>, includeData: true })
```

Look at:

- **Which node failed?**
- **What input did it have?**
- **What error message?** Read carefully. Usually points at the cause.

No execution ID? Ask the user to re-run.

### Step 3: re-fetch the workflow

```
get_workflow_details({ workflowId: <workflow_id> })
```

Confirm the actual current state. The user might be looking at a different workflow or remembering a stale version.

Compare:

- Nodes vs. the user's mental model.
- Connections vs. intent: pull via `get_workflow_details` and compare the `connections` object to the SDK code.
- Credentials vs. expected (per `n8n-credentials-and-security-official`).
- **Upstream-strip risk:** any node between a data source and a downstream `$json.x` consumer that replaces the json with its own output? Common offenders are HTTP-binary, Extract from File, Aggregate, Code in "Run for All Items" mode, and branching Merge, but any node can do this if its output shape doesn't include the upstream fields. The consumer should reference the source node by name (`$('Source Node').item.json.x`), not `$json`. Otherwise the field silently resolves to null.
- **Item-context risk:** any Aggregate / Execute Once / Split Out followed by downstream `.item` references? n8n may not be able to pair items deterministically. Look for "The expression is referencing... multiple matching items" in past executions.

### Step 4: re-fetch the node types

```
get_node_types([{ name: '<failed-node>', resource: '...', operation: '...' }])
```

Compare actual parameter shape vs. configured. Common mismatches:

- Missing required parameter.
- Wrong type (string vs. number, etc.).
- **`object` and `array` are distinct in n8n's UI type dropdowns** (Set, IF, Switch, Filter, anywhere the UI asks you to pick a type). Picking `object` won't accept an array value, and vice versa. Inside expressions themselves it's normal JS (arrays *are* objects), so the distinction only bites at those UI type-pick surfaces. Watch for this when a `={{ ... }}` expression returns the wrong container shape for a typed slot.
- A dependent parameter set without its parent (e.g., `credentials` without `authentication !== 'none'`, or `query` without `operation === 'executeQuery'`). Re-fetch with `get_node_types` passing the right discriminators.

If the manual shape-vs-config diff is tedious (deep params, AI tool subnodes, many conditional branches), run `validate_node_config` directly. Returns `{ path, message }` per failure. For tool subnodes set `isToolNode: true`.

### Step 5: test with pinned data

```
prepare_test_pin_data({ workflowId: '<id>' })
test_workflow({ workflowId: '<id>' })
```

Controlled input isolates "workflow broken?" from "input weird?". If pinned data works but real input fails, the issue is in real input handling.

If pinned data also produces wrong output, that's likely a logical error: trace each node's output against what you expected. `get_execution` on the test run gives you the actual emitted data per step, which is the source of truth for what each node did.

### Step 6: read the n8n source

When everything checks out and behavior still seems wrong:

```
github.com/n8n-io/n8n
```

- `packages/nodes-base/nodes/<NodeName>` for built-in nodes.
- `packages/cli/src/...` for execution logic.
- `packages/core/src/...` for workflow runtime.

The behavior of the code is truth.

See `references/FETCHING_N8N_SOURCE.md`.

### Step 7: suspect drift on either side

If steps 1-6 all check out and behavior still doesn't match expectations, version drift is the most likely remaining cause. Two sides drift independently:

<!-- TEMPORARY: when instance metadata tool is added, change asking user to just using the tool -->
- **Their n8n instance version.** Ask. (UI: `Settings → About`, or `GET /rest/settings`.) On older instances, parameters and tools the skill assumes may be missing; on very new ones, parameter shapes or tool names may have moved. Suggest updating to the latest n8n release, or if a fix is rumored or the issue is recent, the latest beta.
- **This skill plugin's version.** These skills drift relative to n8n over time. If the user installed the plugin a while ago, suggest `git pull` (or the plugin manager's update command) on the skills repo. See the README's "Drift" section.

Drift surfaces as: parameter shape mismatches in `get_node_types`, MCP tools that don't exist or carry new parameters, tool descriptions that contradict what the skill teaches, behavior diverging from the skill's claims. When you spot any of those, surface drift explicitly to the user: *"This may be drift between your n8n version and these skills. Can you tell me your n8n version, and when you last updated the skills?"*

If after updating both sides the issue persists, proceed to Step 8.

### Step 8: report or workaround

For confirmed bugs:

- Have the user post a question on https://community.n8n.io
- Surface a clear repro to the user.
- Check n8n GitHub issues. May already be filed.
- If blocking, work around (different node/approach) and note in workflow notes.
- If a fix is in progress, mark workarounds with `<!-- TEMPORARY: ... -->`

## Reference files

| File | Read when |
|---|---|
| `references/PARAMETER_VERIFICATION.md` | Parameters might be misconfigured, need a systematic re-check |
| `references/FETCHING_N8N_SOURCE.md` | n8n behavior contradicts docs, need to read the actual code |

## Anti-patterns

| Anti-pattern | What goes wrong | Fix |
|---|---|---|
| "It should work, are you sure you're doing X?" | Dismisses the user's report, misses real issues | Believe the user. Investigate. |
| Re-running without checking the execution | Same failure twice, no new info | `get_execution` on the failed run, read the error |
| Assuming docs are accurate when behavior contradicts | Accepting the wrong mental model | Read the source. Behavior is truth |
| Re-implementing logic in a Code node when a configured node fails | Hides the bug, doesn't fix root cause | Diagnose first, only work around when the bug is confirmed |
| Bisecting by deleting nodes randomly | Wastes time | Step through `get_execution` to find the failed node directly |
| Asking the user to re-screenshot instead of inspecting via MCP | Slow, error-prone | Use `get_workflow_details` and `get_execution` |
| Calling it "fixed" when you've worked around the bug, not understood it | Bug recurs in slightly different form | Document the cause. If working around, mark with `<!-- TEMPORARY: -->` |
| Declaring a "bug" without asking the user's n8n version or when they last updated the skills | Real cause is often drift, and user updates and the "bug" disappears | Ask both versions before reporting. See Step 7. |

