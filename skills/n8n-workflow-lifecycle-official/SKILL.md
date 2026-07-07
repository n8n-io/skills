---
name: n8n-workflow-lifecycle-official
description: Use when starting, designing, organizing, finishing, or shipping an n8n workflow. Covers visual layout (sticky notes), descriptions that capture the *why*, node names, validation, testing, folders/projects, and publishing. Triggers on create_workflow_from_code, update_workflow, validate_workflow, publish_workflow, archive_workflow, "design", "lay out", "organize", "structure", "sticky", "describe this workflow", "ship", "deploy", "publish", "name this workflow", or any folder/project organization request.
---

# n8n Workflow Lifecycle

## The six stages

1. **PLAN.** Gather requirements, ask clarifying questions, search for existing workflows / sub-workflows that already do this.
2. **BUILD.** Write SDK code (with skills: subworkflows, node-config, expressions, code-nodes; readability section below). Use `validate_node_config` as a side-channel for iteration, debugging, or small single-node edits: clean per-parameter errors without full-graph noise. Not a replacement for `validate_workflow` in VALIDATE.
3. **VALIDATE.** `validate_workflow` + `get_workflow_details` for connections, then have the user verify per-node credentials and create anything you couldn't (missing credentials, folders, etc).
4. **TEST.** `test_workflow` with `prepare_test_pin_data`; iterate until output matches intent.
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

- **Test before publish** with `test_workflow` + `prepare_test_pin_data`. See `references/TESTING.md` for mocking by trigger type, pinning individual nodes, and the side-effect surface. Looser for internal one-off scripts you watch run.
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
- **Tags:** the AI-side discovery mechanism (n8n 2.27.0+). The MCP lists (`list_tags`), filters (`search_workflows({ tags })`), and attaches them (`update_workflow` `addTags`/`removeTags`, auto-creating unknown names). Lowercase, 2-4 per workflow. See `references/NAMING_CONVENTIONS.md`.

## Readability: descriptions, node groups, sticky notes, conventions

For any workflow over ~5 nodes, four levers carry the readability load:

- **Workflow `description`: capture the *why*, including AI-derived context.** Two sentences: what it does and why it exists. Most importantly, capture context you had during conversation that won't otherwise survive into the file (the constraint that drove the design, why this approach over the alternative, the user's reason for asking). Otherwise it dies with the chat.
- **Node groups: group every logical step past ~10 nodes.** Partition the canvas into named groups, one per logical step (`Validate input`, `Enrich order`, `Notify`), via `update_workflow` `setNodeGroups` (n8n 2.28.0+). Each group must be a connected, trigger-free run with a single entry and exit (n8n rejects anything else); collapsed, the workflow reads as its steps, not its nodes. Where a section is too branchy to form one group, a sticky note marks it instead. Organization only, members run inline (reuse/isolation is a sub-workflow's job).
- **Sticky notes: group nodes by purpose.** Use the `n8n-nodes-base.stickyNote` node with markdown `content` (`### Title` on the first line, 1-3 sentences of body) and an integer `color` 1-7. Title each with the purpose ("Validate input" not "If, Set, If"). Pick a small palette and stick to it (e.g. gray/yellow for processing, red for errors, pink for TODOs); random colors communicate nothing.
- **Node `notes` for non-obvious config.** Explain *why* a workaround exists or a Code node does what it does. Don't annotate obvious nodes.

Plus two notes:

- **Match existing project conventions before introducing your own.** Skim a couple of nearby workflows via `search_workflows` + `get_workflow_details` and mirror the sticky palette, naming, and description style.
- **Layout is auto-applied on create / update.** SDK `position` values for non-sticky nodes are ignored. Stickies, node groups, and naming are your readability levers.

## Folder limitations

The MCP can place a workflow into a folder that **already exists**. It cannot:

- Create new folders
- Move existing folders
- Move existing workflows between folders

If the user asks for a folder that doesn't exist, **say so before building**. Don't silently create at the project root and report success. Surface options:

1. User creates the folder manually, then you place workflows into it.
2. Use a different existing folder.
3. Confirm root-level placement is acceptable.

For the full protocol including detecting existing folders via `search_folders`, read `references/FOLDER_LIMITATIONS.md`.

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
- **Create missing folders.** The MCP can't create folders. If the user wanted a folder that doesn't exist, they create it before you can place the workflow there. See `references/FOLDER_LIMITATIONS.md`.
- **MCP access toggle for user created workflows.** Workflows you create via the MCP are MCP-accessible by default. The toggle only matters when the test depends on a UI-created workflow being callable from the MCP. See `references/MCP_ACCESS_PER_WORKFLOW.md`.

Don't proceed to TEST until these are confirmed done.

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
| `references/FOLDER_LIMITATIONS.md` | User mentions a folder, project structure, or wants workflows organized |
| `references/MCP_ACCESS_PER_WORKFLOW.md` | Building a workflow that you or another agent will call via MCP |
| `references/VALIDATION_CHECKLIST.md` | Just finished a workflow and about to call `publish_workflow` |
| `references/REVIEW_CHECKLIST.md` | Reviewing or auditing an existing workflow (any age, any author). Severity-tiered findings, distinct from the pre-publish validation checklist |
| `references/TESTING.md` | About to run `test_workflow` or `execute_workflow`, mocking trigger input, side-effect protocol |

## Anti-patterns

| Anti-pattern | What goes wrong | Fix |
|---|---|---|
| Calling `publish_workflow` without validating | Broken workflows reach production | Validate, verify connections, then test |
| Creating workflows at root because the requested folder doesn't exist | Workflows get lost, and the user has to drag them manually | Surface the limitation *before* building |
| Generic node names (`HTTP Request1`, `Set2`) | Workflows are unreadable a month later | Rename to describe the action |
| Missing `description` on `create_workflow_from_code` | Workflow invisible in search, no context for maintainers | Always include 1-2 sentences |
| Asking the user to flip the MCP access toggle on a workflow you created via the MCP | Wastes their time, agent-created workflows default to MCP-accessible | Only mention the toggle for UI-created workflows, or when the user wants to *revoke* MCP access on an agent-created one |
| Running `test_workflow` on a workflow with side-effecty non-pinned downstreams without asking | Real Data Table write, real sub-workflow side effects, real Execute Command output, etc. Triggers + credentialed nodes + HTTP get pinned, nothing else does | Ask first. See `references/TESTING.md`. |
| No sticky notes on a 15-node workflow | Reader has to read every node to find what they want | Add stickies per logical section. See "Readability" above |
| Sticky titled "Set, If, Set" or sticky-of-every-color | Re-states what's visible / color becomes pure noise | Title with the *purpose*; one color per category |
| `description: "Sends Slack."` | Adds nothing visible from the trigger and Slack node | Include *why* + AI-derived context: "Sends weekly summary to founders. Replaces manual report that kept getting skipped." |
| Designing fan-out branches as if they execute concurrently | n8n runs fan-out branches sequentially, top-to-bottom by Y-position. Total runtime is the sum of branches, not the max | For real concurrency, dispatch via `Execute Workflow` with `mode: 'each'` + `waitForSubWorkflow: false`. See `n8n-subworkflows-official` "Fire-and-forget parallelization" |

