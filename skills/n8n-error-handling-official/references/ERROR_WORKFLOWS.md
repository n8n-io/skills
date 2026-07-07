# Workflow-level error workflows

Per-node error outputs handle one node's failure. They don't catch:

- Failures in nodes you forgot to wire.
- Crashes between nodes.
- Workflow timeouts.
- Issues with the trigger itself.

For unattended workflows, this gap matters: silent failure means no alert, no log, no clue. The fix is a **workflow-level error workflow**: when an unhandled error escapes, n8n invokes the designated error workflow with the failure context.

## What an error workflow looks like

Triggered by the **Error Trigger** node. Receives roughly this shape (verified against `IWorkflowErrorData` in `packages/cli/src/interfaces.ts` and `ExecutionBaseError.toJSON` in `packages/workflow/src/errors/abstract/execution-base.error.ts`):

```json
{
  "execution": {
    "id": "...",
    "url": "...",
    "retryOf": "...",
    "error": {
      "name": "NodeApiError",
      "message": "...",
      "description": "...",
      "context": { },
      "timestamp": 1715000000000
    },
    "lastNodeExecuted": "Fetch order",
    "mode": "trigger"
  },
  "workflow": {
    "id": "...",
    "name": "Sync Stripe customers"
  }
}
```

The error workflow's job:

1. Identify the failure and surface it (Slack/email/PagerDuty).
2. Optionally enqueue retry / dead-letter logic.

## Minimal error workflow

```
Error Trigger
  → Edit Fields (build alert message from execution + error data)
  → Slack (post to #incidents)
```

Or, more featurefully, fetch the actual execution to recover the input data that caused the failure:

```
Error Trigger
  → n8n (resource: execution, operation: get,
         executionId: {{ $json.execution.id }},
         options.activeWorkflows: true)        ← includeData=true on the API
                                               ← REQUIRES an "n8n API" credential
                                                 (Settings → API → create personal access token,
                                                  then attach via the node's Credential field)
  → Edit Fields (extract failed-node input from execution data)
  → Switch (route by severity)
      ├── high → PagerDuty
      ├── med  → Slack #incidents
      └── low  → Slack #monitoring
  → Data Table Insert (log for tracking)
```

The Error Trigger payload only carries the error message, the failed node *name* (`lastNodeExecuted`), and the execution URL. It does **not** include the input data that caused the failure. The `n8n` node with `Get Execution` + `Include Execution Details: true` fills that gap by hitting `GET /executions/{id}?includeData=true` and returning the full run data, so you can pluck the failed node's input out of `data.resultData.runData[<lastNodeExecuted>][0].source` (or its inputs in `executionData.nodeExecutionStack` for more depth).

Why it's worth the extra step:
- The on-call message can include the actual offending payload, not just "node X errored".
- If you triage by input shape (which customer, which order ID), you skip a step in the n8n UI.

Caveats:
- Requires an **n8n API credential** on the error workflow. Create one under *Settings → API* (personal access token), then attach it to the n8n node's Credential field. Without it the node fails with a 401, which means an unhandled error in the *error* workflow itself.
- Requires the failing workflow to have **Save Execution Data** enabled (instance default or per-workflow setting; set it via `setWorkflowSettings` `saveDataErrorExecution`/`saveDataSuccessExecution`). If executions aren't persisted, the API returns the metadata only.
- The n8n node call itself can fail (API down, rate-limited). Wire its error output to a fallback that still notifies, otherwise the original error vanishes.

Minimal is enough for most cases. The featureful version pays off in production-critical workflows where on-call time matters.

## Setting it up

Set it via `update_workflow` `setWorkflowSettings.errorWorkflow` (the target workflow's ID). Validated server-side: the target must exist, be published, and contain an active Error Trigger node, else the update is rejected. Pass `"DEFAULT"` to clear. (n8n 2.29.0+; older instances set it in the workflow settings panel.)

## What the error workflow should *not* do

- **Make external API calls that can themselves fail.** If your error workflow fails, the original error silently disappears.
- **Take significant time.** Runs synchronously, so slow error workflows compound the original failure's impact.

Keep error workflows fast: parse, notify, return.

## Avoiding the recursion trap

If your error workflow uses Slack and Slack is down, the error workflow fails too. n8n won't re-trigger on its own failure (no infinite loop), but the failure goes nowhere.

Mitigations:

- Use a different channel than the monitored workflows. If most workflows notify Slack, the error workflow should use email.
- Have a fallback: write to a Data Table if the primary notification fails.
- Configure instance-level logging (server logs, Sentry) so even error-workflow failures surface.

## What to put in the alert

Good notifications include:

- **Workflow name**: `{{ $json.workflow.name }}`
- **Workflow ID**: `{{ $json.workflow.id }}`
- **Workflow link**: `{{ $json.execution.url.split('/executions/')[0] }}` (the execution URL is `{base}/workflow/{id}/executions/{execId}`, so stripping the tail gives the editor URL)
- **Execution ID**: `{{ $json.execution.id }}`
- **Execution link**: `{{ $json.execution.url }}` (opens the failed run directly)
- **Failed node name**: `{{ $json.execution.lastNodeExecuted }}`
- **Error message**: `{{ $json.execution.error.message }}` (real, not generic)
- **Error description**: `{{ $json.execution.error.description }}` (often empty, useful when set)
- **Timestamp**: `{{ DateTime.fromMillis($json.execution.error.timestamp).toISO() }}` (the payload's `timestamp` is a Unix ms number, format with Luxon)
- **Severity**: derived from your routing logic, not on the payload

Bad: "Workflow failed."

Good (Slack body, expression-driven, both links present):

```
Workflow failure: *{{ $json.workflow.name }}* (`{{ $json.workflow.id }}`)
Workflow: {{ $json.execution.url.split('/executions/')[0] }}
Failed node: `{{ $json.execution.lastNodeExecuted }}`
Error: {{ $json.execution.error.message }}
Execution: {{ $json.execution.url }}
Time: {{ DateTime.fromMillis($json.execution.error.timestamp).toISO() }}
```

Two links matter: the **workflow link** so on-call can open the editor to start fixing, and the **execution link** so they can see the exact run that broke. Skipping either costs a step.

A "likely cause" line is optional, but for known failure modes a hint saves the on-call ten minutes.

## When error workflows fire

Fires when:

- A node throws unhandled (not routed via per-node error output).
- The workflow itself fails (timeout, OOM).
- The trigger fails (rare, possible for non-webhook triggers).

Does **not** fire when:

- A node's error output is wired and the error is "handled" (even if the handler does nothing).
- You manually stop an execution.
- A workflow is paused / inactive.

So per-node error outputs that drop errors silently (e.g., wired to a no-op Set node) will *not* trigger the error workflow. The error has been "handled" from n8n's perspective, even though it's been swallowed.

For unhandled errors to bubble up, don't catch them per-node unless you're actively doing something with them.

## Verifying the error workflow

After setup:

1. Build a test workflow that always fails (HTTP Request to an invalid URL with no error output wired).
2. Run it.
3. Confirm the error workflow fires and the notification arrives.

Catches setup mistakes (wrong workflow assigned, wrong channel, missing credentials). Do this before relying on alerting.

## Drift watch

Error Trigger payload shape can change between versions. If fields aren't where this file says, check current n8n docs and update parsing.
