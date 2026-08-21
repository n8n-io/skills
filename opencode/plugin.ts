// opencode/plugin.ts
// OpenCode plugin for n8n-skills: bridges the existing bash hooks into
// OpenCode's plugin event system. See opencode/README.md for installation.
//
// Requires bash and jq on the system (the hook scripts use them). The
// @opencode-ai/plugin import is type-only and erased at build, not a runtime dep.

import type { Plugin } from "@opencode-ai/plugin"
import { readFileSync, existsSync, statSync, readdirSync, rmSync } from "fs"
import { join, dirname } from "path"
import { fileURLToPath } from "url"
import { spawnSync } from "child_process"

// Resolve this file's directory portably. OpenCode loads plugins under different
// runtimes: the CLI on Bun, the desktop app on Node (Electron). Bun exposes
// import.meta.dir but Node does not (it would be undefined and throw here at load,
// silently disabling the plugin), so we derive the path from import.meta.url,
// which is standard in both. Both runtimes resolve the module URL through the
// ~/.config/opencode/plugins symlink to this file's real location, so REPO_ROOT
// points at the actual repo checkout, not the symlink directory.
const PLUGIN_DIR = dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = join(PLUGIN_DIR, "..")
const HOOKS_DIR = join(REPO_ROOT, "hooks")
const SKILLS_DIR = join(REPO_ROOT, "skills")
const META_SKILL_PATH = join(SKILLS_DIR, "using-n8n-skills-official", "SKILL.md")

// Must match STATE_DIR in hooks/pre-tool-use/_emit.sh and hooks/session-start.sh
const STATE_DIR = join(process.env.TMPDIR ?? "/tmp", "n8n-skills-state")

// Everything below fails silently by design, so a broken install (unexpected
// repo layout) would otherwise be undiagnosable.
if (!existsSync(HOOKS_DIR) || !existsSync(META_SKILL_PATH)) {
  console.warn(`[n8n-skills] hooks/ or skills/ not found under ${REPO_ROOT}; skills and reminders will not load`)
}

// Derive tool-suffix -> hook-script tables from hooks/hooks.json (the source
// of truth for Claude Code and Codex) so new matchers there propagate without
// touching this file. Matchers are ^mcp__.*__<suffix>$; only the suffix is
// kept because MCP server names are user-configurable in OpenCode.
function loadHookTable(event: "PreToolUse" | "PostToolUse"): Array<{ match: string; script: string }> {
  try {
    const config = JSON.parse(readFileSync(join(HOOKS_DIR, "hooks.json"), "utf-8"))
    const table: Array<{ match: string; script: string }> = []
    for (const entry of config.hooks?.[event] ?? []) {
      const suffix = /^\^mcp__\.\*__(\w+)\$$/.exec(entry.matcher ?? "")?.[1]
      const script = entry.hooks?.[0]?.command?.split("/hooks/")[1]
      if (suffix && script) table.push({ match: suffix, script })
    }
    return table
  } catch {
    return []
  }
}

const PRE_TOOL_HOOKS = loadHookTable("PreToolUse")
const POST_TOOL_HOOKS = loadHookTable("PostToolUse")
if (PRE_TOOL_HOOKS.length === 0) {
  console.warn("[n8n-skills] no PreToolUse matchers parsed from hooks/hooks.json; tool reminders disabled")
}

// Cache the meta-skill content with mtime-based invalidation.
// On git pull, SKILL.md changes on disk; checking mtime ensures the cache
// is invalidated without requiring an OpenCode restart.
let metaSkillCache: string | null = null
let metaSkillMtime = 0
function getMetaSkill(): string | null {
  try {
    if (!existsSync(META_SKILL_PATH)) return null
    const mtime = statSync(META_SKILL_PATH).mtimeMs
    if (metaSkillCache === null || mtime !== metaSkillMtime) {
      metaSkillCache = readFileSync(META_SKILL_PATH, "utf-8")
      metaSkillMtime = mtime
    }
    return metaSkillCache
  } catch {
    // Transient read failure (file locked, permissions, etc.): degrade
    // gracefully without skill injection rather than rejecting the event
    return null
  }
}

// Match n8n MCP tool names flexibly (server name is user-configurable in OpenCode).
// Matches mcp__n8n_nccio__validate_workflow, n8n_nccio_validate_workflow, etc.
//
// The "n8n" guard is deliberate: suffixes like update_workflow / execute_workflow
// also appear on unrelated CI-automation MCP servers (e.g. GitHub Actions), so
// matching the suffix alone would fire hooks on the wrong tools. The cost is that
// the connected n8n MCP server MUST be named with "n8n" in it (documented in the
// README); if it isn't, no hooks fire. Case-insensitive so a server named "N8N"
// still matches. We can't anchor the suffix to a segment boundary the way Claude's
// ^mcp__.*__<suffix>$ matcher does, because OpenCode tool names use single
// underscores (n8n_nccio_validate_workflow) with no unambiguous server/tool split.
function isN8nTool(toolName: string, suffix: string): boolean {
  return toolName.toLowerCase().includes("n8n") && toolName.endsWith(suffix)
}

// Marker string to prevent duplicate injection into system prompt
const SYSTEM_MARKER = "[n8n-skills: using-n8n-skills-official]"

// Run a bash hook script synchronously with JSON stdin and return parsed output
// Uses spawnSync instead of BunShell ($) for reliability inside OpenCode's plugin context
function runHook(scriptPath: string, hookInput: string): { hookSpecificOutput?: { additionalContext?: string } } | null {
  try {
    const result = spawnSync("bash", [scriptPath], {
      input: hookInput,
      encoding: "utf-8",
      timeout: 10000,
    })
    if (result.status !== 0 || !result.stdout) return null
    return JSON.parse(result.stdout)
  } catch {
    return null
  }
}

// The SDK types say tool.execute.after output is { output: string }, but at
// runtime MCP tools receive the raw MCP CallToolResult ({ content: [...] })
// instead, so duck-type both shapes. See README "MCP tool output shapes".
function appendToOutput(output: any, text: string): void {
  if (typeof output.output === "string") {
    output.output += text
  } else if (Array.isArray(output.content)) {
    output.content.push({ type: "text", text })
  }
}

const N8nSkillsPlugin: Plugin = async (input) => {
  return {
    // 0. Register the bundled skills/ dir into live config so OpenCode discovers
    // the n8n capability skills without the user editing skills.paths. Lets a
    // git/npm plugin install ("plugin": ["n8n-skills@git+..."]) be the whole
    // setup: REPO_ROOT resolves to the installed package, which carries skills/.
    config: async (config: any) => {
      config.skills = config.skills || {}
      config.skills.paths = config.skills.paths || []
      if (!config.skills.paths.includes(SKILLS_DIR)) {
        config.skills.paths.push(SKILLS_DIR)
      }
    },

    // 1. Inject meta-skill into system prompt on every LLM call
    // This replaces Claude Code's SessionStart hook: the meta-skill is always
    // in context, so the agent never needs to manually load it
    "experimental.chat.system.transform": async (_input, output) => {
      const metaSkill = getMetaSkill()
      if (!metaSkill) return
      // Only append once (system array may persist across calls in the same session)
      if (!output.system.some(s => s.includes(SYSTEM_MARKER))) {
        output.system.push(`${SYSTEM_MARKER}\n\n${metaSkill}`)
      }
    },

    // 2. Ensure meta-skill survives compaction, and re-arm the one-shot tool
    // reminders: mirrors hooks/session-start.sh, which wipes this session's
    // markers on compact because the agent's memory of the reminders is gone
    "experimental.session.compacting": async (input, output) => {
      try {
        for (const f of readdirSync(STATE_DIR)) {
          if (f.startsWith(`${input.sessionID}-`) && f.endsWith(".loaded")) {
            rmSync(join(STATE_DIR, f), { force: true })
          }
        }
      } catch {
        // State dir may not exist yet; markers only exist after a hook fired
      }
      const metaSkill = getMetaSkill()
      if (!metaSkill) return
      output.context.push(`## n8n Skills Protocol\n\n${metaSkill}`)
    },

    // 3. After n8n MCP tools return, append hook reminders to tool output.
    // OpenCode has no way to inject model-visible text before a tool runs, so
    // both PreToolUse reminders and PostToolUse analysis land in the result.
    "tool.execute.after": async (input, output) => {
      try {
        // PreToolUse reminders: the agent sees the reminder in the tool
        // result and applies it on the next action
        for (const hook of PRE_TOOL_HOOKS) {
          if (!isN8nTool(input.tool, hook.match)) continue
          const hookInput = JSON.stringify({
            session_id: input.sessionID,
            tool_input: input.args,
          })
          const scriptPath = join(HOOKS_DIR, hook.script)
          const parsed = runHook(scriptPath, hookInput)
          if (parsed?.hookSpecificOutput?.additionalContext) {
            appendToOutput(output, `\n\n--- n8n skill reminder ---\n${parsed.hookSpecificOutput.additionalContext}`)
          }
          break // Only one pre-tool hook matches per tool call
        }

        // PostToolUse analysis: runs after validate_workflow to suggest
        // which skills to load based on the node types detected in the code
        for (const hook of POST_TOOL_HOOKS) {
          if (!isN8nTool(input.tool, hook.match)) continue
          const hookInput = JSON.stringify({
            session_id: input.sessionID,
            tool_input: input.args,
          })
          const scriptPath = join(HOOKS_DIR, hook.script)
          const parsed = runHook(scriptPath, hookInput)
          if (parsed?.hookSpecificOutput?.additionalContext) {
            appendToOutput(output, `\n\n--- n8n post-validation analysis ---\n${parsed.hookSpecificOutput.additionalContext}`)
          }
          break
        }
      } catch {
        // Silent failure: never block tool execution if serialization or hooks fail
      }
    },
  }
}

export default N8nSkillsPlugin
