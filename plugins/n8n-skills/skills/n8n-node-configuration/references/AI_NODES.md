# AI Agent node: configuration gotchas

The AI Agent node (`@n8n/n8n-nodes-langchain.agent`) is the load-bearing node for AI features in n8n. **For design depth, read the `n8n-agents` skill first.** This file only covers Agent-node-configuration knobs and runtime gotchas not in that skill.

| For | Read |
|---|---|
| When to use Agent vs other AI nodes | `n8n-agents` SKILL.md |
| Sub-node pattern (model, memory, tools, outputParser) | `n8n-agents` SKILL.md |
| System prompt design | `n8n-agents` `SYSTEM_PROMPT.md` |
| Tool design and the four tool types | `n8n-agents` `TOOLS.md` |
| Sub-workflow as tool | `n8n-agents` `SUBWORKFLOW_AS_TOOL.md` |
| Memory backend choice and sessionId | `n8n-agents` `MEMORY.md` |
| Structured output: parser + autoFix | `n8n-agents` `STRUCTURED_OUTPUT.md` |
| Human review on tools | `n8n-agents` `HUMAN_REVIEW.md` |
| Slack / Discord / Teams / Telegram surfaces | `n8n-agents` `CHAT_AGENT_PATTERNS.md` |
| RAG primitives | `n8n-agents` `RAG.md` |
| Binary in agent tools | `n8n-binary-and-data` `AGENT_TOOL_BINARY.md` |

## Always inspect the node first

`get_node_types([{ nodeId: '@n8n/n8n-nodes-langchain.agent' }])`. The Agent's parameter shape evolves often (new sub-node slots, new option fields, new built-in tools). Build against the live shape.

## Streaming

n8n streams Agent responses end-to-end when the trigger and responder both support it:

- **Trigger**: Chat Trigger with `options.responseMode: 'streaming'` (default when `availableInChat: true`), or Webhook with `responseMode: 'streaming'`.
- **Agent**: `options.enableStreaming: true` (default).
- **Responder** (when needed): Respond to Webhook with `options.enableStreaming: true` (default).

When all three are aligned, tokens flow to the caller as the agent generates them.

## Vision / multimodal

`options.passthroughBinaryImages: true` (default) lets the model see uploaded images as image-type messages. Pair with a vision-capable model.

Only the model can see binary. Tools cannot receive it. For tools that need uploaded files, see `n8n-binary-and-data` `AGENT_TOOL_BINARY.md`.

## Iteration cap

`options.maxIterations` defaults to 10, which is low for modern agents with flexible tool sets. Raise it (30-50+) for any non-trivial multi-tool agent. Hitting the cap throws a workflow error (`Max iterations (N) reached`).

## Deterministic tasks

Set `temperature: 0` on the model sub-node for extraction, classification, or any deterministic task. Defaults introduce variability that's annoying in production. Leave higher for creative or open-ended generation.

## Cost control

For high-volume workflows:

- **Don't always pick the biggest frontier model.** Small models for classification or routing, larger for reasoning, reserve frontier for genuinely complex multi-tool agents.
- **`options.batching`** on the Agent: `batchSize` (parallel items, default 1) and `delayBetweenBatches` (ms, default 0) for rate-limited or expensive flows.