# n8n MCP tools

Use this index to discover capabilities. Load the live tool schema before each call. Available tools depend on the n8n version, enabled features, and granted scopes.

Tool names omit the client-specific prefix. Use the qualified name exposed by your connected MCP server.

## User preferences

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

## Workflow management

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

## Workflow building

| Tool | What it does |
|---|---|
| `get_workflow_sdk_reference` | Fetch the n8n Workflow SDK reference. **Read this before writing workflow code.** Sections: `patterns`, `patterns_detailed`, `expressions`, `functions`, `rules`, `import`, `guidelines`, `design`, `groups` (n8n 2.33.0+), `all`. |
| `get_workflow_best_practices` | Fetch best-practices for a workflow technique. Call once per technique before searching nodes. `technique: "list"` discovers what's available. |
| `search_nodes` | Discover nodes by capability (e.g. "gmail", "slack", "schedule trigger"). Returns IDs plus discriminators (resource/operation/mode). |
| `get_node_types` | Fetch exact TypeScript parameter definitions for node IDs. **Required before configuring any node.** Don't guess parameter names. |
| `explore_node_resources` | Resolve the real values behind resource-locator (`@searchListMethod`) and load-options (`@loadOptionsMethod`) params: Slack channels, Sheets tabs/docs, DB tables/columns, model lists, labels. Needs a `credentialId` from `list_credentials` (pass `currentNodeParameters` for dependent lookups). Call after `get_node_types` to ground dropdown values instead of inventing IDs. |
| `create_workflow_from_code` | Save a workflow from SDK code. Always include a 1-2 sentence `description`. Pass `skillsUsed` as described in [the router](../SKILL.md#reporting-skills-used). |
| `update_workflow` | Apply atomic ops (max 100): node/connection CRUD, `setNodeCredential`, `setNodeSettings` (per-node onError/retry/executeOnce), `setWorkflowSettings` (errorWorkflow, timezone, callerPolicy, timeouts, save-data policies; n8n 2.29.0+), `setNodeGroups`/`addNodeGroup`/`removeNodeGroup`/`updateNodeGroup` (canvas grouping), `setWorkflowMetadata`, `addTags`/`removeTags` (auto-create unknown names). All-or-nothing **except the four group ops**: an invalid one is skipped into `skippedOperations` and the batch still saves, and unrelated edits can delete an existing group into `removedGroups`. Read both. Saves a draft; needs `publish_workflow` to go live. Pass `skillsUsed` as described in [the router](../SKILL.md#reporting-skills-used). |
| `validate_node_config` | Schema-only validation of node configs (1-50 per call). Per-parameter errors, no graph noise. Side-channel for iteration/debug; `validate_workflow` still gates publish. For ai_tool subnodes set `isToolNode: true`. |
| `validate_workflow` | Validate full SDK code before create/update. Necessary but **not sufficient**: doesn't catch all wiring traps (`.to()`, merge index). |
| `list_credentials` | List accessible credentials (filter by type/project/etc). Returns metadata only, **never secret values**. Discover IDs before binding via `setNodeCredential`. |
| `list_n8n_gateway_services` | List node/credential types the platform can supply managed credentials for (Gateway credits coverage), so the user can skip credential setup for them. |

## Workflow testing & execution

| Tool | What it does |
|---|---|
| `prepare_workflow_pin_data` | Returns JSON Schemas (not data) for nodes that need pinning: triggers, credentialed nodes, and HTTP Request. You generate sample values. |
| `test_workflow` | Run with the pin data you supply. **Auto-pins triggers, credentialed nodes, and HTTP Request.** Code, Edit Fields, If, Data Tables, Execute Command, file ops, and sub-workflow calls run for real. Ask before running if any not-auto-pinned node has side effects. Pin data is per-execution only with no visual indicator in the execution viewer, so tell the user which nodes were pinned after the call. See `n8n-workflow-lifecycle-official` `references/TESTING.md`. |
| `execute_workflow` | Run the workflow with live services. Credentialed and HTTP Request nodes are not auto-pinned. Confirm authorization for their effects. Use `test_workflow` for generated mock data. **`executionMode` is required** — use `"manual"` for testing or validating the current workflow (including tests against live external services), and `"production"` only when intentionally running the published workflow as a live execution. Structured `inputs` for chat/form/webhook triggers. Returns an execution ID immediately without waiting; poll `get_workflow_execution` for results. |
| `get_workflow_execution` | Fetch an execution by `executionId` + `workflowId` (both required). Metadata only by default; set `includeData: true` (optionally `nodeNames`, `truncateData`) for node inputs/outputs. |

## Data tables

n8n's built-in tabular storage. **Not** an external service. Prefer over external DBs for workflow-local persistent state. Full surface:

| Tool | What it does |
|---|---|
| `create_data_table` | Create a new Data Table. |
| `search_data_tables` | Find existing Data Tables. |
| `rename_data_table` / `rename_data_table_column` | Rename. |
| `add_data_table_column` / `delete_data_table_column` | Schema changes. |
| `add_data_table_rows` | Append rows. |
| `get_data_table_rows` | Read rows (optional filter/sort/pagination). |

## Version history

| Tool | What it does |
|---|---|
| `get_workflow_history` | List a workflow's saved versions, newest first (n8n 2.29.0+). |
| `get_workflow_version` | Fetch a past version's full content by `versionId`. |
| `get_workflow_versions_diff` | Diff two saved versions: nodes/connections added, removed, modified. |
| `restore_workflow_version` | Re-apply a past version as the current draft (records a new history entry). |

## Building n8n Agents

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
