# Chat agent patterns: shell + core + sub-agents

For external chat surfaces: Slack, Discord, Microsoft Teams, Telegram, embedded webhook chats. The pieces (memory, tools, sub-workflow as tool, structured output) are covered in their own refs. **This file covers the multi-workflow composition that production chat agents grow into**, plus chat-surface-specific gotchas the other refs don't.

**Anti-loop filtering is required regardless of complexity.** Any chat-triggered workflow that posts a reply MUST filter out the bot's own user ID right after the trigger, or it triggers itself forever. That's the minimum bar for every bot, not a reason to split. Some triggers may have built in parameters for this.

Beyond that, a simple bot (one trigger → one agent → one reply, with the bot-user filter) lives fine in a single workflow. The shell + core + sub-agents split is for production robustness, not the default. It earns its keep once any of these is true:

- The bot needs loading-state UX (typing indicator, reaction, placeholder message) and graceful error handling beyond a single message.
- The bot is invoked from more than one surface (Slack AND Discord, Teams AND Telegram).
- There are specialist domains the agent shouldn't carry inline (Notion DB schema, CRM custom fields, Linear labels).
- The agent or its tools will be reused across other workflows.

If none of those apply, keep it in one workflow (with the bot-user filter still in place).

The shape:

```
   [chat-surface workflow]    ──►  [agent core workflow]   ──►  [sub-agent workflows]
   ("the shell")                   ("the brain")                ("specialists")

   - Trigger from the surface       - Stateless                  - One narrow domain each
   - Anti-loop filter               - chatInput + threadId       - chatInput only
   - Routing / event types          - Memory keyed on threadId   - Their own tools + model
   - Loading + error UX             - Tools, sub-agents
   - Render the reply
```

Examples in [examples/slack-router.json](examples/slack-router.json), [examples/agent-core.json](examples/agent-core.json), [examples/notion-ideas-subagent.json](examples/notion-ideas-subagent.json).

## The shell

Receives chat events, decides whether to respond, manages UX, calls the core, renders the reply. No reasoning, no LLM.

### Anti-loop filter (load-bearing)

The bot's own messages re-trigger the workflow. Slack, Discord, Teams all emit events for posts the bot itself made. Without filtering, every reply triggers another run, then another, until rate limits or n8n concurrency stops it.

**Prefer trigger-level filtering when the trigger supports it.** Some triggers expose user-ID filtering in their options so the loop breaks before any downstream node fires. Semantics differ per surface, verify against the version you're on:

- **Slack** (`n8n-nodes-base.slackTrigger`): `options.userIds` is an **exclusion list**. Listed users are dropped before the workflow runs. Put the bot's user ID here for anti-loop. Verified in the trigger source: the handler returns early `if (userIds.includes(event.user))`.
- **Telegram** (`n8n-nodes-base.telegramTrigger`): `additionalFields.userIds` is an **inclusion / allowlist** (only listed users fire the trigger). Not a bot-exclusion filter, but useful for restricting a private bot to specific human users; bot loops are usually a non-issue on Telegram since bots don't see their own messages by default. Pair with `additionalFields.chatIds` for scope.
- **Discord, Teams**: no native user-level trigger filter. The downstream filter node below is the only option.

Slack trigger-level example:

```ts
const slackTrigger = trigger({
    type: 'n8n-nodes-base.slackTrigger',
    config: {
        parameters: {
            trigger: ['message'],
            channelId: { __rl: true, mode: 'list', value: '<CHANNEL_ID>' },
            options: {
                userIds: '={{ ["<BOT_USER_ID>"] }}',
            },
        },
    },
})
```

`channelId` (`getChannels`) and the exclusion `options.userIds` (`getUsers`) are lookup values: resolve real IDs via `explore_node_resources` instead of hardcoding the placeholders. RLC values in this skill's `examples/*.json` are instance-specific, re-resolve before reuse.

When the trigger filters at its own boundary, you don't need a separate filter node.

**When the trigger doesn't expose a usable exclusion filter** (currently Teams, plus Discord via community nodes that vary), the first node after the trigger must filter the bot's own user ID out:

```ts
const filterBot = node({
    type: 'n8n-nodes-base.filter',
    config: {
        parameters: {
            conditions: {
                conditions: [
                    {
                        leftValue: '={{ $json.user }}',
                        rightValue: '<BOT_USER_ID>',
                        operator: { type: 'string', operation: 'notEquals' },
                    },
                ],
            },
        },
    },
})
```

The bot user ID is the API ID from your bot's auth (Slack `bot_user_id`, Discord application ID, Teams `botId`).

### Switch on event type and identity

The same trigger fires for messages, reactions, threads, mentions, slash commands, button clicks. One Switch right after the bot-loop filter routes each event to the right handler. The shell stays thin: it classifies the event and dispatches, and the actual work happens in dedicated sub-workflows per case.

Example for a Slack assistant (your shape will vary by what you support):

```
Switch case                              Goes to
──────────────────────────────────────────────────────────────────────────
"owner message"               ──►  Execute Workflow: agent-core
"owner reaction"              ──►  no-op (or Execute Workflow: reaction-handler)
"unknown user"                ──►  Send canned reply (or 4xx-shaped equivalent)
"slash command: /summary"     ──►  Execute Workflow: summary-command
"slash command: /search"      ──►  Execute Workflow: search-command
"button click"                ──►  Execute Workflow: interaction-handler
```

Each case has its own sub-workflow because the routing decision (what kind of event is this) and the work (run an agent, run a one-off tool, post a follow-up) are different concerns and often need different models, timeouts, or memory shapes. Adding a new slash command or button means adding one Switch output and one sub-workflow, not a new top-level workflow with its own trigger.

Slack-specific routing notes (payload shapes evolve on both Slack's side and n8n's, so verify field paths against a live event before relying on the exact shape):

- **Reactions and mentions** typically flow through the Slack Trigger as Events API events (`reaction_added`, `app_mention`).
- **Slash commands and Block Kit button clicks generally don't come through the Slack Trigger**, since Slack delivers those to separate Request URLs (Slash Command Request URL and Interactivity Request URL) outside the Events API. Two ways to bring them into the shell:
    - Add a **Webhook node** as a second trigger in the same shell, configured as Slack's Request URL for that case. The shell then has Slack Trigger + Webhook(s) feeding the same Switch.
    - Use a community Socket Mode node (e.g., `@mbakgun/n8n-nodes-slack-socket-mode`) that consolidates messages, slash commands, and interactivity into a single trigger.
- For matching, slash commands generally expose a `command` field, and Block Kit interactions arrive with `type === 'block_actions'` and an `actions` array (commonly routed by `actions[0].action_id`). These are reasonable starting points, but check the captured payload in your version before hardcoding.

### Loading-state UX

Users assume nothing is happening if they don't see acknowledgement. Pattern: **add a loading indicator before the agent call, remove it on every exit path, including error**.

```
[Trigger] → [Filter bot] → [Switch]
   → (owner message)
   → [Add loading reaction]                        # :chatgpt:, :spinner:, etc.
   → [Execute Workflow: Agent core]
        onError: 'continueErrorOutput'
        ├── (success) → [Remove reaction] → [Send reply]
        └── (error)   → [Remove reaction] → [Send error message with link]
```

The error path is the easy one to forget. Without it, the loading indicator sits forever and the user thinks the bot is still working. `onError: 'continueErrorOutput'` on the `Execute Workflow` node enables the second branch (see `n8n-error-handling-official` `references/NODE_ERROR_OUTPUTS.md`).

For Slack: `slack` node with `resource: 'reaction'`, `operation: 'add'` and `'remove'`. For Discord/Telegram, typing indicators are time-bounded, so for long agents, you could, for instance, send a placeholder message and edit it instead.

### Threading as session continuity

Use the surface's thread primitive as the memory `sessionKey`:

```ts
workflowInputs: {
    value: {
        chatInput: '={{ $("Filter bot").item.json.text }}',
        threadId: '={{ $("Filter bot").item.json.thread_ts || $("Filter bot").item.json.ts }}',
    },
}
```

`thread_ts || ts` is the canonical Slack idiom: replies in a thread carry `thread_ts` referencing the parent, and the parent itself only has `ts`. Falling back to `ts` means the parent message becomes the session key for the thread it starts. Each thread is a fresh conversation, and memory doesn't leak across unrelated threads.

User ID, channel ID, and workspace ID alone are wrong: they cross conversations.

When sending the reply, target the same thread by setting `otherOptions.thread_ts.replyValues.thread_ts` to the same `thread_ts || ts`. Without it, replies go to the channel root and the thread context is lost.

### Error UX: surface, don't hang

The error branch sends a short message with a link to the failed execution:

```
There was a workflow error. https://<n8n-host>/workflow/<id>/executions/{{ $execution.id }}
```

`$execution.id` is the live execution ID at the time the error fires. Parameterize the host if you ship across environments.

## The agent core

A sub-workflow with two declared inputs: `chatInput` (the user's message) and `threadId` (the surface's thread/session ID). Returns the agent's final output: string, structured object, or surface-specific envelope (Block Kit, adaptive card).

The only chat-specific wiring not covered in `MEMORY.md` is plumbing `threadId` straight to `sessionKey`:

```ts
sessionIdType: 'customKey',
sessionKey: '={{ $json.threadId }}',
```

`threadId` flows trigger → (any pass-through nodes) → memory. Don't put it behind `fromAi` (covered in `SUBWORKFLOW_AS_TOOL.md`).

Per-execution context (user identity, attached files) goes in a Set node before the agent and gets templated into the system prompt, pattern in `SYSTEM_PROMPT.md` "File handling injection" and "Template + variables." Don't add a Set node speculatively for context that isn't varying yet. Inline in `systemMessage` is fine until reuse is real.

For Slack Block Kit, Discord embeds, or Teams adaptive cards, pair the agent with `outputParserStructured` (see `STRUCTURED_OUTPUT.md`). The general guidance to default to `schemaType: 'manual'` with a real JSON Schema applies even more strongly here: Block Kit and adaptive cards lean heavily on `oneOf` union types across block kinds, plus enums for fields like `style` and per-block constraints, none of which `jsonSchemaExample` can express. Examples will produce confidently-wrong block trees that the surface rejects.

## Sub-agents (agent as a tool)

A sub-agent is its own workflow with its own Agent node, called from the router agent via `toolWorkflow`. Use it when:

- The domain has a schema or enum set the router shouldn't carry (Notion DB properties, Linear labels, CRM fields).
- The domain has 5+ tools that would clutter the router's tool list.
- The capability is reused across more than one router agent.
- The domain warrants a different (cheaper, faster) model than the router.

The contract is **stateless**. The router sends the full request in `chatInput`, with no shared memory and no implicit context. Reinforce in both the tool description (router-side) AND the sub-agent's system prompt (callee-side):

> IMPORTANT: This tool is stateless. Send all relevant context in a single message.
> If you need to create an entry, include ALL required fields upfront.

Without that, the router assumes implicit context and the sub-agent guesses.

For everything else about wiring sub-workflows as tools (the `toolWorkflow` node, `fromAi` mapping, plumbed-vs-agent-filled values, return shapes), see `SUBWORKFLOW_AS_TOOL.md`.

### Fresh schema injection

When the domain schema can change at runtime (Notion DB property options evolve, Linear teams add labels), refetch on every sub-agent call instead of hardcoding it in the system prompt:

```
[Execute Workflow Trigger]
   ↓
[Notion: Get Database]                       # fetches the schema
   ↓
[Agent]                                       # system prompt template includes:
    ## Database Schema
    {{ $('Get a database').first().json.properties.toJsonString() }}
```

One extra API call per invocation, and in exchange the sub-agent never returns "that property doesn't exist" because the prompt is stale. Worth it for low-call-volume chat assistants. For high-volume hot paths, cache the schema in a Data Table with a TTL.

## Worked example: a personal Slack assistant

Three workflows demonstrating the full pattern:

| Workflow | Role |
|---|---|
| [Slack router](examples/slack-router.json) | The shell. Bot-loop filter, event-type switch, loading reaction, error UX with execution link. |
| [Agent core](examples/agent-core.json) | Stateless agent. Memory keyed on `threadId`. Native tools (web search, deep research, calculator) plus two sub-agents. Block Kit output. |
| [Notion ideas sub-agent](examples/notion-ideas-subagent.json) | Specialist for a Notion ideas DB. Fetches schema fresh per call. Cheaper model (Claude Haiku 4.6). |

## Cross-references

- `TOOLS.md`: tool naming, descriptions, `fromAi()`.
- `SUBWORKFLOW_AS_TOOL.md`: the `toolWorkflow` shape and parameter mapping.
- `SYSTEM_PROMPT.md`: per-execution context, file injection, prompt storage.
- `STRUCTURED_OUTPUT.md`: parser config, autoFix, fixer model selection.
- `MEMORY.md`: memory types, `sessionKey` persistence options.
- `n8n-error-handling-official` `references/NODE_ERROR_OUTPUTS.md`: `onError: 'continueErrorOutput'`.
- `n8n-node-configuration-official` `references/COMMS_NODES.md`: Slack node parameter shapes.
- `n8n-binary-and-data-official` `references/AGENT_TOOL_BINARY.md`: receiving uploaded files and returning generated files. Read the "Surface-specific seams" section: every platform's file events and image rendering differ.

## Anti-patterns

| Anti-pattern | What goes wrong | Fix |
|---|---|---|
| No bot-user-ID filter at the top of the shell | Bot's own messages re-trigger the workflow, infinite loop | Prefer trigger-level filtering when available (Slack: `options.userIds` is an exclusion list, put the bot ID there). Otherwise filter on `$json.user !== '<BOT_USER_ID>'` as the first node after the trigger |
| Putting the bot's user ID in Telegram's `userIds` expecting exclusion semantics | Telegram's `userIds` is an **allowlist**, not an exclusion list. Only the bot would fire the trigger, which means no human messages get through. Workflow looks "fixed" until you realize it's been silent for hours | Telegram bots don't see their own messages by default, so anti-loop usually isn't needed. If you need to restrict who can talk to the bot, use `userIds` as the allowlist of permitted humans, not as a place for the bot's ID |
| Loading indicator added but only removed on the success path | User sees the bot stuck "thinking" forever after any error | `onError: 'continueErrorOutput'` on the agent call, remove the indicator on both branches |
| Using user ID, channel ID, or workspace ID as the session key | Conversations cross threads inside the same channel | Use the surface's thread primitive (Slack `thread_ts || ts`, Discord thread ID, Teams reply ID) |
| Stuffing trigger + UX + agent + sub-agent tools into one workflow when the agent already has multi-surface, sub-agent, or reuse needs | Can't reuse across surfaces, UX leaks into reasoning, harder to test in isolation | Split into shell + core + sub-agents (but only once one of those needs is real, simple bots stay in one workflow) |
| Sub-agent that reads or writes shared memory | Caller can't reason about behavior, not safely retryable | Sub-agents are stateless, full context goes in `chatInput` |
| Hardcoding domain schema (Notion properties, Linear labels) in a sub-agent's system prompt | Schema rots, sub-agent picks invalid options weeks later | Re-fetch the schema at the start of the sub-agent and template it into the system prompt at runtime |
| Set-before-agent context injection for static text "in case I want to reuse it" | Extra node, no actual reuse, more places to update | Inline in `systemMessage` until reuse is real, use Set only for per-execution variability |
| Calling the agent core synchronously without an error UX | Worker fails, user sees nothing, debug requires opening n8n | Error branch surfaces a short message with a link to the failed execution |
