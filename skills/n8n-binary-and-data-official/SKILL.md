---
name: n8n-binary-and-data-official
description: Use when handling files, images, attachments, or binary data in n8n, OR when an AI agent needs to take a user-uploaded file as tool input or return a generated file. For Data Tables (schemas, dedup, persistent state), see the separate n8n-data-tables-official skill. Triggers on "file", "image", "PDF", "attachment", "binary", "upload", "download", chat trigger with files, agent tool that needs a file, vision/multimodal, or any handling of non-JSON file data.
---

# n8n Binary and Data

n8n handles two kinds of data: JSON (in `$json`) and binary (in `$binary`), flowing side-by-side. Binary has sharp edges around agent tools, storage, and display contexts (chat surfaces, message rendering).

For tabular storage (Data Tables), see the **`n8n-data-tables-official`** skill.

## Non-negotiables

1. **Binary is in `$binary`, not `$json`.** Don't read file contents from `$json`.
2. **Binary cannot cross the agent tool boundary in either direction.** Tool parameters are JSON only (via `fromAi()`), and tool results are JSON only. Pre-stage binary in storage and pass keys/URLs through JSON. The agent's `passthroughBinaryImages: true` lets the LLM *see* uploaded images for vision, but it does NOT enable tools to receive them. See `references/AGENT_TOOL_BINARY.md`.

## Strong defaults

- **Merge nodes keep binary in context.** When a side computation strips binary, merge it back rather than re-fetching. See `references/MERGE_FOR_CONTEXT.md`.

## Binary basics

In n8n, each item has two slots:

```ts
{
    json: { ... },           // your data
    binary: {                // your files
        data: {              // 'data' is the typical key; can be any name
            data: '<base64>',
            mimeType: 'application/pdf',
            fileName: 'invoice.pdf',
            fileExtension: 'pdf',
        },
    },
}
```

`$binary.<key>` reads the named property. Most file-handling nodes have a `binaryPropertyName` parameter, the key inside `$binary`.

### Setting binary

File-producing nodes (HTTP Request with binary response, Read Files, etc.) populate `$binary` automatically. To produce binary in a Code node:

```ts
return [{
    json: { ... },
    binary: {
        data: {
            data: Buffer.from(content).toString('base64'),
            mimeType: 'text/plain',
            fileName: 'output.txt',
        },
    },
}]
```

### Reading binary

```ts
// In a Code node
const buffer = await this.helpers.getBinaryDataBuffer(0, 'data')
const text = buffer.toString('utf-8')
```

Most workflows don't need to read binary directly. Pass it through to consumer nodes (email attachments, file uploads, etc.).

See `references/BINARY_BASICS.md` for more.

## Agent tool gymnastics

Agent tools (sub-workflows wired into a LangChain Agent, or workflows exposed as MCP tools) have a constraint: parameters and results are JSON, not binary. Affects both directions.

**Inbound (user uploads → tool consumes):** the chat trigger gives `files[]`. The agent can have `passthroughBinaryImages: true` for vision, but `fromAi()` can't pass binary to a tool. So:

1. Pre-stage uploaded files: hash a key, upload to private storage.
2. Inject the keys into the agent's system prompt: "Files passed in: [{originalFileName, fileName}]. Use EXACTLY the `fileName` field when calling tools."
3. The tool's `fromAi('imageName', '...', 'string')` receives the key. The sub-workflow downloads from storage.

**Outbound (tool produces → agent returns):** a tool generates a file. It can't return raw binary.

1. Generate binary internally.
2. Upload to storage, get back URL/key.
3. Return JSON: `{ ok: true, file_id: '...', url: '...' }`.
4. The agent embeds the URL in its response, or another tool fetches by key.

For the full pattern including the async-via-webhook variant for long-running tools, see `references/AGENT_TOOL_BINARY.md`.

## Merge for keeping binary in context

A JSON-only operation (Edit Fields, Code, IF) often strips binary from the item. To keep it:

```
[Source with binary] ─┬─→ [Edit Fields: transform JSON] ─┐
                      │                                    ├─→ [Merge: by position] ─→ [Email with attachment]
                      └─────────────────────────────────────┘
```

Merge combines the streams, and binary survives. See `references/MERGE_FOR_CONTEXT.md`.

## CDN requirement for chat surfaces

When a workflow generates an image and the user wants it embedded in a chat message (Slack, Discord, Teams, Telegram, embedded webhook chat, etc.):

- **Binary on the item isn't enough.** Chat surfaces don't read `$binary`; they render messages that reference images by URL (or via platform-specific file upload APIs).
- **The image must live somewhere a URL can fetch.** Upload to a CDN or object store first.
- **The user configures this storage.** Not built into n8n.

Common options span object storage (S3, R2, GCS, Azure Blob, Vercel Blob, Supabase Storage) and drive-style services (Dropbox, Google Drive, OneDrive, Box). Ask the user what they use rather than defaulting to S3.

See `references/CDN_REQUIREMENT.md`.

## Data Tables

For Data Tables, see the **`n8n-data-tables-official`** skill. Distinct surface with its own gotchas (default columns, no foreign keys, no JSON column type, manual-mapping UI quirk).

## Reference files

| File | Read when |
|---|---|
| `references/BINARY_BASICS.md` | First time handling binary, or reading/writing the `$binary` slot |
| `references/AGENT_TOOL_BINARY.md` | Agent tool needs a user-uploaded file, or produces a file (the boundary in either direction) |
| `references/MERGE_FOR_CONTEXT.md` | Binary disappears after a JSON transform and needs to re-attach |
| `references/CDN_REQUIREMENT.md` | Showing images in a chat surface or other places that need URL-referenced images |

## Anti-patterns

| Anti-pattern | What goes wrong | Fix |
|---|---|---|
| Trying to read file content from `$json` | Binary isn't in `$json` | Use `$binary` |
| Building an agent tool that returns binary directly | Tool output is JSON-only, so binary doesn't survive | Upload to storage, return key/URL in JSON (see `AGENT_TOOL_BINARY.md`) |
| Trying to pass uploaded chat files into a tool via `fromAi` | `fromAi` doesn't carry binary, so the tool gets nothing | Pre-stage uploads to storage, inject keys in the system prompt, and have the tool download by key |
| Setting `passthroughBinaryImages: true` and assuming tools can now see the file | The flag only affects what the LLM sees, not what tools receive | Still need the upload-and-pass-key pattern for tools |
| Losing binary after a JSON transform | The transform's output item doesn't have binary | Use Merge to combine the JSON output with the binary stream |
| Storing image in n8n binary and expecting a chat surface to display | Chat surfaces need URL-accessible images (or a platform-native file upload), not raw `$binary` | Upload to CDN, embed URL or use the platform's file API |
| Hardcoding binary base64 in a Code node | Massive workflow JSON, slow, leaky | Reference binary via `$binary` properly, or upload to storage and reference by URL |

