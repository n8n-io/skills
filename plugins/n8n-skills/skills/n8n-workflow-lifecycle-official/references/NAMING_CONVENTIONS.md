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

- Colon for category prefix on top-level workflows: `Daily: clean up stale Slack DMs`, `Webhook: report-request`. Sub-workflows categorize by tag, not name prefix (see Sub-workflows and Tags below).
- No emojis in workflow names. They break in URLs, search, and CLI tools.
- No trailing version numbers (`v2`, `final`). For versioning, archive the old one or use git on the SDK code.

## Sub-workflows

Same verb-first rule. The name says what the sub-workflow does; a **tag** says what kind it is. Category lives in tags, not a name prefix.

| Name | Tags |
|---|---|
| `Fetch JSON with retry` | `subworkflow` |
| `Parse RFC2822 date` | `subworkflow` |
| `Hydrate customer from Stripe` | `customer`, `subworkflow` |
| `Compute MRR` | `billing` |
| `List available credentials` | `tool` (MCP-extending workflows, see `n8n-extending-mcp-official`) |

Tags compose: a customer-domain tool carries `customer` + `tool`. `search_workflows({ tags })` filters on them with AND semantics (a workflow must have every listed tag). This replaces the old name-prefix convention, which only existed because the MCP couldn't filter by tags. Full discovery protocol: `n8n-subworkflows-official` `references/NAMING_AND_DISCOVERY.md`.

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

Tags are the AI-side discovery and categorization mechanism (n8n 2.27.0+). The MCP can read them (`list_tags`), filter by them (`search_workflows({ tags })`, AND semantics), and attach/detach them (`update_workflow` `addTags`/`removeTags`). `addTags` auto-creates an unknown tag, so you never pre-register one. It cannot rename or delete tag entities, and `create_workflow_from_code` can't set tags at create time, so tag right after creating.

Tag names are now exact-match machine identifiers, not just human labels:

- All lowercase, spaces not hyphens: `customer`, `daily report`, `util`, `prod`. A case or spelling mismatch is a different tag.
- No emojis. `addTags` and the `tags` filter match names exactly, so an emoji makes every match fragile.
- **`list_tags` before tagging** to reuse the instance's existing names instead of spawning near-duplicates (`customer` vs `customers`).
- Aim for 2-4 per workflow. More is noise.

Standard category tags: `subworkflow` (reusable building block), a domain tag (`customer`, `billing`, `notification`), and `tool` (MCP-callable, see `n8n-extending-mcp-official`). For the full discovery protocol, see `n8n-subworkflows-official` `references/NAMING_AND_DISCOVERY.md`.

Instance and user conventions overrule all of the above. If `list_tags` shows an existing vocabulary, or the user prefers different names, casing, or categories, match theirs. Consistency within an instance beats this skill's defaults.

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
