# Pre-publish validation checklist

Run before every `publish_workflow`. The whole list. Skipping items is how broken workflows ship.

## The checklist

### 1. `validate_workflow` passed

Run `validate_workflow`. Schema and shape errors must be zero. If validation fails, fix and re-validate.

If a failure points at a single node's params, `validate_node_config` on that node alone returns per-parameter errors without full-graph noise. For tool subnodes, set `isToolNode: true`. Best used as a per-node spot-check during BUILD.

### 2. Antipattern scan (the build-time discipline check)

Walk the workflow with these questions in mind. These are patterns that recur across builds even when relevant skills are loaded, so making this explicit catches them.

**Set nodes:**
- For each Set node, count how many downstream nodes reference its output fields.
- If only 0 or 1 downstream consumer references each field, **delete the Set node and inline the expression at the consumer**. The most common antipattern (`n8n-expressions-official` non-negotiable #2).
- Common offender: a Set node right before a Data Table Insert / Update node, mapping fields to match schema. Map directly in the Insert/Update node's expression slots.
- Common offender: a Set node building a body before an Email/Slack node. Build the body in the body field with an expression.

**Code nodes:**
- For each Code node, ask: could this be an expression or arrow-function-in-Edit-Fields?
- If it's pure data shaping (`.map`, `.filter`, `.find`, field renaming, optional chaining), rewrite as expression or Edit Fields with arrow function. Code's bar is multi-source aggregation, external libraries, or stateful transforms (`n8n-code-nodes-official`).
- **For each operation the Code does, check separately for a native node.** A Code node doing 4 things probably has 4 native answers. Read its body and ask:
  - `this.helpers.httpRequest(...)` → use the **HTTP Request node**.
  - Manual pagination loop (`while (more) { start += page; ... }`) → use HTTP Request's **Pagination** option.
  - Regex parsing structured response (`/<id>...<\/id>/g`, etc.) → use the **XML node** for XML, `JSON.parse` for JSON.
  - `crypto.createHash(...)` or `crypto.createHmac(...)` → use the **Crypto node**.
  - Status-code retry logic (`if (status === 429) throw`) → HTTP Request's `retryOnFail` (retries on any error, no per-status filter, capped at 5 tries / 5000ms wait). For 429-only or 5xx-only retry, use the error output + IF on `$json.error.httpCode` instead.
- **Identity Code nodes** (`return $('Some Node').all();` or `return $input.all();`) are always wrong. They re-emit upstream data, which means the workflow shape is wrong: the downstream consumer should branch off the upstream directly, or the per-item-vs-aggregate context mismatch should be solved with fan-out, not a Code-node bridge.
- Common offender: flattening a single API response's nested structure. That's Edit Fields with arrow function, not Code.

**Merge nodes:**
- Count wires going in. Confirm `numberOfInputs` matches.
- For Merges using `useDataOfInput`, walk through the off-by-one rule (`n8n-node-configuration-official` `references/MERGE_NODE.md`).

**Fan-out branches:**
- If the design assumes branches run in parallel, it's wrong. n8n runs them sequentially top-to-bottom by Y-position. For real concurrency, dispatch via `Execute Workflow` with `mode: 'each'` + `waitForSubWorkflow: false`.

**DateTime nodes:**
- Replace with a Luxon expression (see `n8n-expressions-official`). DateTime nodes are almost always wrong.

**Sub-workflow triggers:**
- For each `Execute Workflow Trigger`, confirm **"Define Below"** mode with typed fields. Passthrough is only correct for (a) binary-receiving sub-workflows that won't be agent tools or (b) sub-workflows that genuinely take no inputs (Define Below requires at least one field). For (b), verify the body opens with a `Set` ("Keep Only Set", no fields) and a sticky noting no inputs are expected. See `n8n-subworkflows-official` non-negotiable #2.

**Data references:**
- Search for `$json.` in expressions. Replace with `$('Node Name').item.json.` unless the node is directly downstream of a single source with no intermediates (`n8n-expressions-official` non-negotiable #1).
- Search for `$env.` in expressions. Doesn't work, throws at runtime. Replace with `$vars.X` (paid plans), a Data Table, or a credential if it's a secret.

Skipping it is how build-time slips slip past validation.

### 3. Error handling is wired

For workflows that are webhook-triggered, production-bound, or otherwise user-facing, every fallible node should have its error path handled. This isn't about catching bugs. It's about returning a clean response when an upstream is down.

Invoke `n8n-error-handling-official` if any of these are true:

- Webhook trigger with a respond-to-webhook pair.
- Unattended (scheduled, cron, queue-driven).
- A failure would silently drop user-visible work.

For internal one-off scripts (manual trigger), error handling can be looser.

### 4. Credentials, not tokens in text fields

Walk every node config for tokens, API keys, or auth values pasted into text parameters. They should be referenced via the credential system.

If you find any, invoke `n8n-credentials-and-security-official` and migrate before publishing.

### 5. `test_workflow` produced expected output

Use `prepare_test_pin_data`, then `test_workflow`. Inspect outputs via `get_execution`.

**Before running:** `test_workflow` auto-pins triggers, credentialed nodes, and HTTP Request. Code, Edit Fields, If, Data Tables, Execute Command, file ops, and sub-workflow calls run for real. If any of those have user-visible side effects, ask the user before running. See `TESTING.md` for the side-effect protocol, mocking by trigger type, pinning individual nodes, and the post-run announce-what-was-pinned protocol.

Check:

- Output shape matches what consumers expect.
- No unexpected errors swallowed by error branches.
- Fan-outs all produced data, none collapsed to empty.
- For webhook responses, the shape is correct (status, body, headers).

Fix and re-test if anything's off.

### 6. Naming, descriptions, structure

Quick pass:

- Workflow name follows the verb-first pattern (`NAMING_CONVENTIONS.md`). Sub-workflows are tagged (`subworkflow`, a domain tag, `tool`) since that's how `search_workflows({ tags })` finds them.
- `description` is set and captures both *what* and *why*, with searchable keywords.
- Nodes are renamed from defaults.
- Workflows past ~10 nodes group their logical steps into node groups (`setNodeGroups`). Ungrouped still runs, but a large ungrouped canvas is hard to read and maintain, so take it seriously. See `SKILL.md` "Readability".

These don't block publish technically, but workflows without them rot faster.

### 7. Folder placement

If the user requested a specific folder, confirm via `search_folders` that the workflow ended up there. If the folder didn't exist, you should have surfaced that before building (`FOLDER_LIMITATIONS.md`). Don't silently dump at root.

### 8. MCP access (if applicable)

Workflows created via `create_workflow_from_code` default to MCP-accessible. No toggle step needed. Only ask the user to flip the toggle when:

- They built the workflow in the n8n UI and you need to operate on it.
- They want to *revoke* MCP access on an agent-created workflow (the toggle is on by default).

See `MCP_ACCESS_PER_WORKFLOW.md`.

## Order matters

Top-to-bottom. Items 1-4 are gates: failing any means the workflow shouldn't publish. Items 5-8 are quality checks: failing means the workflow ships and rots, but won't break immediately.

The most common skip is item 2 (the antipattern scan). It feels like polish, but it catches things `validate_workflow` doesn't.

## What to do if something fails after publish

> **Post-publish is high-stakes: run every operation through the user.** Once a workflow is published, it may be receiving real traffic, holding state, or being depended on by other systems. **Do not** take autonomous action: no `publish_workflow`, no `unpublish_workflow`, no `update_workflow`, no `archive_workflow`, no triggering executions to "see what happens." Surface the problem, propose the fix, and wait for explicit approval before each step. The guidance below is what to *recommend* to the user, not what to do without asking.

n8n keeps versions: `get_workflow_details` returns both `versionId` (the current draft) and `activeVersionId` (the version that's live). They diverge when you save changes via `update_workflow`. Those changes only go live on the next `publish_workflow` call. **Saving is not publishing.**

1. **Consider rolling back first.** `get_workflow_history` lists saved versions (newest first); `get_workflow_version` fetches a known-good one, and `restore_workflow_version` re-applies it as the draft (or pass its `versionId` to `publish_workflow` to go straight live). (n8n 2.29.0+.) Rollback no longer needs the user to copy a `versionId` from the UI, but per the guardrail above, recommend it and let the user approve before you restore.
2. **Recommend `unpublish_workflow` only if no rollback target exists** and the workflow is actively running and broken. A scheduled or webhook workflow with broken connections shouldn't keep firing. Surface the problem and the recommendation, let the user pull the trigger.
3. **Fix-forward path: `update_workflow` saves the draft, then `publish_workflow` makes it live.** Two separate steps: `update_workflow` does NOT auto-publish, the change sits as an unpublished draft until `publish_workflow` runs against it. Re-run this checklist before the publish step. Don't trust that "just one fix" doesn't ripple.

## A note on speed

The cost of skipping is higher than the cost of checking. Debugging a broken production workflow is much more time consuming, stressful, and can cause damage.