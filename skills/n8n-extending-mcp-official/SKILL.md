---
name: n8n-extending-mcp-official
description: 'Use when you want to expose an n8n workflow as a tool the coding agent can call. Two cases. (1) Wrap n8n API capabilities the MCP doesn''t natively expose: folder CRUD, tag rename/delete, instance metadata, credential creation. (2) Expose a general-purpose workflow as an agent tool: a workflow that calls a third-party API, runs business logic, or does any task you want the agent to invoke. Triggers on "expose as MCP tool", "build a tool for my agent", "I need to know X" where X isn''t an MCP tool, "create folder", "rename tag", or any capability gap.'
---

<!-- TEMPORARY: update whenever n8n mcp capacities are added. a lot of listed functionalities missing are coming soon -->
# n8n Extending MCP

Any n8n workflow with MCP access enabled becomes a tool the coding agent can call by name. Two common cases:

1. **Wrap n8n capabilities the MCP doesn't expose.** The MCP covers workflow CRUD, validation, execution, data tables, credential listing, execution search, folder/project listing, tag listing and attach/detach. Still missing: folder CRUD, tag rename/delete, instance metadata, credential creation. Build a workflow that hits the n8n API and exposes the result as an agent tool.
2. **Expose a general-purpose workflow as a tool.** A workflow that has nothing to do with n8n itself (calls a third-party API, runs internal business logic, looks something up in a private system) can be MCP-callable. Lets the agent invoke real operations during a coding session.

The MCP calls your workflow as if it were a native tool: input from the `Execute Workflow Trigger`, output from the workflow's last node.

## When to reach for this

Case 1 (wrap n8n capability):

- Folder CRUD (create, rename, move, delete): REST API exists, no MCP tool yet.
- Tag rename/delete: the MCP lists tags (`list_tags`) and attaches/detaches them (`update_workflow` `addTags`/`removeTags`, auto-creating unknown names), but can't rename or delete tag entities. REST API exists for those.
- Instance metadata (limits, plan info, configured integrations): no MCP tool.
- Credential creation: REST API exists (`POST /credentials`), no MCP tool yet.
- Any n8n API operation the MCP doesn't natively expose.

Case 2 (general agent tool):

- A recurring agent task you'd rather codify than re-explain (lookup, format, send).
- An action against a system the agent doesn't have direct access to (private API, internal service, third-party integration).
- Anything you want a future session to invoke without re-deriving the implementation.

Don't reach for this for:

- One-off questions, ask the user directly.
- Things the MCP already exposes natively.

## Non-negotiables

1. **Ask the user before building.** This creates a workflow on their instance, with credentials. They need to OK it explicitly.
2. **Credentials via credential, never text field.** Same rule as everywhere else in n8n. See `n8n-credentials-and-security-official`.

## Protocol

- **Search for existing wrappers first.** `search_workflows({ tags: ['tool'] })` and a capability keyword search. If something matches, use it instead of duplicating.
- **For case 1, build as a stateless, queryable utility.** Takes input, calls n8n's API, returns the result. No side effects. Case 2 may legitimately have side effects (sending, writing); name them in the tool description.
- **Offer to edit the agent's context file yourself** (CLAUDE.md, AGENTS.md, GEMINI.md, whatever the user's agent reads on session start) to add an entry for the new tool. You have Edit/Write tools, so there's no reason to make the user paste a snippet manually. Ask first since it's their config file, then edit it directly when they say yes.

## The pattern, end to end

```
1. User asks for a capability (missing MCP feature, or a workflow they want
   the agent to be able to invoke).
2. You: "I can build a workflow that exposes this as a tool the MCP can call.
   Want me to create it?"
3. User: yes.
4. You build the workflow:
   - Trigger: Execute Workflow Trigger with declared inputs.
   - Body: whatever logic the tool needs (HTTP Request to n8n's API, a
     third-party call, internal computation).
   - Output: structured response.
5. Validate, test, publish.
6. Ask the user if you can add an entry for this tool to their agent context
   file (CLAUDE.md / AGENTS.md / etc.) so future sessions know to search for
   it by name. Edit the file directly when they say yes.
7. The workflow is immediately callable: agent-created workflows have `availableInMCP: true` set by default.
```

## Common case-1 wrappers (missing MCP capabilities)

Most common patterns, by usefulness. Case 2 (general agent tools) is whatever your project needs, no canonical examples.

> **n8n REST API reference:** https://docs.n8n.io/api/api-reference/. Start here for any case-1 wrap. Find the endpoint, then wrap it with an HTTP Request node + `n8nApi` credential. Self-hosted instances expose this at `<instance-url>/api/v1/`.

### 1. Folder management

The MCP can place workflows into existing folders but can't create, rename, move, or delete them. n8n's REST API has a [Folders endpoint](https://docs.n8n.io/api/api-reference/#tag/folders), so a one-time wrap solves this for users who organize folders frequently.

```
Tool: create folder
Input: { projectId: string, name: string, parentFolderId?: string }
Output: { id, name, projectId, parentFolderId? }
```

### 2. Instance metadata

Version, configured integrations, environment info. Useful for the SessionStart drift check or adapting workflows to instance capabilities.

```
Tool: get instance info
Input: {}
Output: { version, edition, integrations: [...], limits: {...} }
```


## How the agent invokes a tool workflow

The MCP **doesn't register each tool-flagged workflow as a separately-named MCP tool.** Discovery and invocation are two steps:

1. **Discover** via `search_workflows({ query: '<keyword>' })`. Workflows with MCP access on return `availableInMCP: true`. Filter for that.
2. **Invoke** via `execute_workflow({ workflowId, inputs })`. Read the input schema first with `get_workflow_details`. The `Execute Workflow Trigger` defines typed fields.

Output is whatever the workflow's last node returns.

**MCP access defaults:** Agent-created workflows default to `availableInMCP: true`. UI-created workflows may default off, in which case the user has to toggle MCP access on in the workflow's settings before it appears in search results. Either way, the user can flip it off later to restrict access.

**This is why the agent-context-file snippet (CLAUDE.md / AGENTS.md / etc.) matters.** Future sessions don't auto-enumerate tool workflows. The snippet tells them the tool exists by name, so they search for it instead of re-deriving the implementation.

## Anti-patterns

| Anti-pattern | What goes wrong | Fix |
|---|---|---|
| Building an MCP-extension workflow without asking the user | Surprise creation of workflows on their instance with credentials | Always ask permission first |
| Not documenting the new tool in the agent's context file | Future sessions don't auto-enumerate tool workflows. Without a hint they'll re-derive the implementation. | Ask the user, then edit CLAUDE.md / AGENTS.md / whichever file their agent reads, directly. Don't make them paste a snippet. |
| Hardcoding the n8n API token in the HTTP Request node | Token leak when the workflow is exported or copied | Use a credential of type `n8nApi` or appropriate header auth |
| Side-effecting tool with no mention of side effects in its name/description | Agent invokes thinking it's a read, ends up sending real messages or writing real data | Name and describe the side effect explicitly (e.g., `Tool: send Slack message`). Read-only is the safer default for case-1 wrappers. |
| Wrapper that does bulk or destructive ops (archive, delete) with no dry-run | One bug touches many workflows | Strong explicit opt-in per call, plus a dry-run mode that lists targets without acting |
| Wrapper returns credential *values* | Token leak via tool output | Return IDs, names, types only. Never the secret. |
| Skipping the validate + verify + test cycle on the wrapper | The "tool" itself is broken, manifests as confusing tool-not-found or empty-response errors | Same lifecycle as any workflow: see `n8n-workflow-lifecycle-official` |

