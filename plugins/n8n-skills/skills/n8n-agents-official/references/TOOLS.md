# Agent tools

The agent picks tools by reading their **name** and **description**. Both are part of the prompt. Treat tool design like API design: what it does, when to use it, what each parameter means, and proper error handling.

## The four tool types

### 1. Native tool nodes

Pre-built tool nodes from n8n: `slackTool`, `gmailTool`, `googleSheetsTool`, `calculatorTool`, `httpRequestTool`, etc. Same as their non-tool counterparts, except parameters can be filled by the agent via `fromAi()`.

Pros: minimal config, well-tested integrations, consistent and native feel.
Cons: one node = one operation. Multi-step logic doesn't fit.

Use when: the capability maps cleanly to one existing n8n node and one operation.

### 2. Sub-workflow as tool (`toolWorkflow`)

The default for any tool that does more than one thing. Any n8n workflow becomes a tool, with typed inputs via `Execute Workflow Trigger` filled by `fromAi()`.

Pros: full power of n8n inside the tool: branching, error handling, sub-sub-workflow calls, native nodes, custom logic. Reusable across agents. Independently testable.
Cons: one extra workflow boundary, (very) slight latency.

Use when: the capability is more than one node, the logic might be reused, or you want testability.

The canonical n8n way to build agent capabilities. Covered in depth in `SUBWORKFLOW_AS_TOOL.md`.

### 3. HTTP Request Tool

A wrapper around the HTTP Request node that exposes its parameters to the agent.

Pros: any HTTP API is a tool with one node.
Cons: only HTTP. Auth/retry/error handling is yours to wire.

Use when: calling a single external API the agent should orchestrate. One thing to know: HTTP Request has its own HTTP-level timeout (default 5 minutes). For slow endpoints, bump `options.timeout`. Agent tools themselves have no timeout, the agent will wait as long as the tool takes.

Also useful when you want to **give the agent more agency over the call shape**. A native Notion tool node exposes one operation with fixed parameters. Point an HTTP Request Tool at the Notion API with the Notion predefined credential, and the agent can compose the path, method, and full JSON body itself, covering operations the native node doesn't expose. Trade-off: the agent is now writing API requests, which is more error-prone than deterministic tools and needs a capable model (Sonnet-tier or better) and clear endpoint guidance in the description. The user should understand they are widening the blast radius in exchange for flexibility.

### 4. MCP tool

The MCP Client Tool node connects the agent to any MCP server. Two flavors:

- **External MCP servers**: any third-party or self-hosted MCP (Linear, GitHub, Notion, Sentry, custom internal tools, etc.). The agent gets every tool that server exposes in one node.
- **n8n-hosted MCP**: a workflow on the same n8n instance published with MCP access enabled (per `n8n-extending-mcp-official`). Same client node, just pointed at an n8n MCP trigger URL.

Pros: one node exposes many tools, vendor-maintained integrations stay current without you wiring each operation, and n8n-hosted MCP lets one workflow serve many agents and external clients.
Cons: tool descriptions and shapes come from the MCP server, so quality varies and you can't easily tune them. Auth and network reachability are yours to manage.

Use when: a maintained MCP server already covers the capability, or you want to expose your own n8n logic to many agents (internal and external) through one published interface.

## Decision: which tool type?

```
Capability the agent needs?
├── One existing native node + one operation does it
│   └── Use that as a tool node
│
├── More than one node, or logic that might be reused
│   └── Sub-workflow as tool (toolWorkflow). Default to this.
│
├── A single external HTTP API call (or long-running async via webhook callback)
│   └── HTTP Request Tool
│
└── A maintained MCP server covers it, or you want one published n8n workflow to serve many agents
    └── MCP Client Tool (external MCP, or n8n-hosted MCP)
```

## `fromAi()`: how the agent fills tool parameters

Tool parameters that the agent should determine are wrapped in `fromAi()`:

```ts
{
    sendTo: fromAi('recipient', 'Email address of the recipient'),
    subject: fromAi('subject', 'Email subject line, concise and informative'),
    body: fromAi('body', 'Email body in plain text, professional tone'),
}
```

The shape:

```
fromAi(<paramName>, <description>, <type?>, <defaultValue?>)
```

- **`paramName`**: the name the model uses internally. snake_case or camelCase fine, but be consistent.
- **`description`**: tells the model what to fill in. **Part of the prompt.** Be specific: format, range, example.
- **`type`** (optional): `'string'` (default), `'number'`, `'boolean'`, `'json'`. Enforced: a wrong-typed value from the model fails the tool call.
- **`defaultValue`** (optional): used when the model omits the parameter.

A good description for a string parameter:

```ts
fromAi(
    'imageName',
    'Storage reference for an existing image to edit, or leave empty for a new generation. Format depends on the backend: an object-storage key like "abc123.png", a Dropbox file ID, a Google Drive file ID. Use the exact key/ID shown in the system prompt; do not reconstruct.',
    'string'
)
```

A bad description:

```ts
fromAi('imageName', 'image name')   // useless to the model
```

Treat `fromAi` descriptions like JSDoc for an API: the model reads them to figure out what to pass.

## Workflow-filled parameters: hide what the agent shouldn't decide

Tool parameters don't all have to be `fromAi`. Any parameter can be filled deterministically from workflow context, and **workflow-filled values are invisible to the agent**: not in the tool schema, not in any turn, not influence-able by anything the model produces.

```ts
workflowInputs: {
    value: {
        reason: '={{ $fromAI("reason", "Why the user is requesting a refund") }}',  // agent-filled
        customerId: '={{ $("Chat Trigger").first().json.user.id }}',                 // hidden from agent
        maxRefundAmount: '={{ $("Get user tier").first().json.refundLimit }}',       // hidden from agent
        idempotencyKey: '={{ $("Chat Trigger").first().json.sessionId }}',           // hidden from agent
    },
}
```

Use for anything the agent shouldn't be able to get wrong or read:

- **Identity**: `userId`, `customerId`, authenticated actor, tenant scope.
- **Authority limits**: refund caps, tier flags, allowed regions, role-based permissions.
- **Correlation IDs**: `sessionId`, idempotency keys, trace IDs.
- **Anything the agent doesn't need to see** to do its job.

The strongest version: a sensitive tool with **zero `fromAi` parameters**. The agent's only decision is whether to call the tool. A "Refund order" tool can take `orderId` from the chat trigger payload, `amount` from the order record fetched in an earlier node, and `actor` from the authenticated session, all plumbed in deterministically. The agent literally cannot refund the wrong order or the wrong amount, it can only choose whether to fire the call.

Capability-style tool design: give the agent a button to push, not a steering wheel. Pair with the patterns in `HUMAN_REVIEW.md` for actions that need deterministic params AND human sign-off.

## Tool name and description as prompt

Selection process:

1. Model gets the system prompt, conversation, and list of available tools.
2. For each tool, it sees name + description + parameter schema (with `fromAi` descriptions).
3. It picks the tool whose description best matches what it needs to do.

**Bad names and descriptions cause bad selection.** The failure mode isn't always loud: sometimes the model just doesn't call your tool, or it calls a different one with garbage parameters.

### Tool name patterns

Use verb-first specific names:

| Good | Bad | Why |
|---|---|---|
| `Search customer database` | `query` | "query" is generic, "search customer database" is specific |
| `Generate image with Veo` | `imageGen` | Specific tool, specific model, "imageGen" doesn't say which |
| `Edit existing image` | `edit` | "edit" doesn't say what's being edited |
| `Send Slack message to channel` | `slack` | The name should hint at the action, not just the surface |
| `Lookup user by email` | `getUser` | "getUser" doesn't say how |

### Tool description patterns

A well-written tool description has three parts:

1. **What the tool does** (one sentence).
2. **When to use it** (one or two sentences with examples or boundaries).
3. **Parameter format notes** (only if not covered in `fromAi` descriptions).

Example:

```
Edit Image: Modifies an existing image based on a prompt. Use when the user has uploaded an image and asks for changes (color, style, composition, or content edits). Do not use for generating new images from scratch; use Generate Image for that. The `imageName` parameter must be the storage key of the existing image as listed in your available files; do not pass the original filename or a URL.
```

This description does work that would otherwise sit in the system prompt. That's the point. See "Tool descriptions as modular prompts" below.

## Tool descriptions as modular prompts

Anything specific to *how to call this tool* belongs in the tool's description, not the system prompt. Three reasons:

1. **Reusability.** A well-described tool works in any agent. The system prompt doesn't teach each new agent how to use it.
2. **Token efficiency.** The model only "loads" tool descriptions when deciding to use a tool. Per-tool guidance in the system prompt is loaded every turn, even when irrelevant.
3. **Maintainability.** When tool behavior changes, update the tool description, not a paragraph buried in a 5000-token system prompt.

Examples of what to move:

| In the system prompt | Better in the tool description |
|---|---|
| "When generating images, always preserve focus depth" | `Edit Image`: "When editing background only, match the original's depth of field..." |
| "If you call the search tool with no results, summarize that politely" | `Search`: "Returns up to 10 results, and if empty, report 'no matches found' rather than retrying with broader terms" |
| "Use 9:16 aspect ratio for video tools" | `Generate Video`: "Defaults to 9:16 for vertical/mobile, pass `aspectRatio: '16:9'` for landscape" |

Long system prompts often have multiple "when calling X, do Y" sections that can move into X's tool description.

## Granularity: one tool with branching, not two near-identical tools

The model gets confused choosing between near-identical tools. If two tools are ~80% the same internally, consider:

- **One tool with a parameter that branches.** Branch in the sub-workflow based on a parameter value.
- **Two tools only when the use cases are genuinely distinct AND descriptions can clearly differentiate.**

Example: `Send DM` vs `Send Channel Message` are distinct, and the model needs to decide from the user's request. `Generate Image` vs `Edit Image` look distinct but share most logic, so collapse to one with an `imageName` parameter (empty = generate, populated = edit).

## Operational notes

- **Max iterations.** Agents have a configurable tool-call iteration cap. When stuck in a loop, it caps out, surfacing as "max iterations reached" or empty output. Build a fallback, and don't trust graceful recovery.
- **Tool call cost.** Each tool call is at minimum one extra model round-trip. Frequently-called tools should return concise results, since bloated returns burn tokens fast.
- **Tool failure handling.** Wire `onError: 'continueErrorOutput'` on tool sub-workflows where you want the agent to receive an error string rather than halting. The agent can retry, switch tools, or report to the user.

## Cross-references

- For the sub-workflow tool pattern in detail: `SUBWORKFLOW_AS_TOOL.md`.
- For passing binary into tools: `n8n-binary-and-data-official` `references/AGENT_TOOL_BINARY.md`.
- For wrapping APIs as MCP tools accessible to agents: `n8n-extending-mcp-official`.
- For tool naming alignment with the rest of the workflow conventions: `n8n-workflow-lifecycle-official` `references/NAMING_CONVENTIONS.md`.
