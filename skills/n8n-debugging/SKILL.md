---
name: n8n-debugging
description: Diagnose and fix bugs in n8n workflows. Use when analyzing execution audit JSON files, debugging node output shape mismatches, fixing Redis/Postgres/subworkflow data flow issues, or planning workflow patches. Covers n8n 2.x specifics including Redis overwrite behavior, executeWorkflow input mapping, Postgres bigint errors, and HTTP Request node expression limitations.
---

# n8n Debugging

Practical guide for diagnosing and fixing bugs in n8n workflows on self-hosted instances.

## Debugging protocol (MANDATORY order)

Never read a full execution payload before running the summary. Context discipline
is the point: summary → targeted reads → fix → verify.

1. **Summary first** — `n8n_get_failed_execution_summary(execution_id)`.
   Returns failed_node, previous_node, error, last_success_execution_id and a
   `next_steps` array with ready-to-run tool calls. Execute next_steps args as-is.
2. **Targeted read** — `n8n_get_execution(execution_id, node_name=..., json_path=..., list_range=...)`.
   Start from paths suggested in next_steps (`0.error` for the failed node,
   `0.data.main.0` + `list_range=[0,3]` for data). Widen only if needed.
   Never call without node_name unless you need the compacted overview.
3. **Compare with a good run** — `n8n_diff_executions(last_success_id, failed_id)`.
   Profile-level diff: statuses, items per branch, first-item JSON keys, errors.
   Investigate differing nodes via step 2, not by reading raw payloads.
4. **Trace a value** — `n8n_grep_execution(execution_id, pattern)` to find where
   a value or error string first appeared. Returned paths are json_path-compatible:
   feed them straight back into step 2 (dots/backslashes in keys arrive pre-escaped).
5. **Identify root cause** — match findings against ERROR_PATTERNS.md.
6. **Patch procedure** — `backup → dry_run → review diff → apply → validate →
   post_apply_check → live execution`.

Anti-patterns:
- Reading an execution without node_name "just to look around" — use summary + grep.
- Reconstructing paths by hand when next_steps or grep already provide them.
- Diffing raw JSON of two executions in context — that is what n8n_diff_executions is for.

## Tool parameter notes

- `json_path` — dot-path relative to the node's runs: `0.data.main.0.2.json.body`.
  Numeric segments index lists. Literal dots in keys are escaped as `\.`,
  backslashes as `\\` (grep output already escapes them).
- `list_range=[start, end]` — slice when the resolved value is a list; response
  carries `slice.total_items` so you always know what remains unseen.
- `max_chars` — default 60000, ceiling 200000; oversized results return a preview
  plus a hint. Prefer narrowing the path over raising the limit.
- On a wrong path the error lists available keys / list length — follow the hint,
  do not guess blindly.

## Reference files

- `references/ERROR_PATTERNS.md` — confirmed bug patterns with symptoms, causes, fixes
- `references/COMMON_PATTERNS.md` — reusable code patterns and diagnostic procedures

Read the relevant reference file before proposing a fix.

## Patch rules

- Never modify connections, credentials, settings, or workflow name via `n8n_update_code_node` — use `n8n_patch_workflow_dry_run` for structural changes
- Always backup before any write
- For large workflows (`UMQ7RnnKfdZTijyG` etc.) skip full dry_run JSON construction — use `n8n_update_node_params` for targeted node edits
- `forbidden_changes: []` and `settings_changed: false` required before apply
- Post-apply SHA mismatch from gateway is a known artifact — verify manually via live summary

## Key n8n 2.x constraints

- Redis GET node overwrites `$json` entirely — always restore upstream via `$('NodeName').first().json`
- HTTP Request node cannot handle expressions in JSON body fields — use Code node with `this.helpers.httpRequest()`
- `Retry on Fail` and `Continue on Fail` cannot be used simultaneously (bug #9236)
- `first()` in Code node requires `runOnceForAllItems` mode — fails with `Can't use .first() here` in `runOnceForEachItem`
- Gemini 2.5 Flash with reasoning returns two `parts`: `parts[0]` = thoughtSignature, `parts[1]` = actual JSON
