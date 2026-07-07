# Naming and discovery

A sub-workflow nobody can find gets duplicated. Discovery runs on two `search_workflows` surfaces: `tags` (exact-match category filter, AND semantics) and `query` (substring over name and description). **Tags are the primary category mechanism**; the query is keyword search within or across categories.

## Tags are the discovery mechanism

Requires n8n 2.27.0+. Tag every sub-workflow so future searches find it by category:

| Tag | Use for |
|---|---|
| `subworkflow` | Stateless generic reusable building block |
| `<domain>` (`customer`, `billing`, `notification`) | Domain-specific sub-workflow |
| `tool` | MCP-callable tool (see `n8n-extending-mcp-official`) |

Tags compose, so a customer-domain tool carries `customer` + `tool`. How they drive `search_workflows`:

- `{ tags: ['subworkflow'] }` returns every reusable sub-workflow.
- `{ tags: ['customer'] }` returns every customer-domain workflow.
- `{ tags: ['tool'] }` returns every MCP-callable tool.
- `{ tags: ['customer', 'tool'] }` returns customer-domain tools only (AND: must have both).
- `{ query: 'date' }` returns anything with "date" in name or description, regardless of tag.
- `{ tags: ['subworkflow'], query: 'parse' }` narrows to parsing sub-workflows.

`list_tags` shows the instance's existing tag vocabulary. Check it before inventing a tag so you reuse exact names: AND-filtering and `addTags` are case- and spelling-exact, so `customer` and `Customers` are two different tags.

## Search-before-build, in detail

Before writing logic for a generic problem:

```
search_workflows({ tags: ['subworkflow'] })                 # all sub-workflows
search_workflows({ query: 'date' })                         # anything date-related
search_workflows({ tags: ['customer'] })                    # customer-domain
search_workflows({ tags: ['subworkflow'], query: 'parse' }) # specific shape
```

When to search: any time you're about to build something that fits a domain or operation keyword. About to parse a date? Query `date`. Format an invoice? Query `invoice`. Send a Slack notification? Query `Slack` or filter `tags: ['notification']`.

Two searches is fine, and the cost is low. Better to over-search than duplicate.

If a candidate matches, fetch `get_workflow_details` and read the `description`. If inputs/outputs fit, use it. If close-but-not-quite, decide whether to extend the existing one or build a variant.

## Workflow not visible? Check MCP access

If you've named correctly and `search_workflows` still doesn't return it, per-workflow MCP access is the usual cause. Workflows are invisible to the MCP until the toggle is on. See `n8n-workflow-lifecycle-official` `references/MCP_ACCESS_PER_WORKFLOW.md`.

## The description as discoverability tool

After finding a candidate, the reader reads `description` first. Make it scan well:

```
description: |
  Parses an RFC2822-formatted date string into ISO format.
  Returns { ok: true, iso: '...' } or { ok: false, error: 'invalid_format' }.
  Used by webhook handlers that receive email-style timestamps.
```

This tells the reader: what it does, the output shape, and the typical use case. Without this, the reader has to inspect every node.

Description also feeds `search_workflows` matching. Include representative keywords (e.g., "RFC2822", "date", "ISO", "webhook") so varied queries surface it.

## Naming and tagging at create time

`create_workflow_from_code` sets name and description but **can't set tags**, so tag in a follow-up `update_workflow`:

```ts
create_workflow_from_code({
    name: 'Parse RFC2822 date',
    description: 'Parses an RFC2822-formatted date string into ISO format. ...',
    code: '...',
})
// then, on the returned workflow id:
update_workflow({
    workflowId,
    operations: [{ type: 'addTags', names: ['subworkflow'] }],
})
```

`addTags` auto-creates `subworkflow` if the instance doesn't have it yet (needs the `tag:create` permission; without it, addTags errors on unknown names, so create the tag in the UI first). Don't let new sub-workflows ship untagged: an untagged one won't surface under any `tags` filter.

## Cross-project sub-workflows

On Cloud or project-enabled instances, sub-workflows live in a project. By default, workflows can only call sub-workflows in their own project. Sharing requires opt-in.

Only share cross-project when both apply:

- **Stateless**: no project-scoped credentials, data tables, or other state that wouldn't make sense outside the owning project.
- **Generic problem**: date parsing, ID generation, signature validation, formatting. Things that are clearly not coupled to one project's domain.

A stateful sub-workflow (`Get customer by id`, tag `customer`) shared across projects pulls one project's data into another's workflows, which is almost never what's intended. Keep those in-project, and let each project own its repository layer.

For cross-project sub-workflows that meet the bar:

- Tell the user. They share via the n8n UI.
- Document the cross-project intent in `description`.

## What a healthy library looks like

Roughly:

- 5 to 20 `subworkflow`-tagged sub-workflows for common shapes (date parsing, ID generation, formatting, etc.).
- A handful per main domain tag (`customer`, `billing`, `notification`).
- Fewer per-domain "operations" sub-workflows (write to billing table, send email + log).

Counter-examples:

- 100 sub-workflows: likely lots of near-duplicates to merge.
- 0 sub-workflows: no extraction, logic is being duplicated.
- 50 sub-workflows named `Helper`, `Util1`, `Helper2` and untagged: discoverability broken. Rename and tag.

## When the user asks "what sub-workflows do we have?"

Filter by tag:

```
search_workflows({ tags: ['subworkflow'] })
```

Return a list with name + 1-line summary from each `description`. Good moment to spot duplicates and propose consolidating. `list_tags` (which returns `usageCount` per tag) also gives a fast read on how the library is categorized.

## Renaming and reorganizing

For duplicates or poorly-named sub-workflows:

- Renaming preserves the workflow ID, so existing `Execute Workflow` callers still work. Search picks up the new name immediately.
- Re-categorize with `update_workflow` `addTags`/`removeTags` (e.g. drop `subworkflow`, add `tool`). Tag changes don't touch the workflow ID either.
- n8n has no alias mechanism. Just rename, update any sticky-note references, move on.

For mass renames, audit callers via `search_workflows` and inspect each result's `Execute Workflow` references for the old workflow ID.
