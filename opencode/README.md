# OpenCode Plugin for n8n Skills

This plugin bridges the n8n-skills bash hooks into [OpenCode](https://opencode.ai)'s plugin event system, achieving feature parity with the Claude Code and Codex plugins.

## What it does

- **Registers the bundled `skills/` directory** with OpenCode via the `config` hook, so the n8n capability skills are discoverable without a manual `skills.paths` entry
- **Injects the `using-n8n-skills-official` meta-skill into the system prompt** on every LLM call, so the agent always has the n8n skill protocol in context
- **Survives compaction**: the meta-skill is injected into compaction context so it persists across context compression
- **Appends hook reminders to n8n MCP tool results**: after each n8n MCP tool call, the corresponding bash hook script fires and its reminder is appended to the tool output

## Prerequisites

- An n8n instance with the instance-level MCP server enabled ([setup guide](https://docs.n8n.io/advanced-ai/mcp/accessing-n8n-mcp-server/))
- OpenCode (plugin event names verified against `@opencode-ai/plugin` 1.4.10 / OpenCode 1.18.15)
- `bash` and `jq` available on the system

Two events used (`experimental.chat.system.transform`, `experimental.session.compacting`) are on OpenCode's experimental plugin surface and may change between versions. If skill injection stops working after an OpenCode upgrade, check these event names against your installed `@opencode-ai/plugin`.

## Installation

See the [main README](../README.md#opencode) for install steps. The OpenCode CLI (one-line config entry) and the desktop app (clone plus a symlink into the plugins folder) install differently.

## How it works

The plugin is glue code. All actual hook logic (node-specific warnings, antipattern detection, skill routing) stays in the existing `hooks/` bash scripts maintained by the n8n team.

| OpenCode event | n8n hook equivalent | What happens |
|----------------|---------------------|--------------|
| `config` | (install-time setup) | Bundled `skills/` dir pushed into `config.skills.paths` so skills are discoverable |
| `experimental.chat.system.transform` | SessionStart | Meta-skill injected into system prompt on every LLM call |
| `experimental.session.compacting` | SessionStart (compact) | Meta-skill injected into compaction context |
| `tool.execute.after` | PreToolUse + PostToolUse | Bash hook scripts fire after n8n MCP tool calls, reminders appended to tool output |

### Tool name matching

The plugin derives the tool-name suffixes and their hook scripts from `hooks/hooks.json` (the same source of truth Claude Code and Codex use), so a new hook added there fires in OpenCode too without editing the plugin. It matches a suffix like `validate_workflow` against the tool name rather than hardcoding an MCP server prefix, since server names are user-configurable in OpenCode.

**The connected n8n MCP server must be named with `n8n` in it** (the default). The suffixes (`update_workflow`, `execute_workflow`, etc.) also appear on unrelated CI-automation MCP servers, so the plugin requires `n8n` in the tool name to avoid firing on the wrong tools. If your server is named without `n8n`, no hooks fire.

### Path resolution

The plugin resolves the repo root from its own file location via `dirname(fileURLToPath(import.meta.url))`, which works on both runtimes OpenCode uses: the CLI (Bun) and the desktop app (Node/Electron). It deliberately avoids Bun's `import.meta.dir`, which is `undefined` under Node and would throw at load, silently disabling the plugin. Both runtimes resolve the module URL through any symlink to the real file, so the root points at the actual install, not the symlink.

### MCP tool output shapes

OpenCode passes different output object shapes to `tool.execute.after` depending on the tool type: built-in tools get `{ output: string }`, but MCP tools get `{ content: [{type, text}] }` (the raw MCP `CallResult`). The plugin's `appendToOutput()` helper detects which shape is present and appends text accordingly. Without this, `output.output += "..."` silently fails for MCP tools because `output.output` is `undefined`.

### Silent failure

All hook calls use `spawnSync` with a 10-second timeout and are wrapped in try/catch. If a hook script fails (missing `jq`, file permissions, timeout, etc.), the tool result passes through unmodified. Hook errors never block tool execution.

## Updating

CLI install: if you pinned a version (`...skills.git#v1.2.0`), bump it in `opencode.jsonc` and restart. If you tracked the branch unpinned, clear the cached package and restart to re-resolve:

```bash
rm -rf ~/.cache/opencode/packages/n8n-skills@git+*
```

Desktop (symlink) install: `git pull` in your clone. Either way, no plugin edits are needed when n8n changes a hook's warnings or adds a new hook to `hooks/hooks.json`: the plugin reads that file at load and shells out to the bash scripts, so `hooks/` stays the single source of truth.
