# Human review for agent tools

Human review gates a tool behind explicit human approval. Without approval, the wrapped tool does not run, regardless of how confident the agent is. The default safety pattern for any agent tool with user-visible side effects.

n8n docs and node names use **HITL**, **human-in-the-loop**, and **Human Review** for the same concept, and the review tool nodes are named accordingly (`slackHitlTool`, `discordHitlTool`, etc.).

## Topology

The review node sits between the wrapped tool and the agent on the `ai_tool` connection:

```
[wrapped tool]  --ai_tool-->  [review node]  --ai_tool-->  [Agent]
```

- **The agent doesn't know the review node is there.** It sees the wrapped tool by the wrapped tool's name, description, and parameter schema. The review node is a transparent intercept on the execution path.
- When the agent calls the wrapped tool, the review node intercepts: it collects the parameters the agent built, pauses, sends an approval prompt to a human via the configured platform, and only on approval does the wrapped tool actually run with those parameters.

### SDK syntax

Wire the wrapped tool into the review tool's `subnodes.tools` array. The agent registers the review tool in its own `subnodes.tools`. The SDK auto-resolves both `ai_tool` connections in the saved workflow JSON.

```ts
const refundTool = tool({
  type: 'n8n-nodes-base.stripeTool',
  config: {
    name: 'Refund customer',
    parameters: { resource: 'charge', operation: 'update', /* ... */ },
    credentials: { stripeApi: newCredential('Stripe') },
  },
});

const slackReview = tool({
  type: 'n8n-nodes-base.slackHitlTool',
  version: 2.4,
  config: {
    name: 'Slack approval',
    parameters: { message: '...', user: { __rl: true, mode: 'list', value: '...' }, approvalOptions, options }, // resolve user/channel IDs via explore_node_resources (getUsers/getChannels)
    credentials: { slackApi: newCredential('Slack') },
    subnodes: { tools: [refundTool] },  // wrapped tools go here
  },
});

const agent = node({
  type: '@n8n/n8n-nodes-langchain.agent',
  config: { /* ... */ },
  subnodes: { model, tools: [slackReview] },
});
```

Don't use `.to()` to wire the wrapped tool into the review tool: `.to()` creates a `main` connection, and `validate_workflow` flags the wrapped tool as `DISCONNECTED_NODE`. The wrapped-tool-into-review wiring happens through `subnodes.tools` only.

## Tell the agent the review is there

Because the agent doesn't see the review node, it doesn't know its tool is gated. Models with safety priors hedge on destructive-looking tools (send, delete, refund, charge) by default: they refuse, ask the user for confirmation first, or pick a less-direct option. With human review wrapping the tool, that caution is doubled up: the model self-censors AND a human reviews. Sometimes the model never even gets to the review step because it talked itself out of trying.

If you see the agent over-hedging on the wrapped tool (refusing to use it, asking the user for permission first, picking less-direct options), add a note to the **wrapped tool's description** that the review exists. Per the modular-prompt principle (see `SYSTEM_PROMPT.md`), tool-specific behavior belongs with the tool so it travels across agents and stays out of an already-busy system prompt.

Example addition to the tool description:

> "This tool is gated by a human review step. Use it freely when relevant. A human will see the exact parameters and approve before anything is sent. Don't ask the user for confirmation first."

Don't pre-emptively add this to every wrapped tool. Many agents already use the tool freely without it. Deploy when the symptom (hedging, refusing, talking itself out of trying) actually shows up. Concrete payoff when it does apply: faster turn-taking (one approval click vs back-and-forth confirmation messages), better tool selection (the model isn't artificially de-prioritizing the gated tool), and the reviewer sees the model's actual decisions rather than its hedging.

## When to default to human review

- **Sends, pays, refunds, account changes.** Anything user-visible and hard to roll back.
- **The approver is different from the chatter.** Customer triggers a workflow that asks support staff to approve the refund. Customer doesn't see the approval, support does.
- **Non-chat triggers.** Order received, form submitted, schedule fired. The action is taken on someone's behalf, and a person approves before it runs.
- **Production-bound agent tools** where the cost of a wrong call (money, customer trust, reputation) outweighs the cost of a one-step delay.

Skip review when the tool is read-only, idempotent and cheap to undo, or when the deployment is internal and exploratory with mocked services.

## Available review tool nodes

| Node | When to use |
|---|---|
| `n8n-nodes-base.slackHitlTool` | Approver is on Slack (multi-channel pattern: chatter elsewhere, support staff approves in Slack) |
| `n8n-nodes-base.discordHitlTool` | Approver is on Discord |
| `n8n-nodes-base.telegramHitlTool` | Approver is on Telegram |
| `n8n-nodes-base.gmailHitlTool` | Approval via Gmail |
| `n8n-nodes-base.emailSendHitlTool` | Approval via generic SMTP email |
| `n8n-nodes-base.googleChatHitlTool` | Approval in Google Chat |
| `n8n-nodes-base.microsoftOutlookHitlTool` | Approval via Outlook email |

More platforms are added over time. Verify what's available on the target instance with `search_nodes({ queries: ['hitl'] })`.

## Response types

`responseType` chooses the response shape the human sees:

- **`approval`**: button-based approve / disapprove. Sub-configured via `approvalOptions.values.approvalType`:
  - `'single'` (the default): one button (Approve only). Use when disapproval isn't a meaningful choice. The approver either acts or ignores.
  - `'double'`: two buttons (Approve / Disapprove). For actions where Disapprove needs to be a loud, recordable choice.
- **`freeText`** (Slack / Discord / Telegram / Gmail / etc.): the human types a free-form response. Useful when the agent is genuinely asking a question and any answer is valid.
- **`customForm`** (every variant): a multi-field form supporting text, dropdown, radio, checkbox, and file inputs. The human fills in the form before the wrapped tool runs with those values. **This is the practical answer to "editable parameters"**: define a form whose fields match the wrapped tool's parameters and the human can override what the agent picked.

A two-button "semantic choice" (e.g., "Schedule for today" / "Schedule for tomorrow") is NOT a separate response type. Use `responseType: 'approval'` with `approvalType: 'double'` and customize `approveLabel` / `disapproveLabel`.

## Wait timeout

`options.limitWaitTime` (in seconds) bounds how long the workflow pauses for approval before erroring out. Default is 45 minutes. Set it explicitly on production workflows. Without setting it, paused executions can sit indefinitely if approvers don't act, and the queue piles up.

## Approval message content

Show the **actual parameters the wrapped tool will receive**. The model picked them, and the human is approving the literal call.

### Reference parameters via `$tool.parameters.<name>`

```
The agent wants to refund {{ $tool.parameters.amount }} to {{ $tool.parameters.customerId }}.
Reason: {{ $tool.parameters.reason }}.
```

`$tool.name` is the wrapped tool's display name. `$tool.parameters` is the full object the agent built.

### Iterate over all parameters

So that adding a parameter to the wrapped tool doesn't silently leave it out of the approval message:

```
The agent wants to call {{ $tool.name }}:
{{
  $tool.parameters.keys()
    .map(param => `${param}: ${$tool.parameters[param]}\n`)
    .join('')
}}
```

Drop this into the message field and any future parameter on the wrapped tool shows up automatically.

### Don't fill the approval message via `fromAi()`

`fromAi()` asks the model to produce a value, including, if you let it, the approval text itself. That means the human approves a model-paraphrased description rather than the literal parameters about to be sent. Defeats the point of human review.

```ts
// WRONG
parameters: {
  message: expr("{{ $fromAI('approvalText', 'describe the action for approval') }}"),
}

// RIGHT
parameters: {
  message: expr("Refund {{ $tool.parameters.amount }} to {{ $tool.parameters.customerId }}?"),
}
```

### Customize button labels with the actual values

Embed values in button text so the click is as clear as possible:

```ts
approvalOptions: {
  values: {
    approvalType: 'double',
    approveLabel: expr("Approve ${{ $tool.parameters.amount }} refund"),
    disapproveLabel: 'Cancel',
  }
}
```

A button that says "Approve $50 refund" is unambiguous. A button that says "Approve" alone is not. Default disapprove label is "Decline" if you don't override it.

`slackHitlTool` also exposes `buttonApprovalStyle` and `buttonDisapprovalStyle` (`'primary' | 'secondary'`) for visual emphasis on Slack's button styling.

## Multi-channel pattern: approver isn't the chatter

A common production pattern: customer chats with an agent on a website (or via email, order trigger, form submission), and support staff approves sensitive actions in Slack.

```
[customer chat / order trigger]
    -> [Agent]
        -> [Slack review tool]  ->  [refund / cancel / escalate tool]
```

The customer never sees the Slack channel. The Slack review message routes via `slackHitlTool.parameters.user`, a resource locator with a `select` parent (`'channel' | 'user'`). The user branch uses `mode: 'list' | 'id' | 'username'` plus a value, and the channel branch uses `channelId`. On approval, the wrapped tool fires, and the agent's response goes back to the customer via the original chat path.

This pattern also works without any chat at all: trigger could be a webhook, schedule, form, or queue. The review tool is the only human-facing surface.

## UI quirk: test data autofill

When building a review tool, click "Approve" once on the test execution in the canvas editor. n8n autofills the test data so subsequent runs work without manual input. Easy to miss, and new builders often think the tool is broken because the `$tool.parameters.<name>` is highlighted red since there is no test data.

## Editable parameters: use customForm

For "I want to approve, but at $40 instead of $50" workflows, use `responseType: 'customForm'` (see Response types above). The human fills in a multi-field form whose values feed the wrapped tool, so they can override what the agent picked. Available on every Hitl variant.

Don't try to build editable approvals on top of the `approval` response type. The form mode is the supported path.

> Note: the form mode is not an ideal UX and is reported feeling like a work around. Keep that in mind. Sometimes it may be better to have the user respond with a chat to decline with changes. 

## Anti-patterns

| Anti-pattern | What goes wrong | Fix |
|---|---|---|
| Tool that mutates user-visible state without human review | Agent fires irreversible action on a wrong inference | Wrap with the right review tool node |
| Approval message via `fromAi()` | You approve a paraphrase, not the literal call | Use `$tool.parameters.<name>` |
| "Approve" button with no context in the label | Approver clicks without seeing what they're approving | Embed actual values: `Approve {{ $tool.parameters.amount }}` |
| Review on a channel the approver doesn't actively monitor | Tool sits indefinitely, executions pile up | Pick a channel approvers watch, consider TTL / fallback patterns |
