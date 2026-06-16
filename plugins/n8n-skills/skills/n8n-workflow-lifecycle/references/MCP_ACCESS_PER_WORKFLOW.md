# Per-workflow MCP access

Each workflow has an `availableInMCP` flag, controlled by a toggle in the workflow's UI settings. When false, the workflow doesn't appear in `search_workflows` results and the agent can't see it.

## Defaults

- **Agent-created workflows** (via `create_workflow_from_code`) default to `availableInMCP: true`. No toggle step needed.
- **UI-created workflows** can default to off. If a user describes a workflow you can't find, this is the most likely cause.

## When this matters

### User asks about a workflow you can't find

By far the most common case. You search via `search_workflows` and either get nothing or a result set that doesn't include the workflow they're describing. Before assuming it doesn't exist:

> "I can't see a workflow matching that description. Could you check that MCP access is enabled on it? In the n8n UI, open the workflow, go to Settings, and toggle MCP access on. Workflows aren't visible to me until that's enabled."

If they confirm it's already enabled, *then* dig into other causes (wrong project, wrong instance, archived).

### Restricting access to a workflow you built

Agent-created workflows are visible to MCP by default. To revoke access (e.g., temporarily disabling a destructive tool), the user toggles the flag off in the UI.

## Why this exists

Auto-exposing every workflow to MCP would be a security hole: any agent with MCP access could trigger or modify any workflow, including production-critical ones. The opt-in toggle for UI-created workflows is intentional. Agent-created workflows default on because the agent already has full MCP access during creation.
