#!/usr/bin/env bash
# Shared helper for PreToolUse hooks.
# Reads the session_id from stdin (Claude Code hook input is JSON), checks for
# a per-session marker file, and emits a one-shot reminder telling Claude to
# invoke the relevant Skill via the Skill tool.
#
# Usage: _emit.sh <marker-name> <reminder-text>
#
# - marker-name: short identifier used for the dedup marker file. Different
#                tools that point at the same skill should share a marker so
#                we don't double-fire (e.g. validate + create both → "lifecycle").
# - reminder-text: the additionalContext to inject. Keep it terse (~25 tokens).
#
# Always exits 0. Fails silently on any error rather than blocking the tool call.

set -uo pipefail

MARKER_NAME="${1:-}"
REMINDER="${2:-}"

if [[ -z "${MARKER_NAME}" || -z "${REMINDER}" ]]; then
  exit 0
fi

# Read session_id from the hook input JSON on stdin.
INPUT="$(cat)"

if command -v jq >/dev/null 2>&1; then
  SESSION_ID="$(echo "${INPUT}" | jq -r '.session_id // empty' 2>/dev/null)"
elif command -v python3 >/dev/null 2>&1; then
  SESSION_ID="$(echo "${INPUT}" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("session_id",""))' 2>/dev/null)"
else
  exit 0
fi

if [[ -z "${SESSION_ID}" ]]; then
  exit 0
fi

STATE_DIR="${TMPDIR:-/tmp}/n8n-skills-state"
mkdir -p "${STATE_DIR}" 2>/dev/null || exit 0
MARKER="${STATE_DIR}/${SESSION_ID}-${MARKER_NAME}.loaded"

# Already fired this session, exit silently.
if [[ -f "${MARKER}" ]]; then
  exit 0
fi

# Mark first so a downstream JSON encoder failure can't cause double-firing.
touch "${MARKER}" 2>/dev/null || exit 0

if command -v jq >/dev/null 2>&1; then
  jq -n --arg ctx "${REMINDER}" '{
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      additionalContext: $ctx
    }
  }'
elif command -v python3 >/dev/null 2>&1; then
  python3 -c '
import json, sys
ctx = sys.stdin.read()
print(json.dumps({
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "additionalContext": ctx
  }
}))
' <<< "${REMINDER}"
fi
