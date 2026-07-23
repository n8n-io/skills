// opencode/plugin.ts
// OpenCode plugin for n8n-skills: bridges the existing bash hooks into
// OpenCode's plugin event system. See opencode/README.md for installation.
//
// Requires: OpenCode with @opencode-ai/plugin, bash, jq (for hook scripts).

import type { Plugin } from "@opencode-ai/plugin"
import { readFileSync, existsSync, realpathSync, statSync } from "fs"
import { join, dirname } from "path"
import { spawnSync } from "child_process"

// Type augmentation for Bun's import.meta.dir (not in standard Node.js types)
declare global {
  interface ImportMeta {
    dir: string
  }
}

// Resolve the real path of this module in case it's loaded via symlink
// (e.g. ~/.config/opencode/plugins/n8n-skills-hooks.ts -> ~/.../n8n-skills/opencode/plugin.ts)
// Bun resolves import.meta.dir to the symlink target, but realpathSync ensures
// correctness even if a future runtime changes that behaviour.
const PLUGIN_DIR = (() => {
  try {
    return dirname(realpathSync(import.meta.dir + "/plugin.ts"))
  } catch {
    return import.meta.dir
  }
})()

// Resolve repo root from this file's location (plugin is at <root>/opencode/plugin.ts)
const REPO_ROOT = join(PLUGIN_DIR, "..")
const HOOKS_DIR = join(REPO_ROOT, "hooks")
const META_SKILL_PATH = join(REPO_ROOT, "skills", "using-n8n-skills-official", "SKILL.md")

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

// Match n8n MCP tool names flexibly (server name is user-configurable in OpenCode)
// Matches patterns like: mcp__n8n_nccio__validate_workflow, n8n_nccio_validate_workflow, etc.
function isN8nTool(toolName: string, suffix: string): boolean {
  return toolName.includes("n8n") && toolName.endsWith(suffix)
}

// PreToolUse hooks: reminders to inject after the tool returns
// Each entry maps an n8n MCP tool name suffix to the corresponding bash hook script
const PRE_TOOL_HOOKS: Array<{ match: string; script: string }> = [
  { match: "validate_workflow",         script: "pre-tool-use/validate-workflow.sh" },
  { match: "create_workflow_from_code", script: "pre-tool-use/create-workflow.sh" },
  { match: "update_workflow",           script: "pre-tool-use/update-workflow.sh" },
  { match: "get_node_types",            script: "pre-tool-use/get-node.sh" },
  { match: "execute_workflow",          script: "pre-tool-use/execute-workflow.sh" },
  { match: "test_workflow",             script: "pre-tool-use/test-workflow.sh" },
]

// PostToolUse hooks: analysis that runs after the tool returns
const POST_TOOL_HOOKS: Array<{ match: string; script: string }> = [
  { match: "validate_workflow", script: "post-tool-use/validate-workflow.sh" },
]

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

// Append text to the tool result output, handling both output shapes:
// - Built-in tools: output.output is a string (mutate with +=)
// - MCP tools: output.content is an array of {type:"text", text:string}
//   (push a new content entry)
// Without this, output.output += "..." silently fails for MCP tools
// because output.output is undefined.
function appendToOutput(output: any, text: string): void {
  if (typeof output.output === "string") {
    output.output += text
  } else if (Array.isArray(output.content)) {
    output.content.push({ type: "text", text })
  }
}

const N8nSkillsPlugin: Plugin = async (input) => {
  return {
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

    // 2. Ensure meta-skill survives compaction
    // OpenCode compacts long sessions; this injects the meta-skill into the
    // compaction context so the protocol survives context compression
    "experimental.session.compacting": async (_input, output) => {
      const metaSkill = getMetaSkill()
      if (!metaSkill) return
      output.context.push(`## n8n Skills Protocol\n\n${metaSkill}`)
    },

    // 3. After n8n MCP tools return, append hook reminders to tool output
    // OpenCode passes different output shapes to tool.execute.after:
    // built-in tools get { output: string }, MCP tools get { content: [{type, text}] }.
    // appendToOutput() handles both. This covers both PreToolUse
    // (reminders about to be relevant) and PostToolUse (analysis of what just ran).
    "tool.execute.after": async (input, output) => {
      try {
        // PreToolUse reminders: fire after the tool returns so the agent sees
        // the reminder in the tool result and applies it on the next action
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
