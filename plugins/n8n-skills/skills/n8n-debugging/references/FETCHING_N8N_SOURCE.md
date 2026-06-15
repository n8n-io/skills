# Fetching n8n source from GitHub

When a node's behavior contradicts docs or intuition, read the source. The code is truth, and n8n is source-available, so the repo is public.

## The repo

```
https://github.com/n8n-io/n8n
```

n8n monorepo:

- `packages/cli/`: CLI and runtime.
- `packages/core/`: workflow engine.
- `packages/nodes-base/`: built-in nodes.
- `packages/@n8n/nodes-langchain/`: AI nodes.
- `packages/editor-ui/`: web editor.
- `packages/workflow/`: data structures.

For node behavior, `packages/nodes-base/nodes/<NodeName>`.

## How to find the relevant code

### For a built-in node

```
packages/nodes-base/nodes/<Capitalized name>/
```

Examples:

- `packages/nodes-base/nodes/HttpRequest/`
- `packages/nodes-base/nodes/Postgres/`
- `packages/nodes-base/nodes/Slack/`

Inside, you'll find:

- `<Name>.node.ts`: main definition (parameters, operations, execute logic).
- `descriptions/`: parameter shape definitions, often by resource/operation.
- `methods/`: helper methods for resource lookups, etc.
- `actions/`: for some nodes, the actual operation implementations.

### For execution / workflow logic

When the bug is about how n8n executes (timing, item handling, error propagation):

- `packages/core/src/WorkflowExecute.ts`: core execution loop.
- `packages/core/src/Workflow.ts`: data structure and routing.
- `packages/cli/src/commands/`: CLI issues.

Denser. Start with node-level code unless the bug is clearly engine-level.

### For the SDK

- `packages/@n8n/workflow-sdk/`: SDK definition and types.

For "SDK function does X but seems to actually do Y."

## Reading efficiently

### Start at the entry point

For a node, `<Name>.node.ts` has the `execute` function or `executeRouter` map.

```ts
async execute(this: IExecuteFunctions): Promise<INodeExecutionData[][]> {
    // ...node-specific logic
}
```

Most behavior lives in operation-specific files.

### Search for the parameter

To figure out what a parameter does, find `this.getNodeParameter('<name>', ...)` in the node's source.

### Watch for version branches

```ts
if (nodeVersion >= 2) {
    // new behavior
} else {
    // old behavior
}
```

Different version, different behavior. Check `typeVersion` in workflow JSON.

## Useful patterns

### Find when a feature was added

```bash
git log -p packages/nodes-base/nodes/<Name>/ | grep -A 5 -B 5 '<keyword>'
```

GitHub's "Blame" view shows which commit introduced each line. Click through for the PR description.

### Cross-reference with the changelog

`https://github.com/n8n-io/n8n/releases`: per-version release notes.

### Search for the exact error message

```
github.com/n8n-io/n8n: <error message>
```

The throw site shows the triggering condition. Often more specific than the message implies.

## Reading the node's parameter description

Each node has properties defined as:

```ts
description: INodeTypeDescription = {
    displayName: 'HTTP Request',
    name: 'httpRequest',
    properties: [
        {
            displayName: 'Method',
            name: 'method',
            type: 'options',
            options: [...],
            default: 'GET',
        },
    ],
}
```

Each property has `name`, `type`, `displayOptions` (conditional visibility), `default`, `required`.

Read when:

- A parameter "isn't being recognized": check `displayOptions`.
- Unsure what values an option accepts: read `options`.
- Conditional requirement questions: read `displayOptions.show`/`hide`.

## When to fetch vs ask

Reading source is high-effort. The order:

1. Check parameters via `get_node_types` and `get_workflow_details`.
2. Test with `prepare_test_pin_data`, inspect via `get_execution`.
3. Re-read user docs at `docs.n8n.io`.
4. Search GitHub issues for similar reports.
5. **Then** source.

~95% of weird behavior resolves before step 5.

## Citing the source

When you find the cause:

- Cite file and line number.
- Quote the relevant snippet.
- Explain what the code does.

Example:

> "HTTP Request strips the `Authorization` header when `authentication: 'none'`, even if added via `headerParameters`. See `packages/nodes-base/nodes/HttpRequest/V3/HttpRequestV3.node.ts:1247`: headers are filtered after the auth check. Fix: use a Header Auth credential instead of inline headers."

Much more useful than "there might be an issue with headers." User can verify and learns to investigate similarly.

## Reporting bugs upstream

For a confirmed bug:

1. Search existing issues at `github.com/n8n-io/n8n/issues` for the same symptom.
2. If none match, file a new issue at `github.com/n8n-io/n8n/issues/new`. Include: clear repro, n8n version, expected vs actual, relevant source citation, and importantly, a disclaimer about using AI to create the issue.
3. Note the issue number (existing or newly filed) in workflow notes or `CLAUDE.md` so future readers know why a workaround exists.
4. Mark workarounds `<!-- TEMPORARY: ..., fixed in n8n X.Y.Z -->` so maintainers can find and remove them after the fix ships.
