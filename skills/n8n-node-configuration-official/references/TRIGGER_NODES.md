# Trigger nodes: gotchas

Param shapes are version-dependent; `get_node_types` is canonical. This file covers what's *not* in the type def.

For the Webhook trigger, see `WEBHOOK_NODES.md`.

## Schedule Trigger

### Timezone is workflow-level, not per-rule

The Schedule Trigger uses the **workflow's** timezone setting (Workflow Settings → Timezone). There is no `timezone` field inside `rule`. For workflows that must run at a specific local time regardless of host, set the workflow timezone explicitly. Without it, DST transitions and instance moves cause timing shifts.

### Cron: 5 fields or 6

n8n's cron supports both 5-field (Minute Hour DoM Month DoW) and 6-field (Second Minute Hour DoM Month DoW) formats. The UI hint shows 6, the placeholder shows 5. Both work.

For "run weekly Monday 9am"-style cases, the simple time-based modes (`field: 'weeks'`) are clearer than cron.

### Instance restarts can miss runs

Schedules use the instance's clock. A restart during a scheduled time can miss that run. For business-critical schedules:

- Idempotent design (multiple runs = same result).
- Missed-run detection at workflow start (compare last successful run to expected, catch up if needed).

## Execute Workflow Trigger

For sub-workflows called by other workflows. The trigger's `inputSource` discriminator picks one of three input contracts:

- **Schema-defined** (preferred): list each input's name and type. Strongest contract, self-documenting.
- **JSON example**: paste an example object, n8n infers the schema.
- **Passthrough**: accept all data from the parent.

Pick schema-defined unless the input shape is genuinely free-form or requires binary passthrough. The schema is the API. Document inputs/outputs in the workflow `description` per `n8n-subworkflows-official`.
