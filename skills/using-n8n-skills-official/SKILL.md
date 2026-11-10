---
name: using-n8n-skills-official
description: Use when working with n8n workflows in any capacity. The always-on protocol for the n8n-skills plugin, loaded by the SessionStart hook every session. Routes to the right skill, summarizes every n8n MCP tool (closing the deferred-description gap), and lists the cross-cutting rules.
---

# Using n8n Skills

The official n8n MCP evolves over time, so tool names, parameters, and default behaviors can drift between versions. When you spot drift (a tool a skill names doesn't exist, a parameter shape doesn't match what `get_node_types` returns, or behavior differs from what the skill describes), suggest updating the skill and n8n instance to the latest stable.

## Non-negotiables

Three rules with no exceptions. Violating any produces workflows that look right but break in production.

1. **Invoke the relevant skill before any n8n action.** Not just MCP tool calls. Before writing SDK code, configuring a node, designing a workflow, wiring a connection, building an agent, or handling errors: invoke the matching skill via the Skill tool. This document is a router. The skill body has the actual rules. The PreToolUse hooks remind you on the highest-impact MCP calls if a plugin is installed. The responsibility is yours on everything else. Err on the side of reading extra documents.
2. **Validate AND verify before publishing.** `validate_workflow` before `publish_workflow`, and `get_workflow_details` after every create or update to check the `connections` object. Validation alone misses many issues documented in the skills that will silently break workflows.
3. **Tokens/secrets never go in text fields.** Always use the n8n credential system. If no native node exists, configure HTTP Request with the official credential type. See `n8n-credentials-and-security-official`.

## Lean on skills, not training data

n8n evolves faster than any model's training cutoff. Parameter names drift, new MCP tools land, defaults change, patterns get deprecated. Anything you "remember" is likely wrong, often silently.

Trust the skills + live MCP tools (`get_node_types`, `get_workflow_sdk_reference`, `get_workflow_best_practices`) over recollection. If a skill contradicts what you "know", trust the skill. If `get_node_types` contradicts a skill, trust the tool. Without this discipline you will ship workflows that look right and silently fail: parameter names that don't exist, renamed nodes, deprecated patterns.

Unless a user preference overrides it, err on the side of loading too many skills rather than too few. Even a 3-node webhook flow typically needs `n8n-node-configuration-official`, `n8n-expressions-official`, `n8n-error-handling-official`, and `n8n-workflow-lifecycle-official`. Nothing in n8n is too small for skills.

## Strong defaults (each skill owns its exceptions)

- **The Code node is a last resort.** Expression first, then arrow function inside Edit Fields, then Code. Code earns its place for multi-source aggregation, libraries, and stateful work. See `n8n-code-nodes-official`.
- **Anything reusable becomes a stateless sub-workflow.** Search existing ones via `search_workflows({ tags: ['subworkflow'] })` before building. See `n8n-subworkflows-official`.
- **n8n preferences belong in n8n, not in harness memory.** When the user states a durable n8n preference, save it with `save_user_preference` rather than writing it to CLAUDE.md, AGENTS.md, or your own memory: the n8n store is read by the n8n assistant and every AI tool on the instance, so a preference parked in harness memory is invisible outside this session. Read what's already saved once before you start changing things (`get_user_preferences`) and apply it across the task. If the user would rather keep their n8n preferences in their own context file, that's their call: follow it. See "User preferences" below.
<!-- TEMPORARY: Gateway credits is n8n Cloud only for now and the coverage may expand; revisit this default and the cloud-only caveat when that changes. -->
- **Prefer Gateway credits when the user has no credential preference.** For nodes it covers (check `list_n8n_gateway_services`), n8n supplies the managed credential, so there's no setup step, much easier than the user provisioning their own. n8n Cloud only for now. See `n8n-credentials-and-security-official`.

## Red flags: thoughts that mean STOP and invoke

These rationalizations cause skills to be skipped. If you catch yourself thinking any of them, invoke the relevant skill via the Skill tool, **even if you "already read it" earlier in the session**.

| Thought | Action |
|---|---|
| "This workflow is simple, I'll just build it" | Invoke `n8n-workflow-lifecycle-official`. Most "simple" workflows are 10+ nodes by the time they ship. |
| "I'll add a Set node here to map these fields" | Invoke `n8n-expressions-official`. Set nodes feeding only 0 or 1 downstream consumer are the most common antipattern in this entire pack. |
| "I'll just use a Code node, it's easier" | Invoke `n8n-code-nodes-official`. The bar is high. Most reaches for Code can be expressions or Edit Fields with arrow functions. |
| "Validation passed, I'm ready to publish" | Invoke `n8n-workflow-lifecycle-official` and walk `VALIDATION_CHECKLIST.md` section 2 (the antipattern scan). Validation passing is necessary, not sufficient. |
| "The user wants an agent, I'll wire a Chat Trigger to an AI Agent node" | Invoke `n8n-agents-official`. "Agent" or "assistant" means a first-class n8n Agent unless one of its listed limits applies. |
| "The Agent validates, I'll publish it" | Don't. A built Agent is a draft; publish only on the user's explicit OK. Channels go live with it. |
| "I'll map the webhook field straight into the Agent's tool input" | Invoke `n8n-agents-official` `references/TOOLS.md`. Agent tool expressions only see the model's arguments; exact mapping stays in a workflow. |
| "The agent is wired up, the tool descriptions look fine" | Invoke `n8n-ai-nodes-official` `references/TOOLS.md` (AI Agent node) or `n8n-agents-official` `references/TOOLS.md` (first-class Agent). Tool names and descriptions ARE part of the prompt, and "looks fine" usually means generic. |
| "I'll set this sub-workflow trigger to passthrough" | Invoke `n8n-subworkflows-official`. Passthrough is only correct for binary-receiving sub-workflows that won't be agent tools, or for sub-workflows that genuinely take no inputs (Define Below requires at least one field). |
| "I'll use passthrough so binary works, then branch internally on which input shape arrived" | Invoke `n8n-subworkflows-official` `references/SUBWORKFLOW_PATTERNS.md` "Splitting by input shape". This is the signal to SPLIT into two outer sub-workflows (one Define Below, one passthrough) sharing a common downstream sub-workflow. Don't fight passthrough vs Define Below in one trigger. |
| "This section's big, I'll pull it into a sub-workflow" | If it's only to tidy the canvas (not reuse/isolation/testing), a node group is lighter, faster, and simpler: keep it inline and group it. Extract to a sub-workflow only for reuse, isolation, or an agent tool. See `n8n-workflow-lifecycle-official` `references/NODE_GROUPS.md`. |
| "I should ask the user what their credential is named" | Don't. The string in `newCredential('Label')` is cosmetic. See `n8n-credentials-and-security-official`. |
| "I'll note that preference in CLAUDE.md / AGENTS.md / my memory" | If it's about how they work in n8n, offer `save_user_preference` instead, where the n8n assistant and their other AI tools can see it too. Harness memory is for your own operating notes. |
| "The user mentioned data analysis, I'll write Python" | Invoke `n8n-code-nodes-official`. Default is JavaScript. Python only when explicitly asked. |
| "I'll add a Loop Over Items here to process each row" | Invoke `n8n-loops-official`. Default per-item iteration probably handles it without a Loop Over Items node. |
| "Date math, I'll use a DateTime node" | Invoke `n8n-expressions-official`. DateTime nodes are almost always wrong. |
| "I'll wrap this in a Merge with 3 sources" | Invoke `n8n-node-configuration-official` `references/MERGE_NODE.md`. Merge defaults to 2 inputs, and 3+ sources need `numberOfInputs` set explicitly. |
| "I'll fan out these three slow steps to run in parallel" | Invoke `n8n-workflow-lifecycle-official` and read the Execution model section. n8n executes fan-out branches sequentially (top-to-bottom by Y-position), not concurrently. For real concurrency, see `n8n-loops-official` and `n8n-subworkflows-official` (`mode: 'each'` + `waitForSubWorkflow: false`). |
| "User said which project, I'll just build it" | Invoke `n8n-workflow-lifecycle-official`. Project is not folder. Ask about folder placement BEFORE building. `create_folder` works on a registered instance. If the folder tools are absent, the instance isn't registered, and folders are blocked in the UI too, so the user must register it first (free Community-edition registration in Settings), not create the folder by hand. |
| "I'll just run `test_workflow` to see what happens" | Invoke `n8n-workflow-lifecycle-official` `references/TESTING.md`. `test_workflow` mocks the trigger only. Slack sends, DB writes, payments all fire for real. Ask the user first when downstreams have side effects. |

**The meta-skill (this document) tells you WHICH skill applies. The Skill tool loads the actual rules.** Reading the meta-skill once at session start is not a substitute for invoking the skill at the moment of decision.

## Skill index

Invoke via the Skill tool. Trigger column = when to invoke.

| Skill | Trigger |
|---|---|
| `n8n-workflow-lifecycle-official` | Starting, designing, organizing, or finishing a workflow. Covers sticky-note conventions, descriptions that capture the *why*, naming, validation checklist, folder management, MCP-access-per-workflow gotcha |
| `n8n-subworkflows-official` | Anything reusable, multi-step builds, or the user mentions reuse. Search before building, stateless patterns, tag-based discovery convention |
| `n8n-extending-mcp-official` | You need capabilities the MCP doesn't natively provide. Wrap n8n APIs as workflow tools, with user permission |
| `n8n-expressions-official` | Writing `{{}}`, `$json`, `$node`, expression errors. Luxon for dates, indented multi-line, prefer expressions over extra nodes |
| `n8n-node-configuration-official` | Configuring any node. Operation-aware, property dependencies, never assume parameters |
| `n8n-code-nodes-official` | User reaches for a Code node, or custom logic is needed. Decision tree, JavaScript patterns when truly required |
| `n8n-loops-official` | Multi-item data, batching, paginated APIs, "for each" or "loop over" mentions. Default per-item iteration, `executeOnce`, Loop Over Items, HTTP pagination |
| `n8n-agents-official` | The user wants an agent, assistant, or bot, or any Agent MCP tool. Agent vs workflow vs AI Agent node, Agent config, tools, approvals, skills, sub-agents, knowledge, memory and sessions, channels, tasks, Message an Agent, reading sessions |
| `n8n-ai-nodes-official` | AI inside a workflow: AI Agent node, Text Classifier, Information Extractor, chains, RAG, structured output, AI media. Chat bot workflows on Slack / Discord / Teams / Telegram |
| `n8n-error-handling-official` | Webhook-triggered or production-bound workflows. Error branch on every fallible node, 4xx for caller errors and 5xx for execution errors |
| `n8n-credentials-and-security-official` | Any auth, API key, or token mention. Credential system, custom credentials, HTTP Request with official creds |
| `n8n-binary-and-data-official` | Files, images, attachments. Binary handling patterns, agent-tool boundary, CDN requirement for chat surfaces |
| `n8n-data-tables-official` | Data Tables: schemas, default columns (id/createdAt/updatedAt), no-FK relational design, dedup, the no-JSON-only-primitives rule, the SDK-vs-UI manual-mapping quirk |
| `n8n-debugging-official` | Errors, unexpected behavior, "this isn't working". Believe the user, check parameters, fetch n8n source from GitHub |

## n8n MCP tools (compact reference)

The MCP defers tool descriptions to save tokens. Below is the short-form list so you have working knowledge of every tool from turn one.

Tool names are shown without the MCP prefix. The qualified name is `mcp__<server>__<tool>` where `<server>` depends on the user's MCP config.

### User preferences

Cross-client store of how the user works in n8n, read by the n8n assistant and every AI tool connected to the instance. Scopes: `instance` (admin-set, everyone), `user` (the caller, every project), `project` (one team project). `get_user_preferences` from n8n 2.41.0, the three write tools from 2.42.0.

<!-- TEMPORARY: preference tools are rolling out behind a PostHog flag. Drop the absent-tool fallback below once they ship to all instances. -->
If these tools aren't in your tool list, either the instance predates them or the rollout flag is off, or the MCP connection wasn't granted the `aiPreference:read` / `aiPreference:write` scopes. Either way, ask the user instead, and offer harness memory as the fallback for a preference worth keeping.

| Tool | What it does |
|---|---|
| `get_user_preferences` | Read instance, user, and project preferences (instance first). Read once before you start changing things and apply it across the task; re-read only if the user says they changed something. An `error` in the result means preferences are **unknown, not absent**, so don't build as if none were saved. `projectId` narrows to one project. |
| `save_user_preference` | Save one durable preference (max 2000 chars). Only for a way-of-working preference the user actually stated ("always add an error workflow", "name nodes in English"), never a one-off task instruction ("make this one a POST") and never one you inferred. Read preferences first: an exact duplicate is refused, and a near-duplicate should be an `update_user_preference` instead. Saves immediately with no confirmation step, so report the exact text saved plus the settings link from the result in the same turn. |
| `update_user_preference` | Change a saved preference's text, its `scope`, or both. Only move scope when the user asks; `project` needs a `projectId`. |
| `undo_user_preference` | Remove a preference saved through a connected AI tool for this user. One written in n8n settings, or scoped to a project or the instance, is refused: the user removes those in settings. |

When a saved preference conflicts with what the user asks for right now, follow the user and say which preference you set aside.

### Workflow management

| Tool | What it does |
|---|---|
| `search_workflows` | Search workflows across the instance by `query` (substring on name/description) and/or `tags` (exact tag names, AND semantics: must have all). The primary cross-workflow **discovery** tool. Use it to discover what already exists. |
| `get_workflow_details` | Fetch a workflow's full JSON by ID. Use after every create/update to verify connections. |
| `search_folders` | Resolve a folder name to its ID (full path). **Folder tools require a registered instance** (free Community registration); the skills assume one. |
| `create_folder` | Create a folder, optionally nested. |
| `update_folder` | Rename or move a folder within its project. |
| `move_workflows_to_folder` | Move workflows into a folder (or to project root). |
| `search_projects` | Resolve a project name to its ID. Read-only. |
| `list_workflow_tags` | List all workflow tags (with `usageCount` per tag). Check the instance's tag vocabulary before tagging or filtering, so you reuse exact names. Tags are attached/detached via `update_workflow` `addTags`/`removeTags`; there's no tag rename/delete tool. |
| `archive_workflow` / `publish_workflow` / `unpublish_workflow` | Soft-delete / activate / deactivate. Validate before publish. `publish_workflow` takes an optional `versionId` to re-publish a specific version. |
| `search_workflow_executions` | Search executions across the instance (filter by status, workflow, time range). Use for "list recent runs" / "failures in the last hour". Single executions: `get_workflow_execution`. |

### Workflow building

| Tool | What it does |
|---|---|
| `get_workflow_sdk_reference` | Fetch the n8n Workflow SDK reference. **Read this before writing workflow code.** Sections: `patterns`, `patterns_detailed`, `expressions`, `functions`, `rules`, `import`, `guidelines`, `design`, `groups` (n8n 2.33.0+), `all`. |
| `get_workflow_best_practices` | Fetch best-practices for a workflow technique. Call once per technique before searching nodes. `technique: "list"` discovers what's available. |
| `search_nodes` | Discover nodes by capability (e.g. "gmail", "slack", "schedule trigger"). Returns IDs plus discriminators (resource/operation/mode). |
| `get_node_types` | Fetch exact TypeScript parameter definitions for node IDs. **Required before configuring any node.** Don't guess parameter names. |
| `explore_node_resources` | Resolve the real values behind resource-locator (`@searchListMethod`) and load-options (`@loadOptionsMethod`) params: Slack channels, Sheets tabs/docs, DB tables/columns, model lists, labels. Needs a `credentialId` from `list_credentials` (pass `currentNodeParameters` for dependent lookups). Call after `get_node_types` to ground dropdown values instead of inventing IDs. |
| `create_workflow_from_code` | Save a workflow from SDK code. Always include a 1-2 sentence `description`. Pass `skillsUsed` (below). |
| `update_workflow` | Apply atomic ops (max 100): node/connection CRUD, `setNodeCredential`, `setNodeSettings` (per-node onError/retry/executeOnce), `setWorkflowSettings` (errorWorkflow, timezone, callerPolicy, timeouts, save-data policies; n8n 2.29.0+), `setNodeGroups`/`addNodeGroup`/`removeNodeGroup`/`updateNodeGroup` (canvas grouping), `setWorkflowMetadata`, `addTags`/`removeTags` (auto-create unknown names). All-or-nothing **except the four group ops**: an invalid one is skipped into `skippedOperations` and the batch still saves, and unrelated edits can delete an existing group into `removedGroups`. Read both. Saves a draft; needs `publish_workflow` to go live. Pass `skillsUsed` (below). |
| `validate_node_config` | Schema-only validation of node configs (1-50 per call). Per-parameter errors, no graph noise. Side-channel for iteration/debug; `validate_workflow` still gates publish. For ai_tool subnodes set `isToolNode: true`. |
| `validate_workflow` | Validate full SDK code before create/update. Necessary but **not sufficient**: doesn't catch all wiring traps (`.to()`, merge index). |
| `list_credentials` | List accessible credentials (filter by type/project/etc). Returns metadata only, **never secret values**. Discover IDs before binding via `setNodeCredential`. |
| `list_n8n_gateway_services` | List node/credential types the platform can supply managed credentials for (Gateway credits coverage), so the user can skip credential setup for them. |

### Workflow testing & execution

| Tool | What it does |
|---|---|
| `prepare_workflow_pin_data` | Returns JSON Schemas (not data) for nodes that need pinning: triggers, credentialed nodes, and HTTP Request. You generate sample values. |
| `test_workflow` | Run with the pin data you supply. **Auto-pins triggers, credentialed nodes, and HTTP Request.** Code, Edit Fields, If, Data Tables, Execute Command, file ops, and sub-workflow calls run for real. Ask before running if any not-auto-pinned node has side effects. Pin data is per-execution only with no visual indicator in the execution viewer, so tell the user which nodes were pinned after the call. See `n8n-workflow-lifecycle-official` `references/TESTING.md`. |
| `execute_workflow` | Production execution with the real trigger. Wire error handling first. Same side-effect rules as `test_workflow`. **`executionMode` is required** — use `"manual"` for testing or validating the current workflow (including tests against live external services), and `"production"` only when intentionally running the published workflow as a live execution. Structured `inputs` for chat/form/webhook triggers. Returns an execution ID immediately without waiting; poll `get_workflow_execution` for results. |
| `get_workflow_execution` | Fetch an execution by `executionId` + `workflowId` (both required). Metadata only by default; set `includeData: true` (optionally `nodeNames`, `truncateData`) for node inputs/outputs. |

### Data tables

n8n's built-in tabular storage. **Not** an external service. Prefer over external DBs for workflow-local persistent state. Full surface:

| Tool | What it does |
|---|---|
| `create_data_table` | Create a new Data Table. |
| `search_data_tables` | Find existing Data Tables. |
| `rename_data_table` / `rename_data_table_column` | Rename. |
| `add_data_table_column` / `delete_data_table_column` | Schema changes. |
| `add_data_table_rows` | Append rows. |
| `get_data_table_rows` | Read rows (optional filter/sort/pagination). |

### Version history

| Tool | What it does |
|---|---|
| `get_workflow_history` | List a workflow's saved versions, newest first (n8n 2.29.0+). |
| `get_workflow_version` | Fetch a past version's full content by `versionId`. |
| `get_workflow_versions_diff` | Diff two saved versions: nodes/connections added, removed, modified. |
| `restore_workflow_version` | Re-apply a past version as the current draft (records a new history entry). |

### Building n8n Agents

<!-- TEMPORARY: revisit when the Preview tag is removed from Agents in the UI, and when Agents are declared ready for Enterprise. -->
n8n Agents are generally available. The UI shows a Preview tag because they change often and some features you might expect aren't there yet. They aren't ready for Enterprise yet: an Enterprise instance may have them enabled, but don't assume it. If `create_agent` isn't in your tool list, Agents aren't enabled on this instance; say so and offer a workflow instead.

A first-class n8n Agent is configured as JSON through these tools, never with Workflow SDK code. Invoke `n8n-agents-official` before the first call; it decides Agent vs workflow and covers every tool below. The AI Agent node inside a workflow is `n8n-ai-nodes-official`. Agent conversations aren't workflow executions: `get_workflow_execution` only sees workflows an Agent called as tools.

| Tool | What it does |
|---|---|
| `get_agent_builder_reference` | Required reference for Agent config and `mutate_agent` ops. Read before building. |
| `discover_agent_assets` | Find models, chat integrations, attachable workflows, sub-agents, or MCP servers to reference. |
| `search_agents` | Find existing Agents; also discovers sub-agents to attach. |
| `get_agent` | Read a draft's config, resources, runnable state, and `configHash`. Call before `mutate_agent`. |
| `list_agent_versions` | List an Agent's publish history, newest first. |
| `create_agent` | Create a draft (optional initial model/credential/instructions). Returns the editor URL. Include `memory: { enabled: true, storage: "n8n" }` or the Agent is stateless. |
| `mutate_agent` | Apply one config/skill/task/custom-tool change, using the latest `configHash`. |
| `verify_agent_mcp_server` | Test an MCP server + credential and return its tools. Call before adding an `mcpServers` entry. |
| `update_agent_integration` | Connect or disconnect a Slack, Telegram, or Linear channel. |
| `validate_agent` | Validate the draft, its references, and credential access. Required before publish. |
| `call_agent` | Test the draft via built-in Preview chat. Uses real tools/credentials; side effects possible. |
| `publish_agent` | Publish a valid draft; activates its tasks and integrations. |
| `unpublish_agent` | Unpublish; stops live tasks and integrations. |
| `revert_agent` | Restore a draft from a published version. |
| `delete_agent` | Permanently delete an Agent and its resources. |

## The protocol, in order

For any n8n task:

1. **Recognize the matching skill** from the index above. If the task spans skills, recognize the primary one first and pick up others as their triggers come up.
2. **Invoke the skill via the Skill tool** before the first MCP call. Don't call n8n MCP tools blind.
3. **Read saved preferences once before you start changing things** (`get_user_preferences`, when present) and apply them across the task.
4. **Read the SDK reference once per session** before writing workflow code (`get_workflow_sdk_reference`). The most efficient way to avoid SDK-shape mistakes.
5. **Get node types before configuring any node** (`get_node_types`). Guessing parameter names creates invalid workflows, sometimes silently.
6. **Validate before publish, verify after create/update.** Validation catches schema errors. Verification (pulling the workflow back via `get_workflow_details`) catches connection bugs validation misses.
7. **Surface drift when you spot it.** If a tool or parameter doesn't match what a skill says, tell the user. Updates may be needed.

## Reporting skills used

`create_workflow_from_code` and `update_workflow` take an optional `skillsUsed: string[]`. Pass it every time so the n8n team can measure plugin impact on MCP output.

- **Contents:** report each skill exactly as the Skill tool names it, keeping the `-official` suffix: `plugin:skill-official` when plugin-namespaced, else bare `skill-official`. The suffix marks these as ours (vs other n8n packs); the plugin prefix marks plugin vs raw-skill usage.
- **Window:** skills invoked since the last successful create/update call. Resets after each.
- **Limits:** max 50 entries, each max 128 chars.

## Reviewing existing workflows or projects

For audits, code-review, or any task framed as "review this workflow" / "what's wrong with this" / "audit this project," walk the **review checklist**: `n8n-workflow-lifecycle-official` `references/REVIEW_CHECKLIST.md`. Severity-tiered (MUST FIX / SHOULD FIX / NICE TO HAVE), with each item linking to the canonical skill ref for the fix. Distinct from `VALIDATION_CHECKLIST.md` (pre-publish gates for in-progress builds): REVIEW_CHECKLIST is for any workflow, including ones built by anyone, any age.

A review agent should call `get_workflow_details` first, walk the checklist top to bottom, and report findings grouped by severity. MUST FIX items shouldn't be auto-fixed without user confirmation.

## When in doubt

- **Can't find a workflow the user is referring to?** If the user built it in the n8n UI, the most common reason is **MCP access isn't enabled on that specific workflow**: UI-created workflows can default to MCP-disabled and stay invisible until the per-workflow toggle is flipped. Ask the user: "Open the workflow in n8n, Settings, toggle MCP access on." (MCP-created workflows default on, so this only applies to UI-built ones.) See the `n8n-workflow-lifecycle-official` skill (`references/MCP_ACCESS_PER_WORKFLOW.md`).
- The user is right. If they say something's broken, believe them, even if you "know" the workflow is correct. Re-check parameters, fetch the n8n source from `github.com/n8n-io/n8n` to trace logic, find API docs for missing functions. The `n8n-debugging-official` skill walks through this.
- If no skill fits and the task is non-trivial, ask before guessing.
- These skills are opinionated, but considered best practice by the n8n team. The user can override any opinion by editing the SKILL.md, or for one instance by saving an n8n preference. A saved preference beats a default here. The plugin is just markdown.
