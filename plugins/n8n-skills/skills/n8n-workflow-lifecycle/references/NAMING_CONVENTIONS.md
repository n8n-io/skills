# Naming conventions

A workflow built today gets searched, debugged, and extended six months later by people who weren't in the room. These conventions optimize for findability and readability over brevity.

## Workflows

### Format

```
<Verb> <object> [scope/qualifier]
```

Verb says what it *does*, object says *to what*, qualifier (optional) narrows scope.

| ✅ Good | ❌ Avoid |
|---|---|
| `Send weekly customer report` | `Customer report sender` (noun-first, ambiguous frequency) |
| `Sync Stripe customers to Postgres` | `Stripe-Postgres` (no verb, unclear direction) |
| `Notify on-call when error rate >5%` | `Error monitor` (vague: what does it do?) |
| `Daily: clean up stale Slack DMs` | `Slack cleanup` (no schedule, no specificity) |

### Capitalization

Sentence case, not Title Case. Easier to scan, and matches normal prose. Acronyms keep their casing.

### Punctuation

- Colon for category prefix: `Subworkflow: Parse RFC2822 date`, `Daily: clean up stale Slack DMs`.
- No emojis in workflow names. They break in URLs, search, and CLI tools.
- No trailing version numbers (`v2`, `final`). For versioning, archive the old one or use git on the SDK code.

## Sub-workflows

Same verb-first rule, but prefix with a domain or `Subworkflow:` for stateless sub-workflows reusable anywhere.

| Pattern | Example |
|---|---|
| `Subworkflow: <verb> <object>` | `Subworkflow: Fetch JSON with retry`, `Subworkflow: Parse RFC2822 date` |
| `<Domain>: <verb> <object>` | `Customer: hydrate from Stripe`, `Billing: compute MRR` |
| `Tool: <description>` | `Tool: list available credentials` (for MCP-extending workflows, see `n8n-extending-mcp`) |

The prefix isn't a folder, it's a name pattern. It exists as a workaround: the MCP currently doesn't expose tags, and `search_workflows` matches only against name and description, so prefixes act as the searchable category mechanism. If/when the MCP adds tag support, this convention should shift from prefix-based to tag-based; the prefix is a temporary stand-in for what tags will eventually do better.

## Nodes

### The rule

Nodes are named after **what they do in this workflow**, not the node type.

| ✅ Good | ❌ Avoid |
|---|---|
| `Fetch active customers` | `Postgres1` |
| `Build email HTML` | `Set2` |
| `Send manager Slack alert` | `Slack` |
| `Loop through orders` | `SplitInBatches` |
| `Webhook: report-request` | `Webhook` |

The default name (`HTTP Request1`, `Code1`) is debugging hostile. A failure on `node "HTTP Request3"` tells you nothing, but a failure on `node "Fetch order details"` tells you exactly which step is broken.

### Webhook nodes

Always include path or purpose: `Webhook: report-request`, `Webhook: GitHub PR opened`. The URL itself is opaque, so the name compensates.

### Loop and merge nodes

For `SplitInBatches`, name after what's being iterated (`Loop through orders`).

For `Merge`, name after what's being merged (`Merge customer + Stripe data`).

## Tags

Tags are UI-only. The n8n MCP cannot create, attach, read, or filter by tags, and the SDK doesn't expose a tags field. Useful for **humans** browsing the UI, but **not** an AI discovery mechanism.

If tagging in the UI:

- All lowercase, with spaces (not hyphens): `customer data`, `daily report`, `util`, `prod`.
- Optionally lead with an emoji as a quick visual category marker: `🧰 util`, `📊 daily report`, `💵 financial`. Use it consistently within a project or skip it entirely. Mixing tagged-with-emoji and tagged-without-emoji within the same project defeats the purpose.
- Aim for up to 2-4 per workflow, since more can be noise.

### Discovery is name-based, not tag-based

`search_workflows({ query })` matches name and description only. To make a sub-workflow findable, the name must contain the discovery hook:

- Verb-first prefix: `Subworkflow: Parse RFC2822 date`, `Customer: hydrate from Stripe`, `Tool: list available credentials`.
- Description carries representative keywords.

For the full naming-and-discovery protocol, see `n8n-subworkflows` `references/NAMING_AND_DISCOVERY.md`.

## Workflow `description`

Always include `description` on `create_workflow_from_code`. 2-4 sentences answering:

1. **What does it do?** (one sentence)
2. **Why does it exist / what's the context?** (one sentence)

The second matters more. The "what" is usually obvious from the nodes, but the "why" is context the user provided (or you derived) and otherwise gets lost.

| Good | Avoid |
|---|---|
| "Sends a weekly summary of new signups to the founders' Slack. Built because the manual report kept getting skipped during launch weeks." | "Sends weekly Slack." |
| "Hydrates incoming Stripe customer events with subscription data and writes to the customers table. Replaces the old Zapier flow that hit rate limits." | "Stripe to Postgres." |

For more on capturing derived context, see the parent `SKILL.md` "Readability" section.

## When to break the rules

- **Existing project conventions.** If the user's instance uses different naming, match their pattern. Consistency within a project beats consistency with this skill.
- **Generated workflows.** For programmatic batches (one per data source), templated names are fine, but include the source identifier (`Sync source-A to warehouse`, not `Sync1`).
