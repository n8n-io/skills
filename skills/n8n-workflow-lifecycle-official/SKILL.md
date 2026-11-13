---
name: n8n-workflow-lifecycle-official
description: Use when starting, designing, organizing, finishing, or shipping an n8n workflow. Covers visual layout (sticky notes), descriptions that capture the *why*, node names, validation, testing, folders/projects, and publishing. Triggers on create_workflow_from_code, update_workflow, validate_workflow, publish_workflow, archive_workflow, "design", "lay out", "organize", "structure", "sticky", "describe this workflow", "ship", "deploy", "publish", "name this workflow", or any folder/project organization request.
---

# n8n Workflow Lifecycle

## The six stages

1. **PLAN.** Gather requirements, ask clarifying questions, search for existing workflows / sub-workflows that already do this.
2. **BUILD.** Write SDK code (with skills: subworkflows, node-config, expressions, code-nodes; readability section below). Use `validate_node_config` as a side-channel for iteration, debugging, or small single-node edits: clean per-parameter errors without full-graph noise. Not a replacement for `validate_workflow` in VALIDATE.
3. **VALIDATE.** `validate_workflow` + `get_workflow_details` for connections, then have the user verify per-node credentials and create anything you couldn't (missing credentials, folders, etc).
4. **TEST.** `test_workflow` with `prepare_workflow_pin_data`; iterate until output matches intent.
5. **PUBLISH.** `publish_workflow` only after stages 3 and 4 are clean.
6. **HANDOFF.** Production handoff: how to trigger it, what it returns, what to watch, what they should know to use it well.

Skipping a stage produces workflows that look done but break in production, or solve the wrong problem entirely. Three most common skips:

- **Build before plan.** "User asked for X, I'll start coding" without confirming what X means, whether the same logic already exists as a sub-workflow, or which folder/project it belongs in. Cheaper to ask one clarifying question than to rebuild after.
- **Test before user-side wire-up.** Running `test_workflow` before the user has verified credentials per node hits the wrong service or 401s. Get the user-side setup done as part of VALIDATE.
- **Publish without test.** Validation passing means the SDK is well-formed; it does NOT mean the workflow is correct.

## Non-negotiables

1. **Validate AND verify before publish.** Run `validate_workflow` on the SDK code, then `get_workflow_details` after every create/update to check the `connections` object. Validation alone misses silently dropped wires. `validate_node_config` is a separate per-node iteration tool, not a replacement for this step.
2. **Surface known limitations to the user.** If folders, MCP access, or any other limitation blocks the request, say so explicitly and propose a path. Don't silently dump workflows at the wrong location or report success on a request you couldn't fully fulfill.
3. **Ask before testing when not-auto-pinned downstreams have side effects.** `test_workflow` auto-pins triggers, credentialed nodes, and HTTP Request nodes. Everything else (Code, Edit Fields, If, Wait, Execute Command, file ops, sub-workflow calls, Data Tables) runs for real. Ask the user before running if any of those would fire user-visible side effects. See `references/TESTING.md`.

## Strong defaults

- **Test before publish** with `test_workflow` + `prepare_workflow_pin_data`. See `references/TESTING.md` for mocking by trigger type, pinning individual nodes, and the side-effect surface. Looser for internal one-off scripts you watch run.
- **Always include a `description`** on `create_workflow_from_code`. 1-2 sentences capturing *what* and *why*. See "Readability" below.

## Validation isn't enough

`validate_workflow` runs schema and shape checks: missing parameters, type errors, references to non-existent nodes. It does **not** catch:

- The `.to()`-inside-`.add()` connection trap (silent dropped wires)
- Fan-outs collapsed to a single connection
- Merge index off-by-one
- Error outputs wired without `onError: 'continueErrorOutput'`
- Parameters that are syntactically valid but semantically wrong (e.g., wrong sheet ID, wrong column name)

Validation is necessary but not sufficient. The real gate is:

1. `validate_workflow` passes.
2. `get_workflow_details` returns a `connections` object that matches your intent.
3. `test_workflow` produces the right output on representative pinned data.

Only then call `publish_workflow`.

For the full pre-publish checklist, see `references/VALIDATION_CHECKLIST.md`.

## Execution model

n8n workflows execute **sequentially, left-to-right, top-to-bottom**. Branches that visually appear parallel on the canvas (fan-out from one source to multiple downstreams) run one after the other, ordered by the target nodes' Y-position on the canvas. There is no automatic concurrency.

Practical consequences:

- A fan-out to three slow HTTP calls runs in series; total latency is the sum, not the max.
- "Parallel" branches share workflow state in execution order; downstream consumers see whatever the last branch left.
- For real concurrency, dispatch sub-workflows with `mode: 'each'` and `waitForSubWorkflow: false`. See `n8n-loops-official` and `n8n-subworkflows-official`.

This is platform behavior, not an SDK quirk. Don't design fan-outs around assumed parallelism.

## Naming conventions

Bad names compound: a workflow that's hard to find six months from now gets duplicated.

For full conventions (verb-noun patterns, capitalization, prefixes), read `references/NAMING_CONVENTIONS.md`. Short version:

- **Workflows:** verb-first, scoped. `Send weekly customer report` not `Customer report sender`.
- **Nodes:** describe what they *do* in this workflow, not the node type. `Fetch active customers` not `Postgres1`.
- **Sub-workflows:** plain descriptive name (`Parse RFC2822 date`); carry the category in tags (`subworkflow`, a domain tag, `tool`), not a name prefix. `search_workflows({ tags })` filters on them. See `n8n-subworkflows-official` `references/NAMING_AND_DISCOVERY.md`.
- **Tags:** the AI-side discovery mechanism (n8n 2.27.0+). The MCP lists (`list_workflow_tags`), filters (`search_workflows({ tags })`), and attaches them (`update_workflow` `addTags`/`removeTags`, auto-creating unknown names). Lowercase, 2-4 per workflow. See `references/NAMING_CONVENTIONS.md`.

## Readability: descriptions, node groups, sticky notes, conventions

Four levers carry the readability load, grouping from 7 boxes on and the other three from about 5 nodes on:

- **Workflow `description`: capture the *why*, including AI-derived context.** Two sentences: what it does and why it exists. Most importantly, capture context you had during conversation that won't otherwise survive into the file (the constraint that drove the design, why this approach over the alternative, the user's reason for asking). Otherwise it dies with the chat.
- **Node groups: the only way to group nodes.** Named frames, one per logical step (`Validate input`, `Enrich order`, `Notify`). Organization only, members run inline (reuse/isolation is a sub-workflow's job). **Read `references/NODE_GROUPS.md` before creating or editing any group**, and after any save that reported a group problem. The three things to know up front:
    - **When:** more than **7 boxes** with every group collapsed, typically into 3-5 groups. A box is the trigger, each group, and each ungrouped node; sub-nodes and sticky notes don't count.
    - **A group must be a connected, trigger-free section with at most one member facing out in each direction**, with an Agent's sub-nodes all in or all out. Members are node **names**, not ids.
    - **An invalid group op is skipped, not fatal**, and unrelated edits can silently delete a valid existing group, so a save that looks clean can have lost one. The exception is a description over 145 characters: that rejects the whole `update_workflow` call. Read the group fields on every create and update, and repair before reporting done.

- **Sticky notes: annotate, don't group.** Grouping is the node group's job (above). Stickies carry what a group name can't: a callout, a TODO, a warning. **Read `references/STICKY_NOTES.md` before placing one.**
    - **On create, always anchor.** `sticky(content, [nodes], { color })` derives the box from the nodes it wraps, after layout. Coordinates guess at a canvas that doesn't exist yet; omitting both is worse, since the fallback centers the note under the whole graph and only dodges other stickies, never nodes. If you can't name the nodes a note is about, it doesn't belong on the canvas.
    - **Three roles, and the anchor set follows from the role.** A **stage zone** anchors one stage's nodes; a **callout** anchors the single node it warns about; a gray **title band** anchors the whole flow and is rare, only for a canvas you're deliberately leaving ungrouped.
    - **Scale:** under ~5 nodes, none. From 5 to 7 boxes, one zone per stage. Over 7, node groups section *and* document the canvas via their descriptions, and you anchor nothing to a grouped node: those positions are collapsed-chip slots, so the note draws over the expanded group and matches nothing collapsed.
    - **Zones need room the derived box doesn't give.** Declare `height: 272` for a one-row zone, `464` for a branch fan (add 32 for Message an Agent v2+). Never declare a width. Then, **once the canvas is final**, widen every zone in one batched `update_workflow`: `x = min(node.x) - 56`, `width = span + 112`. Computed from the nodes, so re-running is harmless, but it's a finishing step, not per-edit.
    - **`update_workflow` has no sticky op.** A sticky there is an `addNode` of `n8n-nodes-base.stickyNote` with `content`, `width`, `height`, `color` in `parameters`; an omitted `position` means `[0, 0]`.
    - **Content and color:** `### Title` carrying the point, plus one short line. Only the top 64px clears the nodes, so never add height for more text; longer prose goes in node `notes` or the workflow `description`. `color` 1-7 stands for what happens there: green creates or involves a person, red is destructive or irreversible, blue is routing and transformation, gray is documentation. A user preference, then nearby workflows, outrank that.
- **Node `notes` for non-obvious config.** Explain *why* a workaround exists or a Code node does what it does. Don't annotate obvious nodes.

Plus two notes:

- **Match existing project conventions before introducing your own.** Skim a couple of nearby workflows via `search_workflows` + `get_workflow_details` and mirror the sticky palette, naming, and description style.
- **Layout runs on create, never on update.** `create_workflow_from_code` lays out every node that doesn't carry an explicit `position`, so omit them and let it. Setting some and not others is the bad case: yours are honored and the rest are laid out around them, which is how nodes end up stacked. `update_workflow` runs no layout at all, so anything you add sits exactly where you put it.

## Folder management

On a registered instance the MCP creates and organizes folders: `create_folder`, `update_folder` (rename/move), `move_workflows_to_folder`, and a `folderId` on `create_workflow_from_code` for create-time placement. `search_folders` resolves names to IDs.

If the user wants a folder that doesn't exist, create it, don't build at the root and report success. If the folder tools are absent, the instance isn't registered: folders are blocked in the UI too, so ask the user to register (free, in Settings) rather than create the folder by hand. No tool deletes a folder, and projects are read-only.

For the full protocol, read `references/FOLDER_LIMITATIONS.md`.

## Per-workflow MCP access

Each workflow has an `availableInMCP` flag. The default depends on who created it:

- **Workflows created via the MCP** (`create_workflow_from_code`) default to **MCP-accessible**. No toggle step needed: you can find them via `search_workflows` and operate on them right away.
- **Workflows created in the n8n UI** can default to off. Until the user flips the toggle, the workflow is invisible to you.

The #1 case where this bites: **the user built a workflow manually in the UI and now wants you to inspect or edit it, but you can't see it.** Before assuming it doesn't exist or you're searching the wrong project, ask the user to confirm MCP access is enabled.

Sub-workflows called via MCP: the caller can use them as code-level sub-workflows without the toggle. To invoke as MCP-exposed *tools*, the toggle is required (and is on by default for MCP-created sub-workflows).

For the full case-by-case guide and user-facing message, read `references/MCP_ACCESS_PER_WORKFLOW.md`.

## User-side wire-up (part of stage 3)

There are things the user has to do that you can't, and they need to be done before testing, otherwise the test fires against the wrong credential, hits a missing folder, or 401s. Surface these as a short list during VALIDATE, before TEST:

- **Verify credentials per node.** `newCredential('Label')` is cosmetic. n8n auto-assigns the most recently edited credential of the right type, which silently picks the wrong one when the user has multiples (prod vs staging Gmail, two API keys). Tell them: "open every node that uses a credential and confirm the right one is selected." See `n8n-credentials-and-security-official` non-negotiable #2.
- **Create missing credentials.** If the user pasted a secret in chat or the workflow needs an account that doesn't exist yet, name the credential *type* and have them create it in the UI.
- **Register for folders (only if the tools are missing).** Folder tools need a registered instance. If they're absent, the user registers (free, in Settings) before you can create or place folders; otherwise you handle folders yourself. See `references/FOLDER_LIMITATIONS.md`.
- **MCP access toggle for user created workflows.** Workflows you create via the MCP are MCP-accessible by default. The toggle only matters when the test depends on a UI-created workflow being callable from the MCP. See `references/MCP_ACCESS_PER_WORKFLOW.md`.

Don't proceed to TEST until these are confirmed done.

## Measuring time saved (optional Workflow ROI)

When the user wants workflow ROI or time-saved reporting, use n8n's **Estimated time saved** setting in the **top-level (parent) workflow**, not a calculation hidden inside a child sub-workflow:

1. **Fixed:** In workflow Settings, choose **Estimated time saved → Fixed** and enter the minutes of manual effort saved per production execution. Use this for a predictable, similar amount of work each run.
2. **Dynamic:** In workflow Settings, choose **Estimated time saved → Dynamic**. Add **Time Saved** nodes to the parent workflow at the points where different execution paths actually save work. Set minutes per execution (once for all items) or **per item** when each incoming item represents a unit of work; per-item mode multiplies minutes by the number of input items.
3. **Count only real work:** Multiple Time Saved nodes contribute to the same parent execution only when their paths execute. If a called sub-workflow processes records, put the corresponding Time Saved node **after its Execute Sub-workflow call in the parent**. Use meaningful parent-level branches or item counts so the saved-time estimate reflects the actual outcome, rather than claiming the same fixed savings on every path.
4. **Hard limitation:** Time Saved nodes inside **sub-workflows do not contribute** to Insights time saved, and neither manual test runs nor error-workflow executions count. Place the tracking nodes in the **top-level orchestrator**; do not promise that a child can report ROI upward automatically.
5. **Avoid duplicate runs:** Time Saved is a normal node, not a passive observer. Do not tee it into and rejoin a downstream action in a way that makes that action execute twice; place it inline at the appropriate completed branch.

See [n8n Insights: setting time saved](https://docs.n8n.io/administer/observe-and-log/track-usage-with-insights/) for availability and current behavior.

## Handoff: production handoff (stage 6)

After `publish_workflow` and a clean test, the workflow is technically live, but the user still needs enough context to actually *use* it in production. Treat this like the freelancer-to-customer handoff: short, structured, and oriented toward how they'll operate it from here.

What to include:

- **How it triggers.** Webhook URL (live now that it's published), schedule cadence + timezone, manual trigger button, sub-workflow caller, whichever applies. For webhooks, hand them the URL.
- **What it returns / where the data goes.** One sentence. "Writes new rows to the `customers` table," "responds JSON to the caller," "fires the on-call Slack channel."
- **How to invoke it for real, with an example.** "Hit the webhook with `curl -X POST <url> -d '{...}'`," "trigger manually from the UI," "wait until 09:00 UTC for the first scheduled run."
- **What to watch.** Failure modes that surface as alerts/errors, rate-limit ceilings on upstream services, and where to look first when something breaks (executions tab, error workflow, audit log, etc.).
- **MCP access status.** If you created the workflow via the MCP, it's already MCP-accessible. Let the user know they can revoke access in Settings if they want to lock it down. If they hand-built it in the UI, they need to flip MCP access on for any other agent to call it.
- **Anything still pending on their side.** Secret rotation if a token was pasted in chat, follow-up wiring you couldn't reach, known TODOs left in stickies.

Keep it tight: half a dozen bullets, not a wall of text. The user shouldn't have to ask "ok, what now?"

## Reference files

| File | Read when |
|---|---|
| `references/NAMING_CONVENTIONS.md` | Naming a new workflow, sub-workflow, or node |
| `references/NODE_GROUPS.md` | **Before creating or editing any node group**, or after a save reported a skipped or removed group |
| `references/STICKY_NOTES.md` | About to add, move, or resize a sticky note on either tool |
| `references/FOLDER_LIMITATIONS.md` | User mentions a folder, project structure, or wants workflows organized |
| `references/MCP_ACCESS_PER_WORKFLOW.md` | Building a workflow that you or another agent will call via MCP |
| `references/VALIDATION_CHECKLIST.md` | Just finished a workflow and about to call `publish_workflow` |
| `references/REVIEW_CHECKLIST.md` | Reviewing or auditing an existing workflow (any age, any author). Severity-tiered findings, distinct from the pre-publish validation checklist |
| `references/TESTING.md` | About to run `test_workflow` or `execute_workflow`, mocking trigger input, side-effect protocol |

## Anti-patterns

| Anti-pattern | What goes wrong | Fix |
|---|---|---|
| Time Saved node only inside a sub-workflow | Insights ignores child workflow time savings; parent ROI stays understated | Set Dynamic in the top-level parent and place Time Saved nodes in that parent after the relevant call or branch |
| Time Saved on a parallel tee that later rejoins an action | That downstream action may execute again due to multiple incoming branches | Put Time Saved inline on the intended path, not as an unmerged side branch |
| Calling `publish_workflow` without validating | Broken workflows reach production | Validate, verify connections, then test |
| Creating workflows at root because the requested folder doesn't exist | Workflows get lost, and the user has to drag them manually | Surface the limitation *before* building |
| Generic node names (`HTTP Request1`, `Set2`) | Workflows are unreadable a month later | Rename to describe the action |
| Missing `description` on `create_workflow_from_code` | Workflow invisible in search, no context for maintainers | Always include 1-2 sentences |
| Asking the user to flip the MCP access toggle on a workflow you created via the MCP | Wastes their time, agent-created workflows default to MCP-accessible | Only mention the toggle for UI-created workflows, or when the user wants to *revoke* MCP access on an agent-created one |
| Running `test_workflow` on a workflow with side-effecty non-pinned downstreams without asking | Real Data Table write, real sub-workflow side effects, real Execute Command output, etc. Triggers + credentialed nodes + HTTP get pinned, nothing else does | Ask first. See `references/TESTING.md`. |
| No node groups on a canvas over 7 top-level boxes | Reader has to read every node to find what they want | Group each logical step. See `references/NODE_GROUPS.md` |
| Reporting a create or update as done without reading its group fields (`skippedGroups` on create; `skippedOperations` / `removedGroups` on update) | A group op was silently skipped, or an existing group was deleted by an unrelated edit, and the save still looked successful | Check them on every call and repair. See `references/NODE_GROUPS.md` |
| Sticky note used to fake a group, or sticky-of-every-color | Grouping is the node group's job / color becomes pure noise | Group with a node group; reserve stickies for callouts, one color per category |
| Hand-positioned stickies on `create_workflow_from_code` | Coordinates are chosen before layout runs, so the note lands away from the nodes it describes | Pass the nodes to `sticky(content, [nodes])` and let the box be derived. See `references/STICKY_NOTES.md` |
| `description: "Sends Slack."` | Adds nothing visible from the trigger and Slack node | Include *why* + AI-derived context: "Sends weekly summary to founders. Replaces manual report that kept getting skipped." |
| Designing fan-out branches as if they execute concurrently | n8n runs fan-out branches sequentially, top-to-bottom by Y-position. Total runtime is the sum of branches, not the max | For real concurrency, dispatch via `Execute Workflow` with `mode: 'each'` + `waitForSubWorkflow: false`. See `n8n-subworkflows-official` "Fire-and-forget parallelization" |
