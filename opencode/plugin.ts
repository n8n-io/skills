// opencode/plugin.ts
// OpenCode plugin for n8n-skills: bridges the existing bash hooks into
// OpenCode's plugin event system. See opencode/README.md for installation.
//
// Requires: OpenCode with @opencode-ai/plugin, bash, jq (for hook scripts).

import type { Plugin } from "@opencode-ai/plugin"
import { readFileSync, existsSync } from "fs"
import { join, dirname } from "path"

// Type augmentation for Bun's import.meta.dir (not in standard Node.js types)
declare global {
  interface ImportMeta {
    dir: string
  }
}

// Resolve repo root from this file's location (plugin is at <root>/opencode/plugin.ts)
// Bun provides import.meta.dir as the directory of the current module
const REPO_ROOT = join(dirname(import.meta.dir), "..")
const HOOKS_DIR = join(REPO_ROOT, "hooks")
const META_SKILL_PATH = join(REPO_ROOT, "skills", "using-n8n-skills-official", "SKILL.md")

// Cache the meta-skill content (read once on first use, reuse thereafter)
let metaSkillCache: string | null = null
function getMetaSkill(): string | null {
  if (metaSkillCache === null && existsSync(META_SKILL_PATH)) {
    metaSkillCache = readFileSync(META_SKILL_PATH, "utf-8")
  }
  return metaSkillCache
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

export const N8nSkillsPlugin: Plugin = async ({ $ }) => {
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
    // OpenCode's tool.execute.after exposes output.output (the tool result string)
    // We append the hook's additionalContext to the result so the agent sees it
    // and can adjust before its next action. This covers both PreToolUse
    // (reminders about to be relevant) and PostToolUse (analysis of what just ran)
    "tool.execute.after": async (input, output) => {
      // PreToolUse reminders: fire after the tool returns so the agent sees
      // the reminder in the tool result and applies it on the next action
      for (const hook of PRE_TOOL_HOOKS) {
        if (!isN8nTool(input.tool, hook.match)) continue
        try {
          // Construct a JSON payload compatible with the bash hooks' stdin format
          // The hooks expect Claude Code's hook input shape: { session_id, tool_input }
          const hookInput = JSON.stringify({
            session_id: input.sessionID,
            tool_input: input.args,
          })
          const scriptPath = join(HOOKS_DIR, hook.script)
          // Pipe the JSON to the bash script and capture stdout
          const result = await $`echo ${hookInput} | bash ${scriptPath}`.text()
          // Parse the hook's JSON output to extract additionalContext
          const parsed = JSON.parse(result)
          const ctx = parsed.hookSpecificOutput?.additionalContext
          if (ctx) {
            output.output += `\n\n--- n8n skill reminder ---\n${ctx}`
          }
        } catch {
          // Silent failure: never block tool execution if a hook fails
        }
        break // Only one pre-tool hook matches per tool call
      }

      // PostToolUse analysis: runs after validate_workflow to suggest
      // which skills to load based on the node types detected in the code
      for (const hook of POST_TOOL_HOOKS) {
        if (!isN8nTool(input.tool, hook.match)) continue
        try {
          const hookInput = JSON.stringify({
            session_id: input.sessionID,
            tool_input: input.args,
          })
          const scriptPath = join(HOOKS_DIR, hook.script)
          const result = await $`echo ${hookInput} | bash ${scriptPath}`.text()
          const parsed = JSON.parse(result)
          const ctx = parsed.hookSpecificOutput?.additionalContext
          if (ctx) {
            output.output += `\n\n--- n8n post-validation analysis ---\n${ctx}`
          }
        } catch {
          // Silent failure
        }
        break
      }
    },
  }
}
