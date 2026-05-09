# n8n ChatHub

ChatHub is n8n's built-in chat interface, available in the sidebar starting in n8n 2.5+. It's a chat surface for talking to agents you've built (or to bare LLM provider models) without leaving n8n.

ChatHub usually isn't the production chat surface (Slack bots and custom UIs are more common), but it's the lowest-friction chat path n8n ships: easiest to set up, no credentials required, and the only built-in chat surface outside the canvas test UI. Tight execution-debug loop on top. Particularly well suited for demos and starting quick.

## When to use ChatHub vs other chat surfaces

| Surface | Use when |
|---|---|
| **ChatHub** | Internal users, you want them to chat with agents inside n8n, tight execution-debug loop matters |
| **Slack / Discord / Teams bots** | External users or distributed teams, integrate with chat tools they already use |
| **Webhook + custom UI** | Customer-facing chat on your website, you control the UX |
| **Email / form / queue triggers** | Not chat, agent drives workflows from non-conversational triggers |

ChatHub doesn't replace the others. It's the right answer for "I want users in this n8n instance to chat with an agent and I don't want to build or integrate a UI."

## Two agent types

ChatHub has two agent types: **personal agents** (built directly in the ChatHub UI: pick a model, write a system prompt, attach tools, no workflow involved) and **workflow agents** (built as full n8n workflows with chat triggers, the focus of this skill).

<!-- TEMPORARY: update when new agent paradigm is released -->
The MCP can't create or edit personal agents, since they're a UI-only feature. If a user asks for one, surface that gap and direct them to the ChatHub UI.

For workflow agents, the recipe is: chat trigger with `availableInChat: true`, Agent node with model and memory, whatever orchestration makes sense, then publish the workflow. Once published, the agent appears in ChatHub under "Workflow agents" and each user message fires an execution.

## Response modes

The chat trigger's `responseMode` controls how the agent's output gets back to the chat:

- **`streaming`** (default when `availableInChat: true`): agent output streams to the chat as it generates. Lower latency-to-first-token, works only with text-out responses, doesn't work with human review tools.
- **`responseNodes`**: the workflow ends with a `Respond to Chat` node (`@n8n/n8n-nodes-langchain.chat`) that explicitly returns the response. Required for human review via `chatHitlTool`. Also required for **multi-agent workflows** (e.g. an agent council where several agents give different-perspective answers that a final synthesis agent combines), since with `streaming` every agent streams its own draft into the chat, leaking each perspective before synthesis. With `responseNodes`, only the explicit `Respond to Chat` at the end surfaces output. Slightly higher latency-to-first-token since the response only arrives after the workflow finishes.
- **`lastNode`** (default when `availableInChat: false`): the trigger uses the output of whatever the last node was. Less common in chat contexts.

When in doubt: `streaming` for plain single-agent Q&A, `responseNodes` for anything with a review step, multiple agents whose intermediate output shouldn't surface, post-agent processing, or non-text responses.

## Human review requirement: responseNodes mode + Respond to Chat

`chatHitlTool` (ChatHub's human-review tool) only works in `responseNodes` mode AND only when there's a `Respond to Chat` node after the Agent. Without both, approvals never reach the user.

```
[chatTrigger (responseMode: responseNodes, availableInChat: true)]
    -> [Agent]
        -> [chatHitlTool]
        -> [...other tools]
    -> [Respond to Chat]
```

See `HUMAN_REVIEW.md` for the broader review pattern.

## Chat-only user role

Cloud business / enterprise plans support a "chat-only" user role. They can use ChatHub but cannot see workflows, executions, or credentials. Useful for sharing an agent with non-technical team members without exposing the workflow plumbing.

Free / community / pro plans don't have this user role, so everyone with access can see the underlying workflows.

## Setup checklist for a workflow agent

1. Create a workflow.
2. Add a chat trigger, set `availableInChat: true`.
3. Add an Agent node with at least a `model` sub-node. Memory recommended.
4. Wire the trigger to the Agent.
5. If the workflow uses `chatHitlTool` or any non-streaming output: set chat trigger `responseMode: 'responseNodes'` and add a `Respond to Chat` node after the Agent.
6. Publish the workflow.
7. Open ChatHub from the sidebar. The agent appears under "Workflow agents."

## Anti-patterns

| Anti-pattern | What goes wrong | Fix |
|---|---|---|
| `chatHitlTool` with `streaming` response mode | Approval never surfaces, tool hangs | Switch to `responseNodes` mode and add Respond to Chat |
| Workflow agent without `availableInChat: true` on the trigger | Agent doesn't appear in ChatHub | Toggle `availableInChat` and republish |
| Skipping memory on a workflow agent | Each turn is stateless, users repeat themselves | Add a memory sub-node keyed on `sessionId` |
| Not setting a name or custom icon on the chat trigger | Agent shows up in ChatHub's picker with the default node name and a generic icon, hard to identify in a list of agents | Rename the chat trigger to something descriptive and set a custom icon, both surface in ChatHub |
