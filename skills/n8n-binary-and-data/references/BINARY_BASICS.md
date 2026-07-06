# Binary basics

n8n items have two keys: `json` and `binary`. JSON for data, binary for files. They flow side-by-side in every item.

## The shape

```ts
{
    json: { customer_id: 42, status: 'sent' },
    binary: {
        invoice: {
            data: '<base64-encoded bytes>',
            mimeType: 'application/pdf',
            fileName: 'invoice-42.pdf',
            fileExtension: 'pdf',
            fileSize: 12345,
        },
    },
}
```

The key inside `binary` (here, `invoice`) is the **binary property name**. File-handling nodes have a `binaryPropertyName` parameter pointing at it.

## How nodes produce binary

- **HTTP Request** with `responseFormat: 'file'`: response body in `$binary.data` (or set name).
- **Read Files**: contents from disk into `$binary`.
- **AWS S3 / Google Drive download**: `$binary.<key>`.
- **Email triggers with attachments**: arrive in `$binary`.

## How nodes consume binary

- **Email with attachments**: `attachmentsUi` references `binaryPropertyName`.
- **Slack send file**: references the binary property.
- **HTTP Request multipart/form-data**: references binary in `bodyParameters`.
- **Storage upload (S3, R2, Drive)**: references binary as body.

Pattern: producer names a binary property, and consumers reference it by that name.

## Reading binary in a Code node

```ts
// JavaScript Code node, "Run Once for Each Item"
const item = $input.first()
const buffer = await this.helpers.getBinaryDataBuffer(0, 'data')

// Now `buffer` is a Node Buffer; convert as needed:
const text = buffer.toString('utf-8')
const length = buffer.length
const hash = crypto.createHash('sha256').update(buffer).digest('hex')

return [{
    json: { ...item.json, hash, length },
    binary: item.binary,    // pass through
}]
```

`getBinaryDataBuffer(itemIndex, propertyName)` returns raw bytes. Treat as any Node Buffer.

## Writing binary in a Code node

```ts
const text = 'Hello, world!'

return [{
    json: { ok: true },
    binary: {
        report: {
            data: Buffer.from(text).toString('base64'),
            mimeType: 'text/plain',
            fileName: 'report.txt',
            fileExtension: 'txt',
        },
    },
}]
```

Build the entry yourself: base64 the bytes, specify mimeType and fileName.

## Passing binary through JSON-only operations

Edit Fields, IF, and other JSON-only nodes may strip binary. To keep it:

### Pattern 1: explicit pass-through

Some nodes have a "Keep Binary Data" or similar toggle. Enable it.

### Pattern 2: Merge by position

```
[Source with binary] ─┬─→ [Edit Fields: change JSON] ─┐
                       │                                 ├─→ [Merge: byPosition] ─→ ...
                       └─────────────────────────────────┘
```

See `MERGE_FOR_CONTEXT.md`.

### Pattern 3: route through binary-preserving nodes

Some nodes (Webhook, Set, IF in some configs) preserve binary. Others (Code with the wrong return shape) strip it. Test with `test_workflow` and `get_execution`.

## Mime type matters

`mimeType` tells consumers how to interpret bytes. Wrong mime type means consumers may reject (email refuses to attach), display incorrectly (Slack shows generic file icon instead of inline image), or break.

Common mime types:

| File type | Mime type |
|---|---|
| PDF | `application/pdf` |
| PNG | `image/png` |
| JPEG | `image/jpeg` |
| Plain text | `text/plain` |
| JSON | `application/json` |
| CSV | `text/csv` |
| XLSX | `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` |
| ZIP | `application/zip` |

If unsure, sniff from the bytes (PDF starts with `%PDF-`, PNG with `\x89PNG`, JPEG with `\xFF\xD8\xFF`). The `file-type` library does this, and magic-byte sniffing in a Code node works as fallback.

## File size limits

Execution data is stored in the database, and large blobs slow the instance.

- A few MB per slot: fine.
- Tens of MB: slow.
- 100MB+: use external storage (S3, R2) and reference by URL.

For large files: upload to storage immediately, pass URL/ID through the workflow, fetch only when needed.

## Checking binary in `get_execution`

```
get_execution({ executionId: <execution_id>, workflowId: <workflow_id>, includeData: true })
```

Shows per-node input/output. Look for the `binary` slot on items. Missing where expected = stripped there.

May not show actual base64 (too big) but indicates presence and metadata.

## When binary is the input

For workflows receiving a file (multipart webhook upload, email attachment, watched folder):

- Binary arrives at the trigger's output.
- Reference by binary property name from there.
- Pass through downstream nodes that need it.

If binary doesn't appear at trigger output, check:

- Trigger's content-type handling (multipart vs JSON).
- Trigger's binary handling settings (some skip binary by default).
