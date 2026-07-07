# Agent memory

Memory is wired as a sub-node on the Agent. Without it, every invocation is stateless. With it, the agent holds a conversation across turns (and across executions, depending on type) keyed by a `sessionId`.

n8n memory node availability shifts between versions, so check what's installed on the target instance with `search_nodes({ queries: ['memory'] })`.

## The non-negotiables

1. **Plumb a stable key through.** Memory buckets by whatever expression you bind to `sessionKey`. The chat trigger fills `sessionId` automatically. For other triggers, derive a stable identifier (Slack `thread_ts`, a webhook conversation ID, a generated UUID, a multi-tenant composite) and forward it to memory and any session-keyed tools. Without consistency across the same conversation, memory never matches.
2. **Default to `memoryBufferWindow`.** It persists across executions via n8n's internal store, keyed on whatever you bind to `sessionKey`, and is the right choice for nearly every chat agent. Reach for `memoryPostgres` / `memoryRedis` only when memory needs to be queried or read **outside** the agent (your own UI displaying chat history, analytics, sharing memory across systems).


## The memory types

### `memoryBufferWindow`

In-execution memory of the last N turns. The default for "remember the last few exchanges in this conversation."

```ts
const bufferMemory = memory({
    type: '@n8n/n8n-nodes-langchain.memoryBufferWindow',
    config: {
        parameters: {
            contextWindowLength: 50,
        },
    },
})
```

`contextWindowLength` is the number of exchanges retained. **The default is 5, which is very low for modern chat expectations**, where users typically assume a conversation feels close to endless. 50 is a reasonable starting point for most chat agents. Higher = more context, more tokens.

**Messages past the window are removed from memory entirely.** Once the buffer fills, the oldest exchanges are dropped and the agent can't recall, search, or know they ever existed. If a user said something 60 turns ago and the window is 50, that information is gone from the agent's perspective. For recall beyond the window, raise `contextWindowLength`, or persist key facts in a Data Table that's read and injected into the system prompt.

**Persistence:** keeps the last N messages per memory key and persists across executions via n8n's internal store. With `sessionIdType: 'customKey'`, you bind the key to any expression: `{{ $json.sessionId }}` from a chat trigger, a Slack `thread_ts`, a multi-tenant composite, etc. Multiple users / threads / contexts each get their own memory bucket. The "window" is the sliding cap on how many messages stay in context, not a scope on persistence.

**Right for:** the default for chat memory. Nearly every user-facing chat agent.

### Postgres / Redis stores (when memory needs to be readable outside the agent)

Reach for these when memory needs to be queried or read **outside** the agent: displaying conversation history in your own UI, analytics on past chats, sharing memory across systems, or migrating to a different n8n instance cleanly. Not necessary just to make chat survive across executions, since `memoryBufferWindow` already does that.

```ts
const postgresMemory = memory({
    type: '@n8n/n8n-nodes-langchain.memoryPostgresChat',
    config: {
        parameters: {
            sessionIdType: 'customKey',
            sessionKey: '={{ $json.sessionId }}',
        },
        // ...connection config via credentials
    },
})
```

**Right for:** chat history exposed to non-agent code (your own UI, analytics, multi-system queries).

**Wrong for:** the default chat agent case. `memoryBufferWindow` is the cleaner pick.

## Custom memory patterns (Memory Manager)

Most agents don't need this. The default `memoryBufferWindow` with a sensible `contextWindowLength` covers the vast majority of chat use cases. But when a fixed window isn't enough, the `Chat Memory Manager` node (`@n8n/n8n-nodes-langchain.memoryManager`) is a powerful lever for building custom patterns on top of any memory backend.

The node operates against any wired memory sub-node (BufferWindow, Postgres, Redis, etc.) and exposes three modes:

- **`load`** (default): read the current memory contents into the workflow. Useful for inspection, branching on size, or feeding contents into a summarization step.
- **`insert`**: append a message to memory. An optional `hideFromUI` flag covers messages that should affect the agent but not show in the chat UI.
- **`delete`**: remove some or all messages from memory.

### Pattern: rolling summarization

When a conversation runs long and you want the agent to retain the gist of older turns instead of dropping them entirely past the window:

1. After each turn, `load` the buffer contents.
2. If the buffer is approaching the cap, route to a summarizer branch (otherwise no-op).
3. Run the older turns through an LLM that produces a concise summary.
4. `delete` everything in the buffer.
5. `insert` the summary back as a single message, plus optionally the most recent few turns to keep continuity.

The agent now sees `[summary of turns 1-40] + [most recent 5 turns]` instead of `[turns 1-50]`, paying for far fewer input tokens while still having access to long-history context.

### Other patterns built the same way

- **Prune by relevance.** `load`, filter messages, `delete`, then `insert` only the ones worth keeping.
- **Inject runtime system facts.** `insert` with `hideFromUI: true` for facts the agent should know but the user shouldn't see in the transcript.
- **Reset on command.** `delete` everything when a "/clear" command (or equivalent) fires.

These are plausible patterns, but the Memory Manager node is more recent than the rest of n8n's memory tooling. Verify the modes you intend to use against your installed version before relying on them in production.

## Session ID handling

Where the session ID comes from depends on the trigger:

### Chat Trigger

Sets `sessionId` automatically. Wire it:

- Memory node: `sessionKey: '={{ $('Chat Trigger').first().json.sessionId }}'`
- Tools: `sessionId: '={{ $('Chat Trigger').first().json.sessionId }}'` (NOT through `fromAi`)
- Storage keying: derive bucket keys / file names from sessionId for trivial per-session cleanup

### Webhook trigger

You manage it:

- Caller passes a header or body field (`body.sessionId`), and you forward it.
- Or issue a session ID on first call, return it, expect callers to pass it back.

Either way, the session ID must be consistent across the whole conversation, including across reconnections.

### Manual / scheduled

Usually no session. Use a stable identifier per "conversation" if one exists (Slack thread ID, ticket ID), otherwise memory adds nothing and should be omitted.

## Memory and tools

When a tool is invoked, the tool's sub-workflow does NOT see conversation memory. Memory is the agent's context, not the tool's input. Pass needed context through `fromAi` parameters explicitly.

For tools that need session-keyed state, pass `sessionId` and have the tool look up state from a Data Table or storage keyed by session.

## Memory and binary

Memory stores text turns. Binary uploaded mid-conversation is NOT in memory. It's in the chat trigger's `files[]` for that turn's input.

If the agent should remember "the user uploaded a file last turn":

- The text-side memory captures that "the user mentioned uploading a file."
- To actually USE the file in a later tool call, it must still be in storage (per `n8n-binary-and-data-official` `AGENT_TOOL_BINARY.md`) and the storage key must be in THAT turn's system prompt.

In practice, inject the session's file inventory into the system prompt every turn (loaded by sessionId).

## Common mistakes

- **Hardcoding `sessionId: 'default'`.** All conversations share one session. Memory contents become meaningless.
- **Different sessionId on memory vs tools.** Memory keys on one, tools on another. Memory looks right but tools can't find related state.
- **Using `memoryBuffer` (unbounded) for chat.** Token cost grows until timeout. Use BufferWindow with a sane limit.
- **Adding memory when there's no session.** A "summarize this article" workflow doesn't need memory.
- **Expecting tools to see memory.** Tools see only their `fromAi` parameters and plumbed-in context.
- **Drift between the chat surface and memory.** If anything posts to the conversation outside the agent (a scheduled workflow replies in the Slack thread, a human writes directly, another workflow injects a message), the surface and the agent's memory diverge. The agent then operates on an incomplete view and will contradict or ignore messages it can't see. Whatever shows up in the user-facing surface must also be `insert`ed into memory via Memory Manager (or the equivalent path for your backend), so the workflow logic stays in sync with what the user can see.

## Operational notes

- **Memory size affects token cost.** A 15-turn buffer of 200-token messages is 3000 tokens of input every turn before the user's input. Plan for it.
- **Rate limits.** A model that's hit a rate limit fails mid-conversation, and memory holds everything until then. After resolving, the next turn picks up (assuming session-id continuity).
- **Concurrent sessions.** Persistent backends key on sessionId, so concurrent conversations don't interfere. Verify with two simultaneous tests.

## Cross-references

- For where the agent fits in the bigger picture: parent `SKILL.md`.
- For passing session-keyed state into tools: `SUBWORKFLOW_AS_TOOL.md`.
- For session-keyed file storage: `n8n-binary-and-data-official` `references/AGENT_TOOL_BINARY.md`.
