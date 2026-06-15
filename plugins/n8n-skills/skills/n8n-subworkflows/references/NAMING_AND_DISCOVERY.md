<!-- TEMPORARY: change workflow prefix searching to tags when tag tools are added to mcp -->

# Naming and discovery

A sub-workflow nobody can find gets duplicated. The MCP's only searchable surface is `search_workflows({ query })`, which matches against name and description. **That's the discovery mechanism.** Put discovery hooks in the name and description.

## Tags don't help here

n8n has tags, but the MCP can't read, write, or filter by them. UI-only concept. Don't rely on tags for AI-side discovery.

## The naming convention IS the discovery mechanism

Verb-first prefix names from `n8n-workflow-lifecycle`'s `NAMING_CONVENTIONS.md`:

```
Subworkflow: <verb> <object>            # Stateless generic sub-workflow
<Domain>: <verb> <object>        # Domain-specific
Tool: <description>              # MCP-callable tool
```

Examples:

- `Subworkflow: Parse RFC2822 date`
- `Subworkflow: Compute MRR from subscription`
- `Subworkflow: Format invoice as HTML`
- `Customer: hydrate from Stripe`
- `Customer: write to billing table`
- `Billing: compute MRR`
- `Notification: send + log`
- `Tool: list available credentials`

Why this works for `search_workflows({ query })`:

- `query: 'Subworkflow:'` returns every reusable sub-workflow.
- `query: 'Customer:'` returns every customer-domain sub-workflow.
- `query: 'Tool:'` returns every MCP-callable tool.
- `query: 'date'` returns anything with "date" in name or description, regardless of prefix.

Use the prefix on every sub-workflow.

## Search-before-build, in detail

Before writing logic for a generic problem:

```
search_workflows({ query: 'Subworkflow' })                  # all sub-workflows
search_workflows({ query: 'date' })                  # anything date-related
search_workflows({ query: 'Customer' })              # customer-domain
search_workflows({ query: 'Subworkflow: Parse' })           # specific shape
```

When to search: any time you're about to build something that fits a domain or operation keyword. About to parse a date? Query `date`. Format an invoice? Query `invoice`. Send a Slack notification? Query `Slack` and `Notification`.

Two queries is fine, and the cost is low. Better to over-search than duplicate.

If a candidate matches, fetch `get_workflow_details` and read the `description`. If inputs/outputs fit, use it. If close-but-not-quite, decide whether to extend the existing one or build a variant.

## Workflow not visible? Check MCP access

If you've named correctly and `search_workflows` still doesn't return it, per-workflow MCP access is the usual cause. Workflows are invisible to the MCP until the toggle is on. See `n8n-workflow-lifecycle` `references/MCP_ACCESS_PER_WORKFLOW.md`.

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

## Naming at create time

Set the name correctly when calling `create_workflow_from_code`:

```ts
create_workflow_from_code({
    name: 'Subworkflow: Parse RFC2822 date',
    description: 'Parses an RFC2822-formatted date string into ISO format. ...',
    code: '...',
})
```

Easier than retrofitting. Don't let new sub-workflows ship without the prefix convention.

## Cross-project sub-workflows

On Cloud or project-enabled instances, sub-workflows live in a project. By default, workflows can only call sub-workflows in their own project. Sharing requires opt-in.

Only share cross-project when both apply:

- **Stateless**: no project-scoped credentials, data tables, or other state that wouldn't make sense outside the owning project.
- **Generic problem**: date parsing, ID generation, signature validation, formatting. Things that are clearly not coupled to one project's domain.

A stateful sub-workflow (`Customer: get by id`) shared across projects pulls one project's data into another's workflows, which is almost never what's intended. Keep those in-project, and let each project own its repository layer.

For cross-project sub-workflows that meet the bar:

- Tell the user. They share via the n8n UI.
- Document the cross-project intent in `description`.

## What a healthy library looks like

Roughly:

- 5 to 20 `Subworkflow:` sub-workflows for common shapes (date parsing, ID generation, formatting, etc.).
- A handful of domain sub-workflows per main domain (`Customer:`, `Billing:`, `Notification:`).
- Fewer per-domain "operations" sub-workflows (write to billing table, send email + log).

Counter-examples:

- 100 sub-workflows: likely lots of near-duplicates to merge.
- 0 sub-workflows: no extraction, logic is being duplicated.
- 50 sub-workflows named `Helper`, `Util1`, `Helper2`: discoverability broken. Rename.

## When the user asks "what sub-workflows do we have?"

Run a name-prefix search:

```
search_workflows({ query: 'Subworkflow:' })
```

Return a list with name + 1-line summary from each `description`. Good moment to spot duplicates and propose consolidating.

## Renaming and reorganizing

For duplicates or poorly-named sub-workflows:

- Renaming preserves the workflow ID, so existing `Execute Workflow` callers still work. Search picks up the new name immediately.
- n8n has no alias mechanism. Just rename, update any sticky-note references, move on.

For mass renames, audit callers via `search_workflows` and inspect each result's `Execute Workflow` references for the old workflow ID.
