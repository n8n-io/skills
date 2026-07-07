# Folder limitations

The MCP can place workflows into folders that **already exist**. It cannot create folders, move folders, or move workflows between folders. The typical failure mode:

> User: "Create five workflows for the Customer Data project, organized into a `Reports` folder."
> Agent: *creates five workflows at the project root, doesn't mention folders*
> User: *finds workflows scattered across the root, has to drag them in one by one*

Don't be that agent.

## What you can do

| Operation | Available? |
|---|---|
| List existing folders (`search_folders`) | ✅ |
| Place a workflow into an existing folder (via `create_workflow_from_code` parameter) | ✅ |
| Search workflows by folder | ✅ |
| Create a new folder | ❌ |
| Move an existing folder | ❌ |
| Move an existing workflow into a different folder | ❌ |

## The protocol when the user mentions a folder

1. **Call `search_folders`** for the relevant project.
2. **If the folder exists**, place the workflow there via the `create_workflow_from_code` parameter.
3. **If it doesn't**, surface this *before* building. Use the message below or close to it.

### What to say when the folder doesn't exist

> "I can place workflows into folders that already exist, but I can't create new folders via the MCP. I don't see a `<folder-name>` folder in the `<project-name>` project. Four options:
>
> 1. Create the folder yourself in the n8n UI, and I'll then place workflows into it.
> 2. Use an existing folder. I see: `<list>`. Want one of those?
> 3. Place at the project root, and you can drag them later.
> 4. Build a folder-creation MCP extension once, then I'll create folders directly going forward. n8n's REST API has a Folders endpoint (https://docs.n8n.io/api/api-reference/#tag/folders), so this is a one-time wrap. See `n8n-extending-mcp-official`.
>
> Which would you like?"

The fourth option is worth surfacing when the user creates folders often, or expects to in the future. One-time setup, then this limitation is gone for them. For users hitting this once, options 1-3 are usually the right answer.

Adjust wording, but always:

- Be explicit about the limitation.
- Offer concrete alternatives.
- Don't proceed silently.

## When the user is creating many workflows

Batching makes the limitation worse: scattered workflows mean N drag-and-drops, not one.

If many workflows are requested in a folder that doesn't exist:

1. Pause before creating any.
2. Surface the limitation once.
3. Wait for the user's choice.
4. Batch-create.

