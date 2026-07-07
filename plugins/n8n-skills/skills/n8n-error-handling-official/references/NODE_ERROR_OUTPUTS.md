# Per-node error outputs

About wiring an **error output on an individual node**: the second main output that fires when the node throws. For workflow-level error handling (catch-all workflows, webhook → respond), see the rest of `n8n-error-handling-official`.

## Two-step setup

Always two changes. One without the other looks complete but misbehaves.

### Step 1: configure the node

Set `onError: 'continueErrorOutput'`. Without this, the node has no error output, and `main[1]` doesn't exist regardless of wiring.

```ts
{
  // ...other params...
  onError: 'continueErrorOutput',
}
```

Other valid `onError` values:
- `'stopWorkflow'` (default): error halts the whole workflow
- `'continueRegularOutput'`: error data flows out the regular output (rare, usually wrong)
- `'continueErrorOutput'`: error data flows out a separate error output (the one you wire below)

### Step 2: wire `output(1)` to a handler

With `onError: 'continueErrorOutput'`, the node has two outputs:
- `output(0)`: success path
- `output(1)`: error path

```ts
.add(node.output(0).to(successPath))
.add(node.output(1).to(errorHandler))
```

Or with the convenience handler:

```ts
.add(node.onError(errorHandler))   // same as .add(node.output(1).to(errorHandler))
```

## Common shapes

### Single fallible node with error branch

```ts
const sheets = node({
  type: 'n8n-nodes-base.googleSheets',
  config: {
    parameters: { /* ...sheet config... */ },
    onError: 'continueErrorOutput',
  },
})

const respond = node({
  type: 'n8n-nodes-base.respondToWebhook',
  config: { parameters: { /* 5xx structured body */ } },
})

workflow
  .add(webhook.output(0).to(sheets))
  .add(sheets.output(0).to(successResponse))
  .add(sheets.output(1).to(respond))   // error path
```

### Fan-out on the success path with error branch

```ts
.add(sheets.output(0).to(successA))
.add(sheets.output(0).to(successB))
.add(sheets.output(1).to(errHandler))
```

### Multiple fallible nodes routing to a shared error handler

```ts
.add(nodeA.output(1).to(errorHandler))
.add(nodeB.output(1).to(errorHandler))
.add(nodeC.output(1).to(errorHandler))
// Each node needs onError: 'continueErrorOutput' on its config.
```

## Failure modes

### `onError` set, error output not wired

```ts
const sheetsBroken = node({
  type: 'n8n-nodes-base.googleSheets',
  config: {
    onError: 'continueErrorOutput',
    // no error wire
  },
})
```

On error, the node emits to `main[1]` with no targets. Error data is silently discarded, downstream doesn't fire, and the workflow appears to succeed (because the error was "handled" by a non-existent branch). One of the worst silent-failure modes in n8n: looks fine in the dashboard, no execution failure logged.

**Fix:** wire `output(1)` to a real handler, or change `onError` back to `stopWorkflow` so failures are loud.

### Error wire set, `onError` not configured

```ts
const sheetsMissingOnError = node({
  type: 'n8n-nodes-base.googleSheets',
  config: {
    // missing onError
  },
})

.add(sheetsMissingOnError.output(1).to(errHandler))
```

The wire exists in the JSON but the slot never fires, and the handler is unreachable. On failure, the workflow stops (default `onError: stopWorkflow`).

**Fix:** add `onError: 'continueErrorOutput'` to the node config.

### Mixing `.onError(handler)` with `output(1)` on the same node

Composes without conflict. Both wires are present.

```ts
.add(node.onError(loggerNode))
.add(node.output(1).to(respondNode))
// Both loggerNode and respondNode receive the error data.
```

Intentional: useful for both logging *and* a user-facing response on failure.

## Verification

After create/update, pull via `get_workflow_details` and check both halves:

1. **Node config**: `"onError": "continueErrorOutput"` (or whatever you set).
2. **Connections**: `connections[node].main[1]` contains the expected handler(s).

Either half missing = silent failure.

## When to use error workflows instead

Per-node error outputs handle one node's failure. They don't catch:

- Crashes outside any node (rare).
- Errors on nodes without wired error outputs.
- Whole-workflow timeouts.

For those, configure a workflow-level **error workflow**. See the rest of `n8n-error-handling-official`.
