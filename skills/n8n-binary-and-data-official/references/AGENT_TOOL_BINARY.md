# Agent tools and binary

Binary doesn't survive the agent tool boundary in either direction. Agent and tools communicate via JSON. This catches people twice:

1. **Inbound:** user uploads a file. Agent can *see* it via vision, but tool calls don't carry the file.
2. **Outbound:** tool generates a file. Result back to the agent is JSON, so binary can't be returned directly.

Same workaround shape: **stage binary in storage, pass a key/URL through the JSON boundary, fetch on the other side.**

## Inbound: passing user-uploaded binary into a tool

User pastes an image into chat. The chat trigger gives you a `files[]` array on the input. The agent itself can be configured with `passthroughBinaryImages: true` to let the LLM **see** the image (vision), but **the tools cannot.** Tool parameters are filled by `fromAi()` and `fromAi()` only handles strings/numbers/booleans/objects, not binary.

So if the agent needs to call a tool that operates on the file (image edit, OCR, document parse), the tool can't receive the file directly. You have to pre-stage it.

### The pattern

```
[Chat Trigger]
    │
    │ files[]
    ▼
[IF: files empty?]
    ├── empty ──────────────────────────────────────► [AI Agent]
    └── not empty:
        [Split Out files]
          ↓
        [Generate hash for filename]
          ↓
        [Upload binary to private storage with hashed key]
          ↓
        [Merge back into main path]   ← synchronization barrier (see below)
          ↓
        [AI Agent]  ← system prompt is told the keys; set executeOnce: true
            │
            │ tool call with imageKey="abc123.png"
            ▼
        [Tool sub-workflow]
            ↓
          [Download from storage by key]
            ↓
          [Operate on binary (edit, OCR, etc.)]
            ↓
          [Upload result, return new key + URL]
```

### Two pieces of plumbing that look optional and aren't

- **The Merge is a synchronization barrier, not decoration.** The chat trigger fans out to the IF + the upload branch in parallel. Without merging back before the agent, the agent fires while uploads are still in flight, the file-key template in the system prompt runs against partial state, and the model receives keys that don't yet exist in storage. Tool calls then 404. The Merge waits for the upload branch to complete before letting the agent run.
- **`executeOnce: true` on the AI Agent node.** When files split out and merge back, the merged item count equals the file count. Without `executeOnce`, the agent runs once per file: N agent runs, N replies, N times the cost. The user message is one logical event, so the agent should run once.

### What goes in the system prompt

The agent needs to know which keys exist for this turn. Inject them:

```
## File Handling
Files passed in:
{{ JSON.stringify($('Chat Trigger').first().json.files.map((item, index) =>
    ({
        "originalFileName": item.fileName,
        "fileName": $('Generate Hash').all()[index].json.hash + "." + item.fileExtension
    })), null, 2) }}

CRITICAL: Use EXACTLY the `fileName` field as shown above when calling tools.
```

Two things to notice:

1. **Both names are listed.** The original gives the model human context ("photo.png" tells it what kind of file), and the hashed name is what the tool actually needs.
2. **The "use EXACTLY".** Without it, the model paraphrases ("photo.png" or "the user's image") and the tool can't find the file.

### What the tool's `fromAi` parameter looks like

```
fromAi('imageName', 'storage reference for an existing image to operate on, or empty for a new generation. Format depends on backend: an object-storage key like "abc123.png", a Dropbox file ID, a Google Drive file ID. Use the exact key/ID shown in the system prompt; do not reconstruct.', 'string')
```

The description matters: it tells the agent what shape the value should take. Match the description to the backend the user actually wired up. The example above lists multiple shapes for illustration, but a real tool description names only the one the workflow uses.

### Branching: new vs editing

If the tool can be invoked with OR without an existing file (e.g., "generate" vs "edit"), branch inside the tool's sub-workflow:

```
[Trigger: { imagePrompt, imageName, sessionId }]
   ↓
[IF: imageName empty?]
   ├── empty (generation request) ──► [Generate]
   └── not empty (edit request) ──► [Download from storage] → [Edit]
                                          ↓ (storage error)
                                          → [Fallback path]
```

The agent picks which mode by filling or not filling `imageName` in the tool call. Default to one tool with branching, since near-identical tools can confuse selection.

**The viable two-tool variant.** Two `toolWorkflow` nodes can point at the **same** sub-workflow with different parameter wiring: a `Generate Image` tool that hardcodes `imageName: ""` and an `Edit Image` tool that lets the agent fill `imageName` via `fromAi()`. The descriptions then differ ("generate from scratch" vs "edit existing"), giving the model a clearer pick than one tool with a "leave imageName empty for generate" rule. One sub-workflow, two front doors. Use this when the model keeps misfiring on the unified tool's discriminator parameter. Otherwise the unified tool is simpler.

### `passthroughBinaryImages: true` on the agent

Set this when the agent should be able to *see* uploaded images (multimodal vision). It enables the LLM to receive the image as part of its prompt context.

**Image-only.** The flag handles images for vision-capable models. PDFs, audio, and video do not get vision through this setting. For those, the model only sees what you put in the system prompt (filename, type, the storage key) and must rely on a tool to extract content. For PDFs specifically, an OCR/parse tool is the standard route.

It does **not** help the tools. Tools still get only the parameters from `fromAi`, regardless of this setting. So you still need the upload-and-pass-key pattern if a tool needs to operate on the file.

The two settings work together:
- `passthroughBinaryImages: true`: model can see and reason about the image.
- Pre-staged storage + key in system prompt: the model can ask a tool to *do something* with it.

### Storage choice for inbound

Same options as outbound (next section), but a few inbound-specific notes:

- **Use a private bucket.** Inbound user files often contain sensitive content. Don't dump them in a public bucket.
- **Key by session.** Including the session ID (or a hash of it) in the key makes per-conversation cleanup easy. Pattern: `<session-suffix>-<random-hash>.<ext>`.
- **Short TTL.** User-uploaded files for chat are usually only relevant for that conversation. A 24-hour or 7-day TTL is plenty in most cases.

### Hash strategy: inbound vs outbound

Use different hash patterns at each end:

- **Inbound (uploads, may be referenced repeatedly within a session):** a content-stable or per-upload deterministic key. Re-uploading the same file from the same session lands at the same key, so the agent's reference doesn't break if the user re-attaches the same file. The `Crypto` node with a string-length hash on the file's content (or on a session-and-filename composite) works.
- **Outbound (generated artifacts, single-use):** a random hash, never reused. Same generation prompt should produce a fresh URL every time, otherwise concurrent calls overwrite each other's outputs. Pattern: `<session-suffix>-<random-hex>.<ext>`.

The two `Crypto` nodes you'll often see in this kind of workflow aren't a copy-paste mistake. One is for the inbound stable hash, the other for the outbound unique suffix.

### Long-running tools (video generation, large batches)

Agent tool calls don't time out at the agent layer. A sub-workflow tool that takes 20 minutes returns whenever it returns, the agent waits. So for slow generation, the answer is the same as for any other tool: a sub-workflow tool with the slow node inside, `options.binaryPropertyOutput: 'data'` on the generator, upload to storage, return `{ url, key }`.

The one place duration actually matters: **the HTTP Request node has its own HTTP-level timeout** (default 5 minutes). If your tool is an HTTP Request Tool calling a slow external API, bump `options.timeout` past the expected duration. Otherwise the HTTP call aborts mid-job, the upstream work keeps running, and the agent gets nothing.

## Surface-specific seams: look up the platform's API docs

The examples in this ref use n8n Chat Trigger conventions: `$('Chat Trigger').first().json.files[]` on the way in, markdown image rendering (`![]()`) on the way out. **These shapes aren't universal.** Production chat surfaces (Slack, Discord, Microsoft Teams, Telegram, WhatsApp Business, custom webhooks, etc.) each have their own:

- **Inbound file event shape.** Field names, where the file lives in the trigger payload, whether the URLs are public or require a bearer token to download.
- **Outbound rendering mechanism.** Some platforms render markdown image syntax, many don't. Block-style messages (Slack Block Kit, Teams adaptive cards, Discord embeds) have their own image element shapes. Some platforms have a dedicated file-upload API that pushes binary natively rather than embedding by URL.
- **Auth patterns** for file download. Canvas Chat Trigger URLs are usually directly fetchable, but third-party platforms gate file URLs behind a bot or app token.

Don't guess from the canvas examples. Before wiring an inbound or outbound binary path on a production surface, **look up the platform's official API docs and the n8n node's docs for that platform**. Use WebSearch or WebFetch if you need to. Two specific things to check:

1. The exact path to the file metadata in the trigger event payload, and whether downloading the URL needs auth headers.
2. The exact shape the platform expects for an image / file in a reply (markdown? a JSON block? a separate upload call?).

Get those two right and the rest of the patterns in this ref carry over cleanly. Skip them and the workflow ships looking correct, then quietly fails on real messages.

## Outbound: tool produces binary, agent needs to return it

When an agent tool produces a file (generated PDF, image, document), the tool's result back to the agent is JSON. Binary bytes don't fit naturally into JSON. They'd have to be base64-encoded into a JSON field, and they'd be huge, slowing every tool call and bloating the agent's context.

So agent tools effectively can't return raw binary. The binary lives in storage, and the tool returns a reference to it.

### The pattern

```
[Agent calls tool]
    │
    ▼
[Tool sub-workflow]
    ↓
  [Generate or transform binary]
    ↓
  [Upload to storage with key]
    ↓
  [Return JSON: { ok: true, key, url, mime_type, size_bytes }]
    │
    ▼
[Agent receives JSON, can display URL or pass key to another tool]
```

### What the tool returns

A useful response shape:

```json
{
  "ok": true,
  "file_id": "abc123",
  "url": "https://storage.example.com/files/abc123",
  "mime_type": "application/pdf",
  "size_bytes": 12345,
  "expires_at": "2026-04-26T12:00:00Z"
}
```

The agent decides what to do: display the URL inline (markdown image/link in the response), pass the key to another tool, attach to a callback. The system prompt typically tells it which:

```
## Display Protocol
ALWAYS display generated images using inline markdown:
![descriptive alt text](https://imageurl.com)

For VIDEOS, share as a plain markdown link, NOT a video embed:
[Descriptive video title](https://videourl.com)
```

**Image vs video display matters, and rendering is surface-specific.** The `![]()` markdown above is the canvas Chat Trigger's syntax. Production surfaces use Block Kit image blocks, adaptive cards, embeds, or native file uploads (see the "Surface-specific seams" section above). Whatever the surface, video is the harder case: video embeds often don't render reliably, and a plain link is the path that works everywhere. Tell the agent explicitly in the system prompt for *its* surface. Otherwise it copies the image pattern for video and the user sees a broken thumbnail.

### When you don't need this

- **Internal workflows** where one node generates binary and another consumes it directly in the same workflow. Just pass binary through. No agent boundary involved.
- **Webhook APIs** that respond with binary directly. `Respond to Webhook` can return binary in the response body. Use that for "API returns a file" cases.

The upload-and-return-key pattern is specifically for the agent-calls-tool-and-tool-produces-binary case.

## Storage choices

### Ask which service before building

n8n supports many storage backends, and defaulting to S3 is presumptuous. Before designing the workflow, ask the user what they use. Common options, all with native nodes:

- **Object storage:** Amazon S3, Cloudflare R2, Google Cloud Storage, Azure Blob, Backblaze B2, Supabase Storage. Most expose S3-compatible APIs and run through n8n's S3 node with the right endpoint, or have their own dedicated node.
- **File / drive storage:** Dropbox, Google Drive, OneDrive, Box. Different mental model (folders, sharing semantics, link generation) but works for the same staging job.
- **Self-hosted / FTP / SFTP:** when the user has on-prem infrastructure.
- **n8n's own binary slot:** OK for short-lived artifacts the agent fetches within seconds. Tied to the execution lifecycle, so old executions get cleaned up.
- **User-provided URL:** the caller supplies the storage location as input. Useful when the agent's caller has its own storage layer.

The choice affects credential setup, URL shape, public vs signed access, TTL/cleanup mechanics, and how the tool's `fromAi` parameter description should explain the URL/key format. Don't pick on the user's behalf.

### What changes per backend

- **Object storage** (S3 family): keys, optional public buckets, signed URLs, lifecycle rules for TTL.
- **Drive-style** (Dropbox/Drive/OneDrive/Box): file IDs, share links, no built-in TTL (cleanup is its own workflow), folder permissions instead of bucket ACLs.

A common production split for object storage: private bucket for inbound user files, public bucket for outbound results so the agent can return public URLs. For drive-style, use a private folder for inbound and a shared-link-enabled folder for outbound.

## Lifecycle and cleanup

Without cleanup, bills grow. Options:

- **TTL on storage:** object-storage providers (S3, R2, GCS, Azure Blob) have lifecycle rules that auto-delete old objects, and 7-30 days is usually fine. Drive-style backends (Dropbox, Google Drive) don't have built-in TTL, so cleanup is its own scheduled workflow.
- **Cleanup workflow:** scheduled workflow lists and deletes old files.
- **Reference counting:** a Data Table tracks "referenced" files, and cleanup deletes unreferenced.

Pick based on retention and cost.

## Common mistakes

- **Passing binary through `fromAi()`.** Can't carry binary. Pass a key/URL and re-fetch.
- **Forgetting to inject file keys into the system prompt.** Without this, the agent hallucinates names or refuses.
- **Skipping the Merge synchronization barrier before the agent.** Agent fires while uploads are still in flight, system prompt has keys that don't yet exist in storage, and tool calls 404. Merge the upload branch back into the agent path before the agent runs.
- **Forgetting `executeOnce: true` on the agent when files split out.** N files → N agent runs → N replies for one user message. Set `executeOnce: true`.
- **Forgetting `options.binaryPropertyOutput: 'data'` on provider-binary nodes.** Gemini image/video, OpenAI image, ElevenLabs, etc. need this set explicitly. Without it, the produced binary doesn't land where the next node looks for it and the upload step has nothing to upload.
- **Public bucket for inbound user files.** Privacy hole. Use private with session-scoped keys.
- **Returning binary in the tool response.** Response sizes blow up, and some runtimes reject. Don't.
- **Forgetting `passthroughBinaryImages: true` when you need vision.** Without it, the model responds blind. (Image-only, doesn't help PDFs / audio / video.)
- **No URL expiration.** Public, non-expiring URLs are a security hole for sensitive content. Use signed URLs.
- **HTTP Request Tool with default timeout on a slow endpoint.** Default is 5 minutes. Long-running media generation aborts mid-job, the upstream keeps running, the agent gets nothing. Bump `options.timeout` past expected duration. (Sub-workflow tools don't have this issue, agent tools have no agent-layer timeout.)
- **Embedding video as `![]()`.** Renders as a broken thumbnail in most chat surfaces. Use `[title](url)` link form for video.

## Documenting the tool

In the sub-workflow's `description`:

- Expected input, including storage key parameters and format.
- Return shape (`{ url, key, ... }`).
- Whether URLs expire (and how soon).
- For inbound: whether a pre-staged file is required.

Per `n8n-extending-mcp-official`, also document in the user's `CLAUDE.md`.
