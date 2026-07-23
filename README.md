# Official n8n Skills

<!-- TODO: add 15-second demo gif before the tagline -->

**n8n's MCP makes the connection. n8n Skills set the standard.**

Built by the n8n team to pair with n8n's instance-level MCP server. Your coding agent can now build and edit workflows through the MCP, and the skills enable it to get it right the first time.

**What's inside:**

- **13 capability skills** covering best practices across the full workflow lifecycle: sub-workflow reuse, expressions, loops and pagination, AI agents, error handling, credentials, Data Tables, debugging, and more.
- **50+ reference docs and worked examples** loaded on demand: per-node gotchas, decision trees, and copy-pasteable workflow JSON / TypeScript SDK snippets.
- **A SessionStart hook** that loads the protocol on every session, including a compact reference for every n8n MCP tool.
- **PreToolUse hooks** that nudge your agent to consult the matching skill before high-impact MCP calls.

## Prerequisite

An n8n instance (any plan, Cloud or self-hosted) with the instance-level MCP server enabled. See [n8n's MCP setup guide](https://docs.n8n.io/advanced-ai/mcp/accessing-n8n-mcp-server/?utm_source=github&utm_medium=readme&utm_campaign=official-skills-repo).

## Install

Pick your platform:

- [Claude Code](#claude-code)
- [Codex](#codex)
- [OpenCode](#opencode)
- [Other platforms](#other-platforms)

### Claude Code

Inside Claude Code, run these one at a time:

```bash
/plugin marketplace add n8n-io/skills
```

```bash
/plugin install n8n-skills@n8n-io
```

Restart Claude Code. Skills load automatically.

### Codex

Run these one at a time:

```bash
codex plugin marketplace add n8n-io/skills
```

```bash
codex plugin add n8n-skills@n8n-io
```

> Requires **Codex ≥ 0.142.0** (root-plugin marketplace support). Works in both the Codex CLI and the Codex mode of the ChatGPT desktop app.

Restart Codex. On first run, Codex prompts to review and trust the plugin's hooks, approve them so the SessionStart, PreToolUse, and PostToolUse reminders fire. Skills load automatically.

### OpenCode

Clone the repo and symlink the plugin:

```bash
git clone https://github.com/n8n-io/skills.git ~/.local/share/opencode/n8n-skills
mkdir -p ~/.config/opencode/plugins/
ln -s ~/.local/share/opencode/n8n-skills/opencode/plugin.ts \
      ~/.config/opencode/plugins/n8n-skills-hooks.ts
```

Add the skills path to your `opencode.jsonc`:

```jsonc
{
  "skills": {
    "paths": [
      "/home/youruser/.local/share/opencode/n8n-skills/skills"
    ]
  }
}
```

Restart OpenCode. The plugin injects the `using-n8n-skills-official` meta-skill into the system prompt on every session and fires the bash hooks after n8n MCP tool calls. See [`opencode/README.md`](./opencode/README.md) for details.

### Other platforms

> *Each coding agent has its own skill format. Follow your platform's docs for installing skills*

[skills.sh](https://skills.sh) handles a few popular platforms via `npx`. From your project folder:

```bash
npx skills add n8n-io/skills
```

Compatibility varies by agent. Check skills.sh for support on your specific platform.

#### Then add a snippet to your `AGENTS.md`

```markdown
This project uses n8n. When working with workflows, nodes, expressions, or
the n8n MCP tools, always start by loading the `using-n8n-skills-official` meta-skill
and follow its routing into the matching capability skill before acting.
```

> *The plugins ship a SessionStart hook that loads the entry-point skill for you. Plain skill installs don't have that hook, so the snippet is what cues your agent to start every n8n task by loading `using-n8n-skills-official`.*

## Skills inside

| Skill | When it activates |
|---|---|
| `n8n-workflow-lifecycle-official` | Starting, designing, organizing, or finishing a workflow |
| `n8n-subworkflows-official` | Anything reusable, multi-step builds |
| `n8n-extending-mcp-official` | Need capabilities the MCP doesn't have |
| `n8n-expressions-official` | Writing `{{}}`, `$json`, `$node` |
| `n8n-node-configuration-official` | Configuring any node |
| `n8n-code-nodes-official` | Custom logic, Code node consideration |
| `n8n-loops-official` | Loops, batching, paginated APIs |
| `n8n-agents-official` | LangChain Agent node, tools, system prompts, structured output |
| `n8n-error-handling-official` | Webhook APIs, production workflows |
| `n8n-credentials-and-security-official` | Auth, API keys, tokens |
| `n8n-binary-and-data-official` | Files, images, attachments, vision |
| `n8n-data-tables-official` | Data Tables: schemas, dedup, persistent state |
| `n8n-debugging-official` | Things break |

A 14th meta-skill, `using-n8n-skills-official`, is loaded by the SessionStart hook in plugins and routes your agent to the right capability skill on every n8n task.

## How it works

Each skill is a markdown file. Frontmatter tells the agent when to load it. The SessionStart hook routes to the right one on every n8n task; PreToolUse hooks pull the matching skill back into context before high-impact MCP calls. It's all just markdown. Disagree with a call? Fork it.

## Related

- [Official n8n MCP docs](https://docs.n8n.io/advanced-ai/mcp/accessing-n8n-mcp-server/?utm_source=github&utm_medium=readme&utm_campaign=official-skills-repo)
- [n8n MCP tools reference](https://docs.n8n.io/advanced-ai/mcp/mcp_tools_reference/?utm_source=github&utm_medium=readme&utm_campaign=official-skills-repo)
- [n8n](https://n8n.io?utm_source=github&utm_medium=readme&utm_campaign=official-skills-repo)

## Contributing

See [CLAUDE.md](./CLAUDE.md), the contributing guide for humans and AI agents alike. **Open an issue first.** We don't accept PRs that haven't been discussed in an issue.

**Looking for contributors:** feature parity plugins for other coding agents (Cursor, OpenCode, etc.). The skills are just markdown, the work is wrapping them so they activate in those harnesses the way they do in Claude Code.

## License

Apache 2.0. See [LICENSE](./LICENSE).
