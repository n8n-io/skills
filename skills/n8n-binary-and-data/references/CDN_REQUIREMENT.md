# CDN requirement for chat-surface images

When a workflow generates an image and the user wants it shown in a chat message (Slack, Discord, Teams, Telegram, embedded webhook chat, etc.):

**Image in `$binary` isn't enough.** Chat surfaces don't render raw binary. Either upload to a CDN/object store and embed by URL, or push the bytes via the platform's file-upload API.

The user must provide the storage. n8n doesn't bundle a CDN.

## Why

Chat messages render as HTML/JSON. Embedded images reference URLs:

```html
<img src="https://cdn.example.com/img/abc123.png">
```

Some surfaces (Slack's `files.getUploadURLExternal` + `files.completeUploadExternal` two-step, Discord attachments, Telegram `sendPhoto`) accept binary directly via the platform's file API. Either way, the bytes have to live somewhere the chat client can fetch over HTTPS.

## What the user needs

A publicly-accessible URL for the image. Ask the user what they have today, but lead with the recommendation:

1. **Recommended: a real CDN / object storage service.** Cloudflare R2 (`https://pub-xxxxx.r2.dev/<key>`), AWS S3 + CloudFront (`https://d1234.cloudfront.net/<key>`), Google Cloud Storage, Azure Blob, Backblaze B2, Vercel Blob, Supabase Storage, Bunny CDN. Direct URL embedding works once the bucket or object is public, latency is low because of edge caching, and signed-URL flows are first-class. R2 is the lowest-friction starting point if they don't have anything (~10 minutes, generous free tier, no egress fees).
2. **Drive-style services (fallback):** Dropbox, Google Drive, OneDrive, Box. These can produce shareable links, but the URL shape and chat-surface rendering behavior vary, and some require explicitly converting share links to direct-download URLs before they'll embed. Confirm with the user that their service can serve a `<img src="...">`-renderable URL before committing.
3. **Self-hosted:** user serves from their own domain. Fine if it's already there, but don't propose standing one up just for this.

Choice depends on existing infrastructure, costs, and security needs.

## What the workflow does

```
[Generate image] → [Upload to CDN] → [Set: image_url = response URL] → [Send chat reply referencing image_url]
```

Concretely, with Cloudflare R2:

```
[OpenAI: generate image]
  ↓ binary on item
[HTTP Request: PUT to R2]
  url: https://<account>.r2.cloudflarestorage.com/<bucket>/<key>
  authentication: AWS-style signed
  bodyContentType: 'binary'
  binaryPropertyName: 'data'
  ↓
[Set: { image_url: 'https://pub-<id>.r2.dev/<key>' }]
  ↓
[Send to chat surface: image_url embedded in the message (markdown, Block Kit image block, adaptive card, etc.)]
```

Upload mechanics depend on the provider. Most expose S3-compatible APIs usable via n8n's S3 node or HTTP Request with AWS auth.

## Telling the user

> "I'll generate the image, but the chat surface can't display raw binary. I'll need to upload it somewhere that serves a public URL. What do you use for image / file storage today (R2, S3, GCS, Dropbox, Google Drive, etc.)? If you don't have anything set up, Cloudflare R2 is the lowest-friction starting point (~10 minutes)."

If they don't have storage set up, there's no fallback that hides the requirement: n8n doesn't host the file for them. Pause until they pick a service and provision a bucket / credentials, then resume. Don't quietly ship a workflow that generates images "but they don't display."

Once storage is in place, posting the URL as a link instead of an embedded image is a valid lighter alternative if rendering inline isn't critical, but that still requires the URL to come from somewhere.

## URL signing and expiration

- **Public URL**: easy, anyone with the URL can access. Use for non-sensitive content.
- **Signed URL with expiration**: per-request, expires (e.g., 1 hour). Use for sensitive content.

For internal chat surfaces with scoped channels, public is usually fine, since URLs are buried in messages only specific users see. For compliance-sensitive content, default to signed URLs.

## File naming

- **UUIDs**: `img/abc-123-def-456.png`. Random, unguessable. Good default.
- **Content hash**: `img/sha256:abc123...png`. Free deduplication.
- **User-prefixed**: `users/<user_id>/<filename>`. Easy per-user cleanup.

Avoid user-controlled filenames (path traversal, collisions) and sequential IDs (predictable, scrapeable).

## Cleanup

Configure:

- **Lifecycle rules**: auto-delete after N days (S3, R2, GCS all support).
- **Cleanup workflow**: scheduled, lists and deletes old objects.

7-30 days retention is usually plenty for chat use cases, but ensure you ask the users preference.
