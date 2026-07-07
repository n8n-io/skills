# Sub-workflow as agent tool

The default agent-tool shape for anything beyond one node is the `Tool Workflow` node (`@n8n/n8n-nodes-langchain.toolWorkflow`). Any sub-workflow becomes a tool the agent can call, with typed inputs filled by `fromAi()`. Composes with everything good about n8n: branching, error handling, sub-workflow reuse, native nodes, custom logic.

If you're tempted to write a Code-node tool: a sub-workflow is usually cleaner, but not always. See "When NOT to use sub-workflow as tool" below for the exception.

## Why this is the default in n8n

In raw LangChain, a tool is a function in code. In n8n, a tool can be a whole workflow, meaning it can:

- Branch on input (IF/Switch nodes).
- Call multiple APIs and aggregate.
- Have its own error handling, retries, fallbacks.
- Call OTHER sub-workflows.
- Read/write Data Tables.
- Be tested independently with `test_workflow` and pinned data.
- Be reused across agents AND non-agent workflows.

A function-as-tool can't do most of this without growing into a workflow anyway. n8n gives you the workflow primitive directly.

## The shape

Two things you need:

1. **A sub-workflow with an `Execute Workflow Trigger`** that declares typed inputs.
2. **A `Tool Workflow` node** in the agent's workflow that points at the sub-workflow and binds its parameters via `fromAi()`.

### The sub-workflow side

```ts
const subTrigger = trigger({
    type: 'n8n-nodes-base.executeWorkflowTrigger',
    config: {
        parameters: {
            workflowInputs: {
                values: [
                    { name: 'imagePrompt', type: 'string' },
                    { name: 'imageName', type: 'string' },
                    { name: 'sessionId', type: 'string' },
                ],
            },
        },
    },
})
```

Each declared input becomes a parameter the caller can fill. Type enforcement happens on the agent side via the `type` argument of `$fromAI(key, description, type, defaultValue?)`, not at the trigger itself. Allowed types: `string`, `number`, `boolean`, `json`. A wrong-typed value fails the call, so match the type in the trigger and in `$fromAI`.

**The trigger MUST be in "Define Below" mode (typed fields), not passthrough.** Passthrough has no schema, so the agent has nothing to fill via `fromAi`. Two exceptions: (a) the sub-workflow needs binary, in which case it can't be wired as an agent tool directly (pre-stage binary to storage and pass storage keys as typed string fields instead), or (b) the sub-workflow takes no inputs at all, in which case passthrough is the only option since Define Below requires at least one field, and the tool's only decision is whether to invoke (see `TOOLS.md` "zero `fromAi` parameters"). See `n8n-binary-and-data-official` `AGENT_TOOL_BINARY.md` and `n8n-subworkflows-official` SKILL.md "Sub-workflow inputs and outputs".

### The Tool Workflow side

```ts
const generateImageTool = tool({
    type: '@n8n/n8n-nodes-langchain.toolWorkflow',
    config: {
        parameters: {
            workflowId: { __rl: true, value: '<sub-workflow-id>', mode: 'id' }, // no @searchListMethod on this RLC: get the real ID from search_workflows
            workflowInputs: {
                mappingMode: 'defineBelow',
                value: {
                    imagePrompt: '={{ $fromAI("imagePrompt", "Detailed prompt describing the desired image", "string") }}',
                    imageName: '={{ $fromAI("imageName", "Storage key of an existing image to edit, or empty for new generation. Format: \\"abc123.png\\"", "string") }}',
                    sessionId: '={{ $("Chat Trigger").first().json.sessionId }}',
                },
                schema: [
                    { id: 'imagePrompt', displayName: 'imagePrompt', type: 'string', display: true },
                    { id: 'imageName', displayName: 'imageName', type: 'string', display: true },
                    { id: 'sessionId', displayName: 'sessionId', type: 'string', display: true },
                ],
            },
        },
    },
})
```

The mapping is per-input:

- **Agent-filled**: `={{ $fromAI('paramName', 'description', 'string') }}`. Agent decides the value.
- **Workflow-filled**: `={{ $('SourceNode').first().json.field }}`. Your workflow plumbs it in.

The `sessionId` example is critical: it's NOT an agent decision. Plumbed from the chat trigger so memory and downstream session-keyed work stays consistent. Don't put `sessionId` behind `fromAi` or the agent will fabricate one.

## What the agent sees

The agent sees the tool's **name** (the Tool Workflow node's name) and **description** (a parameter on the node). Both follow the rules from `TOOLS.md`: specific, written like API docs, treated as prompt.

The agent does NOT see:

- Sub-workflow internals.
- The sub-workflow's name (only the Tool Workflow node's name).
- Plumbed-in values like `sessionId`. Only `fromAi` parameters appear in the tool schema.

Encapsulation: the sub-workflow can be refactored heavily without changing what the agent sees.

## Wiring example: image-edit tool

Goal: an agent that can generate or edit images. Both share most logic (prompt → Gemini → upload → return URL), but they differ in whether they download an existing image first.

**Sub-workflow `Generate or edit image` (tags `subworkflow`, `tool`):**

```
[Execute Workflow Trigger: { imagePrompt, imageName, sessionId }]
    ↓
[Crypto: hash for new filename]
    ↓
[IF: imageName empty?]
    ├── empty (generate from scratch) ──► [Gemini: image generation] ──┐
    └── not empty (edit existing):                                     │
        [S3: Download by imageName]                                    │
            ↓                                                          │
        [Gemini: image edit with downloaded binary] ───────────────────┤
                                                                       ↓
                                                              [S3: Upload result]
                                                                       ↓
                                                              [Set: { imageUrl, imageKey }]
```

**Agent side, one Tool Workflow node.** Let the agent decide mode via the `imageName` parameter:

```ts
const generateOrEditImage = tool({
    type: '@n8n/n8n-nodes-langchain.toolWorkflow',
    config: {
        name: 'Generate or Edit Image',
        parameters: {
            description: 'Use to create a new image from a prompt OR edit an existing image. Pass imageName as the storage key (e.g. "abc123.png") to edit; leave empty to generate from scratch.',
            workflowId: { value: '<id>', ... }, // real ID from search_workflows (no @searchListMethod)
            workflowInputs: {
                mappingMode: 'defineBelow',
                value: {
                    imagePrompt: '={{ $fromAI("imagePrompt", "Detailed image description") }}',
                    imageName: '={{ $fromAI("imageName", "Storage key of existing image to edit, or empty for new generation") }}',
                    sessionId: '={{ $("Chat Trigger").first().json.sessionId }}',
                },
            },
        },
    },
})
```

One tool, and the agent picks the mode by what it puts in `imageName`. Two near-identical tools would have made selection harder. (In a real workflow you might still split for clearer descriptions, but the principle holds: collapse near-identical tools.)

## Patterns inside the sub-workflow

### Return a stable shape

The caller (agent or deterministic workflow) receives whatever the sub-workflow's last node outputs. Pick a shape and keep it across modes:

```json
{ "imageUrl": "https://...", "imageKey": "abc123.png" }
```

Don't sometimes return `{ url, key }` and other times `{ result: { url, key } }`. Sub-workflow tools are reusable across agents AND deterministic workflows, and the output shape is a contract every caller depends on: agents read it as part of the prompt, deterministic callers wire downstream nodes to specific paths. Drift breaks callers silently.

For calls that can fail "expectedly" (e.g., search with no results), return:

```json
{ "ok": false, "error": "no_results", "message": "No matches found for query" }
```

Either kind of caller can branch on `ok` without per-tool error wiring.

### When to throw instead: Stop and Error

For unexpected-but-handled errors (auth failure, upstream down, malformed input the sub-workflow can't recover from), use a `Stop and Error` node with a detailed message:

```ts
node({
    type: 'n8n-nodes-base.stopAndError',
    config: {
        parameters: {
            message: 'Auth failed for {{ $json.provider }}: {{ $json.error.code }}',
        },
    },
})
```

This propagates as a thrown error. Agents see a tool error and can retry, switch tools, or report. Deterministic callers catch it via `onError: 'continueErrorOutput'` on the Execute Workflow node. Pick this over `{ ok: false, ... }` when the outcome is a true error, not a normal branch the caller should evaluate.

For the broader error story (4xx/5xx mapping, retries, error workflows, deciding throw vs. continue), see the `n8n-error-handling-official` skill.

### Keep tool sub-workflows discoverable

Tag them with `tool` (plus a domain tag like `customer` where it applies) so `search_workflows({ tags: ['tool'] })` finds them. Attach tags with `update_workflow` `addTags` after creating, since `create_workflow_from_code` can't set tags. Give them a plain descriptive name; the Tool Workflow node references them by ID (stable), and tags carry the category.

### Wire `onError: 'continueErrorOutput'` on fallible nodes

Inside the sub-workflow, fallible nodes (HTTP, S3, DB) should set `onError: 'continueErrorOutput'` and route to a clean error response. Both agent and deterministic callers receive a structured error rather than the sub-workflow halting silently.

### Don't put `sessionId` behind `fromAi`

The agent doesn't know your session ID, and behind `fromAi` it'll hallucinate a UUID. Plumb it from the trigger:

```ts
sessionId: '={{ $("Chat Trigger").first().json.sessionId }}'
```

### Treat the input contract as an API

The `Execute Workflow Trigger`'s declared inputs are this tool's API. Document them in the sub-workflow's `description`:

```
description: |
  Generates or edits an image.
  Inputs:
    imagePrompt (string, required): detailed image description.
    imageName (string, optional): storage key of existing image to edit. Empty for new generation.
    sessionId (string, required): chat session ID, used for storage keying.
  Returns:
    { imageUrl, imageKey }
```

This makes the sub-workflow understandable on its own.

## Testing the sub-workflow independently

A sub-workflow tool can be tested without the agent:

1. `prepare_test_pin_data` on the Execute Workflow Trigger generates representative input.
2. `test_workflow` runs the sub-workflow with that pinned data.
3. Verify the output shape matches what the agent will receive.

## When NOT to use sub-workflow as tool

- **Simple one-node wrappers.** "Call this HTTP endpoint and return" is shorter as an HTTP Request Tool.
- **One-off code-only logic specific to this agent.** A few lines of JS/Python that exist nowhere else and won't be reused work fine as a Code-node tool. Decision rule: reusable business logic → sub-workflow, one-off agent-specific transform → Code-node tool. Either way, the Code rules in `n8n-code-nodes-official` still apply (Code is a last resort, expressions and Edit Fields first, no comments unless WHY is non-obvious).
- **Capabilities that already exist as native tool nodes.** Don't wrap `slackTool` in a sub-workflow.

For everything else, sub-workflow as tool is the default.

## Cross-references

- For the four tool types overview: `TOOLS.md`.
- For how `fromAi` parameter descriptions affect agent behavior: `TOOLS.md`'s "fromAi" section.
- For sub-workflow patterns generally (stateless, naming, search-before-build): `n8n-subworkflows-official`.
- For the Execute Workflow Trigger config details: `n8n-node-configuration-official` `references/TRIGGER_NODES.md`.
- For the Code-node-tool exception and the rules Code follows wherever it's used: `n8n-code-nodes-official`.
