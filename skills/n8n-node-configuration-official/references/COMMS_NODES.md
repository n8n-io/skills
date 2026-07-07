# Comms nodes: Slack, Gmail, Discord, email

Communication nodes share patterns. The exact field shapes (param names, fixedCollection structures, value enums) shift across versions; `get_node_types` is canonical. This file covers security rules, decisions, and gotchas not in the type def.

## Always credentials, never tokens

Per `n8n-credentials-and-security-official`: comms tokens go in credentials, never in node text fields.

If a user pastes a bot token in chat, follow the credential-creation flow in `n8n-credentials-and-security-official`. Don't put it in a node.

## Append n8n Attribution
Most comm nodes have append n8n attribution enabled by default. 
Users typically want to remove it, so remove attribution by default.

## Slack

### Operation values can surprise you

The display name and the internal value don't always match. "Send a message" → `operation: 'post'` (not `'send'`). Always inspect via `get_node_types([{ name: 'slack', resource: 'message', operation: '...' }])`.

### `select`: channel vs DM

`select` determines whether the next field is `channelId` or `user`. Don't mix; only one applies per `select` value. Both are `@searchListMethod` lookups (`getChannels` / `getUsers`): after `get_node_types`, resolve the real ID via `explore_node_resources`.

### Block Kit messages

For rich messages, set `messageType: 'block'`. The block content is a JSON **string** (the JSON output from Slack's Block Kit Builder), not a nested n8n object. The `text` field becomes the fallback notification text.

**`blocksUi` must be wrapped as `{ "blocks": [...] }`, not the bare array.** The Slack node accepts the bare array silently: the request goes through, but the rich content drops and the message posts as plain `text` (or empty if `text` isn't set). No node error, no validation warning. The wrap matches Slack's `chat.postMessage` payload shape; the node forwards it directly.

Build the envelope as a single expression that returns a real object with the array as a live array value, not a stringified one. Reference the upstream by name (per `n8n-expressions-official` non-negotiable #1), not `$json`:

```
={{ { "blocks": $('Agent').item.json.output.blocks } }}
```

Don't reach for string-interpolation hybrids like `={ "blocks": {{ $('Agent').item.json.output.blocks.toJsonString() }} }`. They work in some n8n versions, but stringifying-then-reparsing is fragile (double-escaping, unicode, large payloads) where the object form just hands the node the structure directly.

### Threading: `thread_ts` is required for in-thread replies

Without `thread_ts`, the "reply" posts as a top-level channel message. Inspect via `get_node_types` for where the field sits, it's not under `otherOptions` like older docs suggest.

`thread_ts` is the timestamp of the message you're replying to. `reply_broadcast: true` makes the reply visible in the main channel.

## Gmail

### Operation values: "Get Many" → `'getAll'`

Not `'getMany'`. Display name vs internal value mismatch. Common operations: `'send'` (default), `'reply'`, `'getAll'`, `'addLabels'`, `'removeLabels'`, `'get'`, `'delete'`, `'markAsRead'`, `'markAsUnread'`. `addLabels`/`removeLabels` take a `labelIds` load-options field: resolve real label IDs via `explore_node_resources` (`loadOptions`).

### What lives at top level vs under `options`

Top-level: `sendTo`, `subject`, `emailType` (`'text'` | `'html'`), `message`. Under `options`: `bccList`, `ccList`, `replyTo`, `senderName`, `attachmentsUi`. Easy to misplace.

Build HTML directly in `message` via expression. Don't construct it in an upstream Set node (per `n8n-expressions-official` non-negotiable).

### Multi-recipient

`sendTo` accepts comma-separated recipients. BCC and CC use the same comma-separated convention via `options.bccList` / `options.ccList`.

### Attachments

Attachments reference binary properties on the input item (under `options.attachmentsUi`). See `n8n-binary-and-data-official` for the upstream binary handling.

## Discord

### Webhook vs OAuth

`authentication` is the discriminator: `'webhook'` (simpler, posts to one channel via Discord webhook URL) or `'oAuth2'` (full bot capabilities: DMs, multi-channel).

For "post to a channel," use webhook. Use OAuth only for bot-level features. 

### Embeds

Discord rich embeds use a fixedCollection under `embeds.values[]`. Each embed supports `inputMethod: 'fields'` (structured) or `'json'` (raw JSON). Color is an n8n `type: 'color'` field; pass a hex string and the node converts to the decimal Discord's API expects.

### `emailFormat` is the discriminator

`'text'`, `'html'`, or `'both'`. Determines whether `text`, `html`, or both fields appear. Top-level: `fromEmail`, `toEmail`, `subject`, `emailFormat`, `text`, `html`. Under `options`: `replyTo`, `ccEmail`, `bccEmail`, `attachments`. Different from Gmail's `bccList`/`ccList` naming.

### Email as a fallback

When a service-specific node has issues (rate limit, quota, regional outage), SMTP is a good fallback. Configure both, and pick at runtime via flag or status check.

## Telegram

Bot tokens via `telegramApi`. Each bot can only send to chats it's been added to.

### `parse_mode` is snake_case

Not `parseMode`. Lives under `additionalFields`. Options: `'Markdown'` (legacy), `'MarkdownV2'`, `'HTML'` (default).

MarkdownV2 has stricter escaping than V1: `_`, `*`, `[`, `]` and others need escaping or the message fails. Switch to HTML mode if escape rules become painful.

## Common patterns across comms nodes

### Idempotency

For workflows that can re-fire (retries, re-runs), include an idempotency check. Track sent messages in a Data Table (see `n8n-binary-and-data-official`'s `DATA_TABLES.md`). Check before sending, skip if already sent recently.

### Rate limits

Comms providers (Gmail, Slack, Discord, Teams) have rate limits. Configure node-level retry on any production node so a transient 429 self-heals: `retryOnFail: true` plus a `waitBetweenTries` per the provider's tolerance. For high-volume, use `Loop Over Items` with `Wait` between batches (see `n8n-loops-official` `LOOP_OVER_ITEMS.md`).

### Personalization via expressions

Build the message body directly in the comms node's body field, not in an upstream Set node. Same `n8n-expressions-official` non-negotiable.
