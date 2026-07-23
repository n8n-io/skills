# OpenCode Plugin for n8n Skills

This plugin bridges the n8n-skills bash hooks into [OpenCode](https://opencode.ai)'s plugin event system, achieving feature parity with the Claude Code and Codex plugins.

## What it does

- **Injects the `using-n8n-skills-official` meta-skill into the system prompt** on every LLM call, so the agent always has the n8n skill protocol in context
- **Survives compaction**: the meta-skill is injected into compaction context so it persists across context compression
- **Appends hook reminders to n8n MCP tool results**: after each n8n MCP tool call, the corresponding bash hook script fires and its reminder is appended to the tool output

## Prerequisites

- An n8n instance with the instance-level MCP server enabled ([setup guide](https://docs.n8n.io/advanced-ai/mcp/accessing-n8n-mcp-server/))
- OpenCode with `@opencode-ai/plugin` support
- `bash` and `jq` available on the system

## Installation

### 1. Clone the repo

```bash
git clone https://github.com/n8n-io/skills.git ~/.local/share/opencode/n8n-skills
```

### 2. Symlink the plugin

```bash
# Create the plugins directory if it doesn't exist
mkdir -p ~/.config/opencode/plugins/

# Symlink the plugin file (auto-loaded by OpenCode on startup)
ln -s ~/.local/share/opencode/n8n-skills/opencode/plugin.ts \
      ~/.config/opencode/plugins/n8n-skills-hooks.ts
```

### 3. Add skills path to OpenCode config

In your `opencode.jsonc`, add the skills path:

```jsonc
{
  "skills": {
    "paths": [
      "/home/youruser/.local/share/opencode/n8n-skills/skills"
    ]
  }
}
```

### 4. Add the AGENTS.md snippet

In your project's `AGENTS.md` (or `~/.config/opencode/AGENTS.md` for global):

```markdown
This project uses n8n. When working with workflows, nodes, expressions, or
the n8n MCP tools, always start by loading the `using-n8n-skills-official` meta-skill
and follow its routing into the matching capability skill before acting.
```

### 5. Restart OpenCode

The plugin loads automatically on the next OpenCode startup.

## How it works

The plugin is glue code. All actual hook logic (node-specific warnings, antipattern detection, skill routing) stays in the existing `hooks/` bash scripts maintained by the n8n team.

| OpenCode event | n8n hook equivalent | What happens |
|----------------|---------------------|--------------|
| `experimental.chat.system.transform` | SessionStart | Meta-skill injected into system prompt on every LLM call |
| `experimental.session.compacting` | SessionStart (compact) | Meta-skill injected into compaction context |
| `tool.execute.after` | PreToolUse + PostToolUse | Bash hook scripts fire after n8n MCP tool calls, reminders appended to tool output |

### Tool name matching

The plugin matches tool names flexibly (`toolName.includes("n8n") && toolName.endsWith("validate_workflow")`) rather than hardcoding MCP server name prefixes, since MCP server names are user-configurable in OpenCode.

### Path resolution

The plugin uses `import.meta.dir` (Bun) to resolve the repo root relative to its own file location. This means it works regardless of where the repo is cloned (no hardcoded paths).

### MCP tool output shapes

OpenCode passes different output object shapes to `tool.execute.after` depending on the tool type: built-in tools get `{ output: string }`, but MCP tools get `{ content: [{type, text}] }` (the raw MCP `CallResult`). The plugin's `appendToOutput()` helper detects which shape is present and appends text accordingly. Without this, `output.output += "..."` silently fails for MCP tools because `output.output` is `undefined`.

### Silent failure

All hook calls use `spawnSync` with a 10-second timeout and are wrapped in try/catch. If a hook script fails (missing `jq`, file permissions, timeout, etc.), the tool result passes through unmodified. Hook errors never block tool execution.

## Updating

```bash
cd ~/.local/share/opencode/n8n-skills
git pull origin main
```

This updates skills, hooks, and the plugin together. No plugin updates needed when n8n adds new node warnings or antipattern checks (the bash hooks are the source of truth).

## License

Apache 2.0 (same as the rest of the repo)
