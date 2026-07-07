---
name: n8n-agents-official
description: 'Use when building or editing any AI feature in n8n: AI Agents, Text Classifier, Information Extractor, Sentiment Analysis, Summarization Chain, Basic LLM Chain, embeddings, vector stores, single one-shot LLM calls, or AI media generation (image / audio / video) via the native LangChain provider nodes. Triggers on any `@n8n/n8n-nodes-langchain.*` node, "agent", "chat assistant", "LLM with tools", "tool calling", "fromAi", "system prompt", "memory window", "structured output", "outputParser", "function calling", "RAG", "vector store", "embeddings", "classify with AI", "extract fields with LLM", "sentiment analysis", "summarize with LLM", "single LLM call", chat triggers with files, AI image / video / audio generation, or any multi-turn or one-shot LLM behavior.'
---

# n8n Agents

The n8n Agent node (`@n8n/n8n-nodes-langchain.agent`) is a multi-turn LLM driver with sub-nodes for the model, memory, tools, and optional output parser.

## When to use the Agent node vs raw chat completion

Decision:

- **Need tool calls, multi-turn reasoning, or memory?** Agent. Also a fine default when you don't want to think about it: standardizing on Agent across the workflow is reasonable and makes the path to upgrade simpler.
- **Want the lightest possible single-shot text-out call?** Basic LLM Chain (`@n8n/n8n-nodes-langchain.chainLlm`) with a chat-model sub-node (`OpenRouter Chat Model`, `OpenAI Chat Model`, `Anthropic Chat Model`, etc.). No agent loop, no tool/memory/parser slots, easier to debug. Note: chat-model nodes are sub-nodes, and they don't run standalone. They wire into a chain or agent. Agent works here too if you'd rather standardize.
- **Routing to one of N output branches based on natural-language input (the AI's job is to pick the branch)?** Use the Text Classifier node (`@n8n/n8n-nodes-langchain.textClassifier`). N output handles, one per category, and downstream paths wire directly into each. Every category needs both a name AND a description (the description is what the model picks against, names alone aren't enough). Set `options.enableAutoFixing: true` for robustness on edge inputs. Pair with a chat-model sub-node (`OpenRouter Chat Model`, `OpenAI Chat Model`, etc.). Don't reach for Agent + Switch for this. Text Classifier is one node and purpose-built.
- **Structured output but no tools?** Agent is the easier default with future expansion in mind. Basic LLM Chain also accepts an `outputParserStructured` sub-node and works fine where you want the lighter node.
- **Image / audio / video generation?** The native single-call node for that provider when calling them directly (OpenAI Image, Gemini Image, ElevenLabs, etc.). HTTP Request when routing through an aggregator (OpenRouter, Together, etc.), because no native aggregator node exists and the native nodes hardcode their provider's base URL on the media operation. **Don't wrap media generation in an Agent**, see "Binary and the agent boundary" below.

There are other LangChain "chain" / utility nodes for narrow tasks: Information Extractor (pull structured fields from text), Sentiment Analysis (3-way branch), Summarization Chain, Basic LLM Chain.

Agent is a reasonable default for most LLM steps. Reach for Basic LLM Chain when you specifically want the leaner node for a one-shot text call with no tools, memory, or iteration. Reach for Information Extractor / Sentiment Analysis / Summarization Chain / Text Classifier when one of those purpose-built nodes matches the task exactly.

## Non-negotiables

1. **Tool names and descriptions are part of the prompt.** The model picks tools by name and description. Vague tool node names like (`doStuff`) or weak descriptions ("does things with the data") cause silent failure: the model skips your tool, mis-selects it, or hallucinates parameters. Treat both like API design. See `references/TOOLS.md`.
2. **Structured output: parse AND autoFix.** `outputParserStructured` with `autoFix: true` and a coding-capable fixer model (e.g., Claude Sonnet 4.6) is the production pattern.

## Strong defaults

- **Tool descriptions are modular prompt fragments.** Anything specific to *how to call this tool* belongs in the tool's description, not the system prompt. Keeps the system prompt focused, and tools become reusable across agents. See `references/SYSTEM_PROMPT.md`.
- **Sub-workflow tools (`toolWorkflow`) for anything multi-step.** Any workflow becomes a tool with typed `fromAi()` inputs, and composes with branching, error handling, sub-workflows. See `references/SUBWORKFLOW_AS_TOOL.md`.
- **Wrap tools with user-visible side effects in human review.** Sends, payments, refunds, account changes. Gate them behind a Slack / Chat / Discord / Telegram approval node so a human signs off before the tool runs. See `references/HUMAN_REVIEW.md`.

## The sub-node pattern

The Agent node has a main input (the prompt or user message) and sub-node inputs:

```ts
const aiAgent = node({
    type: '@n8n/n8n-nodes-langchain.agent',
    config: {
        name: 'Customer Support Agent',
        parameters: {
            promptType: 'define',
            text: '={{ $json.userMessage }}',
            options: {
                systemMessage: '...',
                passthroughBinaryImages: true,    // for vision / multimodal
            },
        },
        subnodes: {
            model: openRouterModel,
            memory: simpleMemory,
            tools: [generateImage, editImage, searchKnowledgeBase],
            outputParser: structuredParser,    // optional
        },
    },
})
```

The four sub-node slots:

- **`model`** (required): the language model. OpenAI, Anthropic, OpenRouter, etc. Use chat-model variants, not completion variants.
- **`memory`** (optional): conversation memory. Without it, every call is stateless. See `references/MEMORY.md`.
- **`tools`** (optional, but the point of using an agent): tools the agent can call. See `references/TOOLS.md`.
- **`outputParser`** (optional): forces structured JSON output. See `references/STRUCTURED_OUTPUT.md`.

## Triggers

Different triggers shape the input differently:

- **Chat Trigger (`@n8n/n8n-nodes-langchain.chatTrigger`)** with `availableInChat: true`: powers the canvas chat tester so you can poke at an agent while building it. Input is `{ chatInput, sessionId, files[] }`. `sessionId` is what memory keys on, so pass it through wherever conversation continuity is needed. Files come in via `files[]`, see binary section below. Not a production surface, use Slack / Discord / Teams / Telegram / webhook for that.
- **Webhook**: arbitrary input shape, no session by default. Manage continuity by passing a session/conversation ID through the request body and forwarding it to the memory node.
<!-- TEMPORARY: update below this to include a link to the new agent paradigm when it is released -->
- **External chat surface (Slack, Discord, Teams, Telegram)**: every chat-triggered workflow that posts replies MUST filter out the bot's own user ID, or it loops forever potentially crashing n8n. Prefer trigger-level filtering when the surface supports it (Slack's `options.userIds` is an exclusion list); otherwise filter in the first node after the trigger. Semantics differ per surface, see `references/CHAT_AGENT_PATTERNS.md`. Beyond the anti-loop filter, a simple bot (trigger → agent → reply) is fine in one workflow. Split into a "shell" workflow + agent-core sub-workflow once you need loading UX, sub-agents, reuse across surfaces, or robust error handling.
- **Manual / Schedule**: ad-hoc invocations. Memory rarely useful unless explicitly continuing a previous run.
- **Execute Workflow Trigger** (sub-workflow): when an agent is itself a tool of another agent. Treat the trigger's declared inputs as the contract.

## Binary and the agent boundary

The model can *see* uploaded files (vision) via `passthroughBinaryImages: true`. But **tools cannot receive binary**, and `fromAi()` parameters are JSON only. Base64 is also not accepted by tools, even through non-AI bindings.

Workaround: pre-stage uploads to storage before the agent runs, inject the storage keys into the system prompt, tools accept the key as a string parameter and re-fetch internally. Full pattern in `n8n-binary-and-data-official` `references/AGENT_TOOL_BINARY.md`.

On the output side: the Agent's output formatter is text-shaped (or structured-text when an `outputParser` is wired). When a model returns binary (image bytes, audio bytes, video), the Agent doesn't surface it at all. There's nothing to dig out downstream, and trying to recover it via a Code or Set node after the Agent does not work. **For one-shot media generation, use the provider's native single-call node directly such as `@n8n/n8n-nodes-langchain.googleGemini` or `@n8n/n8n-nodes-langchain.openAi`.**

The exception: when a media step genuinely belongs in an agent (one tool among several, picked based on conversation context, or editing a previously-generated image), the workaround is a tool sub-workflow that uploads the result to storage and returns a key or URL. Pattern in `n8n-binary-and-data-official` `references/AGENT_TOOL_BINARY.md`. Don't reach for this by default. The upload + key + re-fetch path adds nodes and a storage dependency you don't otherwise need. Only when the orchestration actually requires an agent's tool selection.

## What goes in the system prompt vs the tool description

| Belongs in **system prompt** | Belongs in the **tool's description** |
|---|---|
| Persona, role, voice | What this specific tool does |
| Output format rules ("respond in markdown") | When to use this tool vs others |
| Refusal/safety behavior | What each parameter means and its expected shape |
| Display protocols ("show images via `![]()` markdown") | Examples of good vs bad invocations |
| Universal context (current date, user role) | Tool-specific gotchas (rate limits, edge cases) |
| Inter-tool flow ("after generating, always show via display protocol") | Tool-specific input transformations |

Benefit: tools become reusable. A well-described tool works in any agent that drops it in. The system prompt stays focused on role and shared behavior.

For deeper guidance and worked examples, see `references/SYSTEM_PROMPT.md` and `references/TOOLS.md`.

## Tool selection: the four types

Pick the lightest option that covers the job:

- **Native n8n tool node exists?** (e.g., `slackTool`, `gmailTool`, `calculatorTool`) Use it. Lowest config overhead.
    - **Native node is missing an operation or needs custom params** (e.g., a Notion endpoint the node doesn't expose, a non-standard header, a different pagination shape)? HTTP Request Tool with the service's "Predefined Credential Type". Reuses the existing OAuth / API-key credential, gives full API access, no custom auth code.
- **Multi-step logic, or reusing a sub-workflow already in the project?** Sub-workflow as tool (`toolWorkflow`). Anything you can build as a workflow becomes a tool with typed `fromAi()` inputs. The most powerful option in n8n, so default here when in doubt. See `references/SUBWORKFLOW_AS_TOOL.md`.
- **Calling an external HTTP API the agent should orchestrate directly?** HTTP Request Tool. Also good for slow async work via long-poll callback.
- **Tool already exists as a published, MCP-accessible workflow?** MCP tool. Useful for cross-workflow agent capabilities. See `n8n-extending-mcp-official`.

See `references/TOOLS.md` for deeper guidance on each option and how to wire `fromAi()` parameters.

## Human review

Before adding or skipping human review on a tool, check with the user. Whether sign-off is needed is a product / policy call (blast radius, audit requirements, how much they trust the model) that the user is better positioned to make than you. Surface the question, recommend based on the criteria below, and let them decide.

When a tool's effects need human approval before execution (sends, payments, refunds, account changes, customer-facing actions), wrap it with a review tool node: `slackHitlTool`, `discordHitlTool`, `telegramHitlTool`, `gmailHitlTool`, etc. (n8n's node names use `Hitl` for the human-in-the-loop pattern, and "human review" is what it's called in the UI.) The review node sits between the wrapped tool and the agent on the `ai_tool` connection: the wrapped tool's `ai_tool` output wires into the review node, and the review node's `ai_tool` output wires into the Agent. The agent calls through, the review node pauses for approval, on approve, the wrapped tool runs.

Default to / recommend human review when:

- The tool sends, pays, refunds, or otherwise mutates user-visible state.
- The approver is different from the chatter (manager-approves-customer-action, support team approves a customer-triggered refund).
- The trigger is non-interactive (order, form, schedule) but the tool's effect needs human sign-off.

Approval messages should display the **actual parameters the wrapped tool will receive**, not text the model paraphrases. Use `$tool.parameters.<name>` directly, or iterate over `$tool.parameters` to list every param. Don't fill the approval text via `fromAi()`. You'd be approving a paraphrase, not the literal call. Customize button labels with the actual values, e.g. `Approve {{ $tool.parameters.amount }} refund`.

Full config patterns, per-platform setup, and the multi-channel approver pattern in `references/HUMAN_REVIEW.md`.

## Output parsing: when and how

Add an `outputParser` sub-node when downstream needs structured data, not free-form text.

```ts
const parser = outputParser({
    type: '@n8n/n8n-nodes-langchain.outputParserStructured',
    config: {
        parameters: {
            schemaType: 'manual',
            inputSchema: JSON.stringify({
                type: 'object',
                properties: {
                    score: { type: 'integer', minimum: 1, maximum: 5 },
                    category: { type: 'string', enum: ['bug', 'feature', 'question'] },
                    reason: { type: 'string' },
                    tags: { type: 'array', items: { type: 'string' } },
                },
                required: ['score', 'category', 'reason'],
            }),
            autoFix: true,
            customizeRetryPrompt: true,
            prompt: '...retry instructions...', // generally leave as default
        },
        subnodes: {
            languageModel: fixerModel,    // coding-capable model, e.g. Claude Sonnet 4.6
        },
    },
})
```

1. **Use `schemaType: 'manual'` with a real JSON schema, not `jsonSchemaExample`.** An example can't express optional fields, enums, value ranges, or array constraints, so you outgrow it the first time the shape gets non-trivial. A schema lets you mark fields required vs optional, define enums, constrain numbers and string formats, and gives the model clearer rules to follow. Reach for `schemaType: 'fromJson'` with an example only for one-off shapes you're certain will never grow constraints.
2. **`autoFix: true` adds retry on parse failure.** Wire a coding-capable model as the fixer sub-node (e.g., Claude Sonnet 4.6 or similar). Fixing malformed JSON against a schema is a structured-output / coding task, and a weak or generic model often produces another malformed retry, defeating the point.

For the full pattern including custom retry prompts, see `references/STRUCTURED_OUTPUT.md`.

## Memory: brief mental model

- **No memory:** stateless. Right for one-shot tasks (classify, summarize).
- **`memoryBufferWindow`:** keeps the last N messages per memory key and persists across executions via n8n's internal store. The key is whatever expression you bind to `sessionKey`. Chat triggers fill `sessionId` automatically, but you can key on anything (Slack `thread_ts`, a webhook conversation ID, a multi-tenant composite). The default for chat memory. The "window" is the sliding cap on how many messages stay in context, not a scope on persistence.
- **`memoryPostgres` / `memoryRedis` / similar:** reach for these when you need to query or read memory **outside** the agent: displaying conversation history in your own UI, analytics on past chats, or sharing memory with another system. Otherwise `memoryBufferWindow` is enough.

Plumb a stable key from the trigger to memory consistently, or conversations get crossed. See `references/MEMORY.md`.

## RAG (retrieval augmented generation)

n8n has the LangChain RAG primitives: document loaders, text splitters, embeddings, vector stores, retrievers, rerankers. The pieces work, but opinionated end-to-end recipes ("which vector store, which chunking, when to rerank") depend heavily on data shape and scale.

This skill keeps RAG opinions thin on purpose. See `references/RAG.md` for more details on RAG.

## Reference files

| File | Read when |
|---|---|
| `references/TOOLS.md` | Adding tools to an agent, choosing between the four tool types, writing tool names and descriptions |
| `references/SUBWORKFLOW_AS_TOOL.md` | Wiring a sub-workflow as an agent tool via `toolWorkflow`, mapping `fromAi` overrides |
| `references/SYSTEM_PROMPT.md` | Writing or refactoring a system prompt, deciding what goes in the system prompt vs tool descriptions |
| `references/STRUCTURED_OUTPUT.md` | Forcing JSON output, configuring autoFix retries, validating downstream |
| `references/MEMORY.md` | Choosing a memory type, persistence and sessionId handling |
| `references/RAG.md` | Building retrieval-augmented agents, intentionally a stub |
| `references/HUMAN_REVIEW.md` | Adding human approval to a tool, configuring approval messages, multi-channel approver patterns |
| `references/CHAT_AGENT_PATTERNS.md` | Building a chat agent on Slack, Discord, Teams, Telegram, or any custom chat surface, multi-workflow shell + core + sub-agents topology |

## Anti-patterns

| Anti-pattern | What goes wrong | Fix |
|---|---|---|
| Generic tool names (`doStuff`, `runQuery`) | Model can't tell which tool to pick, skips them or hallucinates parameters | Verb-first specific names: `Search customer database`, `Generate image with Veo` |
| Empty or one-line tool descriptions | Model has no clue when to invoke, bad selection | Write a real description: what it does, when to use, parameter meanings |
| Cramming everything into the system prompt | Bloated prompt, reuse impossible, per-tool guidance buried | Move tool-specific instructions to tool descriptions, keep system prompt to persona + global rules |
| Code-node tool where a sub-workflow would work | Not reusable, can't be tested independently, can't compose with branching | Use `toolWorkflow` with a proper sub-workflow |
| Passing binary directly to a tool | Doesn't work, binary can't cross the tool boundary | Pre-stage to storage, pass keys via `fromAi`, tool fetches internally. See `n8n-binary-and-data-official` |
| `outputParserStructured` without `autoFix` | One bad model output and the workflow fails | Set `autoFix: true` with a cheap fixer model |
| Hardcoded `sessionId` or no sessionId | Conversations cross or memory never matches | Pass sessionId from trigger consistently to memory and tools |
| Two near-identical tools instead of one with branching | Model gets confused, selection is non-deterministic | One tool with internal branching driven by parameters |
| Hardcoding a system prompt that's reused across workflows or iterated often | Editing requires republishing, can't share across workflows, tuning churn lives in node JSON | Store in a Data Table, load at runtime |
| Wrapping image / audio / video generation in an Agent | Binary doesn't flow through tools or out of the output formatter, Agent adds nodes for no gain | Use the provider's native single-call node directly (OpenAI Image, Gemini Image, ElevenLabs), HTTP Request only when going through an aggregator |
| Reaching for Agent + Switch to route on natural-language input | Two nodes plus prompt boilerplate where Text Classifier is one node with N built-in output branches | Use Text Classifier (`@n8n/n8n-nodes-langchain.textClassifier`), each category gets its own output handle, wire downstream paths directly |
| Tool that mutates user-visible state (send, pay, refund) without human review | Agent fires irreversible action on a wrong inference | Wrap with the review tool node that fits the channel (Slack/Chat/Discord/Telegram), show actual params via `$tool.parameters` |
| Filling the review approval message via `fromAi()` | The model paraphrases, you approve text not values | Use `$tool.parameters.<name>` directly so the literal call is visible |
| Chat-triggered agent workflow that posts replies without filtering out the bot's own user ID | Bot's own messages re-trigger the workflow, infinite loop that burns runs and tokens until rate limits or n8n concurrency stops it | Prefer trigger-level filtering when available (Slack Trigger's `options.userIds` is an exclusion list, put the bot ID there). Otherwise filter on `$json.user !== '<BOT_USER_ID>'` (or the surface equivalent) as the first node after the trigger. Required for ANY chat-triggered workflow that sends a reply (Slack, Discord, Teams, Telegram), regardless of complexity. See `references/CHAT_AGENT_PATTERNS.md` for per-surface semantics |
| Passing the bare blocks array to the Slack node's `blocksUi` when the agent returns Block Kit | The Slack node accepts the input silently and posts the message with no rich content; no error, no warning | Wrap as `{ "blocks": [...] }` with the value as a real array, not a stringified one. Expression: `={{ { "blocks": $('Agent').item.json.output.blocks } }}`. See `n8n-node-configuration-official` `references/COMMS_NODES.md` "Block Kit messages" |

