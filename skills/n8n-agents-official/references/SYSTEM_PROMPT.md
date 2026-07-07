# System prompts

The system prompt is the load-bearing config of an agent. Most "agent isn't doing what I want" problems trace back to a system prompt that's too long, too vague, or mixing concerns.

This file is opinionated: keep system prompts focused on **persona and global behavior**, push tool-specific instructions into tool descriptions, and iterate the prompt.

## What the system prompt is for

1. **Persona / role.** Who, scope, tone.
2. **Global output rules.** Format conventions, display protocols (e.g. "show images via `![]()` markdown"), language.
3. **Refusal and safety behavior.** What the agent should NOT do. Prefer specific bounds over generic boilerplate.
4. **Universal context.** Current date, user's name/role, company or product context.
5. **Inter-tool flow rules.** "After generating, always show via display protocol", "Confirm before destructive operations". These touch multiple tools.
6. **File handling injection.** When chat includes uploaded files, inject storage keys so the agent can reference them in tool calls. See `n8n-binary-and-data-official` `AGENT_TOOL_BINARY.md`.

What it's NOT for: per-tool usage instructions. Those go in the tool's description.

## Always include the current date

```
Current date: {{ $now }}
```

## The modular split

Here's the mental model:

```
System prompt   →  Persona, global behavior, format rules, file handling
Tool description → How to use THIS specific tool, its parameters, when to choose it over others
fromAi description → What value to put in this specific parameter
```

Why this split:

- **Reuse.** A well-described tool works in any agent. System prompt stays specific to the role.
- **Token efficiency.** The model only "loads" tool details when considering that tool. Per-tool instructions in the system prompt burn tokens every turn.
- **Maintainability.** Update one tool description, not a paragraph buried in a 5000-token prompt.

### What to move where: examples

| Was in the system prompt | Better location |
|---|---|
| "When using the Generate Image tool, prefer realistic photography aesthetics over `8k cinematic` keywords" | `Generate Image` tool description |
| "When the user uploads an image and asks for background changes, do not generate a new image, edit the existing one" | `Edit Image` tool description (and possibly `Generate Image` description as a "do not use" boundary) |
| "Always preserve focus depth when editing backgrounds, match the original's blur level" | `Edit Image` tool description |
| "Use 9:16 aspect ratio for video tools" | `Generate Video` tool description |
| "Respond with markdown image embeds: `![alt](url)`" | System prompt (it's a global display rule) |
| "Refuse to generate images of real people without consent" | System prompt (global safety) |
| "Today is 2026-04-25" | System prompt (universal context) |

The first four moved out, and the last three stay in.

## Storing the prompt

Inline (the system prompt typed directly into the node parameter) is fine for a first agent or any prompt that lives in one place. A 1500-token inline system prompt is a normal shape, and reaching for Data Tables, git-versioned files, or template engines on day one can be overkill. Don't push first-time agent builders toward externalization.

The real reason to externalize is **piecing**, not prompt length. Reusable chunks of context, things like `COMPANY_DESCRIPTION`, `MARKET_FIT`, `BRAND_VOICE`, `COMPETITIVE_ANALYSIS`, `CURRENT_PROMOTION`, each get one canonical home, and every prompt that needs them references that home instead of copying. Suggest this pattern when you see one of:

- Multiple agents share the same context (same product description, same compliance language).
- Pieces drift on their own cadence: `COMPANY_DESCRIPTION` changes once a quarter, `CURRENT_PROMOTION` changes weekly.
- A non-engineer owns part of the prompt (marketing owns brand voice, legal owns disclosures, product owns the feature list).
- You want to A/B test one chunk without touching the rest.

If none apply, stay inline. Mid-prompt restructures cost more than they save when there's no second consumer to pay them back.

### How piecing works

The "template" is the system prompt expression itself. Load each chunk at workflow start (one node per chunk: a Data Table `Get Row`, an HTTP fetch, a Set node, whatever fits the source), then reference them inline in the agent's `systemMessage` where they should appear:

```
=You are the assistant for {{ $('Company Description').first().json.value }}.

## Market positioning
{{ $('Market Fit').first().json.value }}

## Brand voice
{{ $('Brand Voice').first().json.value }}

Current date: {{ $now }}
User: {{ $('Lookup').first().json.name }}
```

Mix where chunks come from:

- **Data Table**: default for chunks shared across agents. Editable in UI, queryable, can be version-stamped.
- **n8n Variables** (`$vars.X`, paid plans only): instance or project wide key/value strings referenced inline without a node call. Right when the chunk is a short shared value (brand name, default tone, support email) and Variables are available on the paid plans.
- **Computed at run time**: `$now`, current user, available files. Just an expression, no storage needed.

## File handling injection

See `n8n-binary-and-data-official` `AGENT_TOOL_BINARY.md` for how to handle binary in agents

## Common patterns to include or exclude

### Include

- **Display protocols** for output that needs specific formatting (markdown image syntax, link format, code block conventions).
- **Conversational style cues** for user-facing agents: "ask one clarifying question before destructive actions", "confirm before sending external messages".
- **Boundaries** unique to this agent: "only answer questions about [domain X], otherwise redirect".
- **Universal context** that changes per execution (date, user identity, files).

### Exclude

- **Per-tool usage docs.** Move to tool descriptions.
- **Generic safety language.** Built in. Reinforcing adds tokens without changing behavior. Reserve for specific risks.
- **"You are a helpful assistant" preamble.** Replace with a specific role.
- **Lengthy examples that aren't carrying their weight.** One sharp example beats five mediocre ones.

## Iteration loop

Treat the system prompt like code:

1. Run the agent on representative inputs.
2. Note where it does the wrong thing.
3. Decide: system-prompt fix, tool-description fix, or downstream-validation fix?
4. Make the smallest change that addresses it.
5. Re-test on the same inputs PLUS one or two new ones.
6. Watch for regressions on previously-working inputs.

Most "the agent doesn't follow my instructions" issues are conflicts between system prompt, tool descriptions, and model defaults. Resolve those conflicts first.

## Anti-patterns

| Anti-pattern | Symptom | Fix |
|---|---|---|
| "You are a helpful assistant" + no specifics | Generic responses, agent has no identity | Replace with a specific role and scope |
| 5000-token prompt with sections per tool | Token cost, slow responses, hard to edit | Move tool sections to tool descriptions |
| Hardcoded date / "current year" | Stale immediately | Inject `$now.toFormat(...)` at runtime |
| Stack of `DON'T` rules | Model gets defensive, refuses too eagerly | Frame as positive instructions where possible |
| Multiple "examples" pasted in | Cargo-cult, rarely earns its tokens | One sharp example or none |
| Per-execution context buried in the system prompt | Hard to update | Build the prompt from a template + variables |
