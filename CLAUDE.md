# CLAUDE.md

The contributing guide for everyone editing this repo: humans, AI agents, both. The rules apply regardless of who's writing.


## Open an issue first

Before writing any code, open an issue describing what you want to change and why. PRs without a linked issue get closed without review. 

## The earn-its-place test

Every word in a skill costs context for the LLM that reads it. Keep a sentence only if it does at least one of these:

1. **Constrains the meaning of a term used later.** Example: "in n8n, an agent specifically means the LangChain Agent node with its four sub-node slots." Disambiguates a polysemous word the rest of the doc relies on.
2. **Flags a load-bearing assumption.** A non-obvious constraint, invariant, platform quirk, or workaround a reader would not derive from the surrounding code.
3. **Explains the why behind a rule.** The why is what lets the model judge edge cases. "Use credentials, not text fields" is a rule. "Because text fields are stored in plaintext in workflow exports" is the why.

If a sentence does none of those, cut it.

## What to cut, aggressively

- **Things frontier models already know.** Generic definitions ("a webhook is..."), textbook framings of well-known concepts, basic programming explanations. Keep n8n-specific or project-specific framings, but cut the textbook part.
- **Restated content.** Anything restated from the frontmatter `description`, anything said twice across sections, "as mentioned above" callbacks.
- **Useless intros.** "This skill covers X." "In this guide we will..." "The goal of this document..." The body is loaded only when the skill triggers, by which point the description has already framed the scope. Re-announcing the description in the body is structurally redundant.
- **Fluff.** Filler transitions, hedging that doesn't change behavior, motivational preamble without concrete consequence, "remember to be careful" without specifics.

## What to preserve

- Examples that anchor an abstract rule. Cutting an example to shorten a rule usually loses more than it saves.
- Non-obvious gotchas, even ones that read as basic. "The UI shows 'no items exist' when items do exist" sounds trivial, but it saves an hour of debugging.
- The why behind every rule. If a rule has no why, write the why or cut the rule.

## Style

- **No em-dashes or obvious gptisms** (`—`). Use a comma, colon, parentheses, or two sentences. If a contribution is clearly fully AI it will be auto closed
- **Be very concise.** Every word costs context. Shorten sentences that can be shorter, turn paragraphs into lists when they fit, turn lists into tables when they fit. The earn-its-place test applies to phrasing too.

## Repo structure

- `skills/<name>/SKILL.md`: the router. Cap **500 lines**. Frontmatter: `name`, `description`, optional `allowed-tools`.
- `skills/<name>/references/*.md`: where depth lives. Loaded on demand. A 2,000-line reference is fine if it only loads when needed.
- `skills/<name>/references/examples/*.json`: workflow JSON examples. Reference by relative path, never inline. Every example must validate on a current n8n version.
- `hooks/`: SessionStart and PreToolUse. Don't add new hooks without an issue discussion first.
- `.codex-plugin/plugin.json` + `.agents/plugins/marketplace.json`: the Codex plugin manifest and marketplace entry. Codex reads the repo root directly (`source.path: "./"`), consuming the same canonical `skills/` and `hooks/` as Claude Code (which reads root via `.claude-plugin/`). Requires **Codex ≥ 0.142.0**: PR #28771 added root-plugin marketplace support; earlier versions rejected the repo root and forced a mirrored copy. Codex still won't follow symlinks (openai/codex#24770), but with root support the mirror is unnecessary.

SKILL.md layout:

1. Non-negotiable rules (3-5 bullets max)
2. Decision tree for the domain
3. Pointers: "for X, read references/X.md"
4. Anti-patterns

## Description field rules

Third person. Starts with "Use when...". Includes trigger keywords a real user would type. Cap 1024 chars. Be explicit about every situation that should activate the skill, since Claude undertriggers by default.

## Project facts that aren't derivable from code

- **Temporary workarounds get HTML-comment markers.** Wrap the section with `<!-- TEMPORARY: short description -->` We check each `<!-- TEMPORARY:` after each n8n release.
- **Hooks never inline skill content.** Hooks emit ~25 tokens of additionalContext at most, naming the canonical Skill-tool path so compaction's skill re-attachment works.
- **The plugin doesn't edit user AGENT.md / CLAUDE.md files.** README provides a copy-pasteable snippet for users who want it.

## Don't

- Write multi-line docstrings or comment paragraphs in skill markdown. Comments in skills work the same as comments in code: only when WHY is non-obvious.
- Restate the frontmatter description in the body. The description is always in context, so the body shouldn't re-announce it.
- Reorganize a skill for tone or aesthetics. The diff cost is real (context churn for any agent that reads it next) and the benefit is usually subjective.

## Reporting issues

Four flavors:

- **Bad experience** (skills + MCP produced a frustrating or broken result): file an issue with the agent transcript, the workflow JSON, and what went wrong. Always include both your n8n version and the plugin version.
- **Factual errors** (wrong tool name, outdated parameter, broken example): file an issue with a minimal repro and your n8n version.
- **Version drift** (skills lag the latest n8n): file an issue with your n8n version, the stale skill or reference, and the specific change. Prioritized after each n8n release.
- **Opinion disagreement** (you'd structure this differently): fine, but frame it as a proposal with reasoning. 

## PR checklist

- [ ] Linked to a prior issue with maintainer agreement on the approach
- [ ] Skill description starts with "Use when..." and includes trigger keywords
- [ ] SKILL.md under 500 lines
- [ ] No tokens, real URLs, or real credentials in examples
- [ ] Workflow JSON examples validate on a current n8n version
- [ ] If touching hooks: regression-tested across `startup`, `resume`, `clear`, `compact`
- [ ] If touching the meta-skill MCP tool list: confirmed against a live n8n MCP connection

## License

By contributing, you agree your contribution is licensed under Apache 2.0.

