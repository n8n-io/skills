#!/usr/bin/env bash
# Fires AFTER validate_workflow. Validation passing is necessary, not sufficient.
#
# This hook analyzes the SDK code being validated and lists ONLY the relevant
# skills to load based on what's actually in the code. The skill bodies carry
# the depth; this hook just routes the agent to them.
#
# Conditional rules (which skills get suggested):
# - n8n-connections: 3+ nodes OR Merge present OR agent present
# - n8n-expressions: Set OR DateTime OR $json. usage (consolidated reasons)
# - n8n-code-nodes: Code node present
# - n8n-loops: splitInBatches present, OR HTTP Request present (pagination)
# - n8n-subworkflows: executeWorkflowTrigger present
# - n8n-data-tables: dataTable present
# - n8n-credentials-and-security: newCredential() OR HTTP OR webhook OR respond
# - n8n-error-handling: webhook OR respond OR scheduleTrigger OR chatTrigger OR agent
# - n8n-workflow-lifecycle (readability): more than 6 nodes
# - n8n-agents: LangChain agent node present
#
# Header and closing gate fire always.
# Fires every call (no dedup).

set -uo pipefail

if ! command -v jq >/dev/null 2>&1; then
  exit 0
fi

INPUT="$(cat)"
CODE="$(echo "$INPUT" | jq -r '.tool_input.code // empty' 2>/dev/null)"

if [ -z "$CODE" ]; then
  # No code to analyze. Fall back to a short reminder pointing at the full checklist.
  jq -n '{
    hookSpecificOutput: {
      hookEventName: "PostToolUse",
      additionalContext: "[validate_workflow returned. Validation is necessary, not sufficient.] If n8n-workflow-lifecycle is not already in your context, load it via the Skill tool and walk references/VALIDATION_CHECKLIST.md section 2.5 before publish."
    }
  }'
  exit 0
fi

has_str() {
  echo "$CODE" | grep -qF "$1"
}

# Signatures
HAS_SET=0;             has_str "n8n-nodes-base.set"                   && HAS_SET=1
HAS_CODE=0;            has_str "n8n-nodes-base.code"                  && HAS_CODE=1
HAS_MERGE=0;           has_str "n8n-nodes-base.merge"                 && HAS_MERGE=1
HAS_LOOP=0;            has_str "n8n-nodes-base.splitInBatches"        && HAS_LOOP=1
HAS_DATETIME=0;        has_str "n8n-nodes-base.dateTime"              && HAS_DATETIME=1
HAS_SUBWF_TRIGGER=0;   has_str "n8n-nodes-base.executeWorkflowTrigger" && HAS_SUBWF_TRIGGER=1
HAS_DATATABLE=0;       has_str "n8n-nodes-base.dataTable"             && HAS_DATATABLE=1
HAS_AGENT=0;           has_str "n8n-nodes-langchain.agent"            && HAS_AGENT=1
HAS_WEBHOOK=0;         has_str "n8n-nodes-base.webhook"               && HAS_WEBHOOK=1
HAS_HTTP=0;            has_str "n8n-nodes-base.httpRequest"           && HAS_HTTP=1
HAS_RESPOND=0;         has_str "n8n-nodes-base.respondToWebhook"      && HAS_RESPOND=1
HAS_SCHEDULE=0;        has_str "n8n-nodes-base.scheduleTrigger"       && HAS_SCHEDULE=1
HAS_CHAT_TRIGGER=0;    has_str "langchain.chatTrigger"                && HAS_CHAT_TRIGGER=1
HAS_NEWCRED=0;         has_str "newCredential("                       && HAS_NEWCRED=1
HAS_DOLLAR_JSON=0;     echo "$CODE" | grep -qE '\$json\.' && HAS_DOLLAR_JSON=1

# Approximate node count via 'type: "n8n-..."' occurrences. Restrict to n8n-
# prefixed types to avoid double-counting Set node assignment field types
# ('type: "string"', 'type: "number"', etc.) as nodes.
NODE_COUNT=$(echo "$CODE" | grep -oE "type: ['\"]n8n-" 2>/dev/null | wc -l | tr -d ' ')
[ -z "$NODE_COUNT" ] && NODE_COUNT=0

# Composed conditions
INCLUDE_CONNECTIONS=0
[ "$NODE_COUNT" -ge 3 ] || [ $HAS_MERGE -eq 1 ] || [ $HAS_AGENT -eq 1 ] && INCLUDE_CONNECTIONS=1

INCLUDE_LOOP=0
[ $HAS_LOOP -eq 1 ] || [ $HAS_HTTP -eq 1 ] && INCLUDE_LOOP=1

INCLUDE_CREDENTIALS=0
[ $HAS_NEWCRED -eq 1 ] || [ $HAS_HTTP -eq 1 ] || [ $HAS_WEBHOOK -eq 1 ] || [ $HAS_RESPOND -eq 1 ] && INCLUDE_CREDENTIALS=1

INCLUDE_ERROR_HANDLING=0
[ $HAS_WEBHOOK -eq 1 ] || [ $HAS_RESPOND -eq 1 ] || [ $HAS_SCHEDULE -eq 1 ] || [ $HAS_CHAT_TRIGGER -eq 1 ] || [ $HAS_AGENT -eq 1 ] && INCLUDE_ERROR_HANDLING=1

INCLUDE_DESIGN=0
[ "$NODE_COUNT" -gt 6 ] && INCLUDE_DESIGN=1

# Detected summary line (which raw signals fired)
DETECTED=""
[ $HAS_SET -eq 1 ]            && DETECTED+=" Set"
[ $HAS_CODE -eq 1 ]           && DETECTED+=" Code"
[ $HAS_MERGE -eq 1 ]          && DETECTED+=" Merge"
[ $HAS_LOOP -eq 1 ]           && DETECTED+=" Loop"
[ $HAS_DATETIME -eq 1 ]       && DETECTED+=" DateTime"
[ $HAS_SUBWF_TRIGGER -eq 1 ]  && DETECTED+=" SubWorkflowTrigger"
[ $HAS_DATATABLE -eq 1 ]      && DETECTED+=" DataTable"
[ $HAS_AGENT -eq 1 ]          && DETECTED+=" Agent"
[ $HAS_WEBHOOK -eq 1 ]        && DETECTED+=" Webhook"
[ $HAS_HTTP -eq 1 ]           && DETECTED+=" HttpRequest"
[ $HAS_RESPOND -eq 1 ]        && DETECTED+=" RespondToWebhook"
[ $HAS_SCHEDULE -eq 1 ]       && DETECTED+=" Schedule"
[ -z "$DETECTED" ] && DETECTED=" (none of the high-risk node types)"

# Consolidate n8n-expressions reasons (Set, DateTime, $json all route to it)
EXPR_REASONS=""
[ $HAS_SET -eq 1 ]            && EXPR_REASONS+="Set antipattern, "
[ $HAS_DATETIME -eq 1 ]       && EXPR_REASONS+="DateTime → Luxon, "
[ $HAS_DOLLAR_JSON -eq 1 ]    && EXPR_REASONS+="\$json refs, "
EXPR_REASONS="${EXPR_REASONS%, }"

# Build the suggestions list. Each line names a skill + a short reason in parens.
# Skill bodies carry the depth; this hook just routes the agent to load them.
# Use literal newlines inside double quotes to avoid ANSI-C quoting hassles.
SUGGESTIONS=""
[ $INCLUDE_CONNECTIONS -eq 1 ]    && SUGGESTIONS+="
- n8n-connections (3+ nodes / Merge / Agent: multi-IO traps, merge index)"
[ -n "$EXPR_REASONS" ]            && SUGGESTIONS+="
- n8n-expressions (${EXPR_REASONS})"
[ $HAS_CODE -eq 1 ]               && SUGGESTIONS+="
- n8n-code-nodes (Code detected: alternatives review)"
[ $INCLUDE_LOOP -eq 1 ]           && SUGGESTIONS+="
- n8n-loops (Loop Over Items / pagination)"
[ $HAS_SUBWF_TRIGGER -eq 1 ]      && SUGGESTIONS+="
- n8n-subworkflows (sub-workflow trigger: Define Below mode + return-shape rules)"
[ $HAS_DATATABLE -eq 1 ]          && SUGGESTIONS+="
- n8n-data-tables (Data Table: schema, dedup, _object column rules)"
[ $INCLUDE_CREDENTIALS -eq 1 ]    && SUGGESTIONS+="
- n8n-credentials-and-security (auth surface present)"
[ $INCLUDE_ERROR_HANDLING -eq 1 ] && SUGGESTIONS+="
- n8n-error-handling (unattended / webhook workflow: error branches required)"
[ $INCLUDE_DESIGN -eq 1 ]         && SUGGESTIONS+="
- n8n-workflow-lifecycle (>6 nodes: sticky notes, descriptions capturing the why)"
[ $HAS_AGENT -eq 1 ]              && SUGGESTIONS+="
- n8n-agents (LangChain agent detected)"

# Compose final output. If nothing relevant was detected, just header + footer.
if [ -z "$SUGGESTIONS" ]; then
  WARNINGS=$(cat <<EOF
[validate_workflow returned. Validation is necessary, not sufficient.]
Workflow analyzed: ${NODE_COUNT} node(s); detected:${DETECTED}.

No high-risk patterns surfaced. If anything in this workflow is non-trivial, load n8n-workflow-lifecycle via the Skill tool and walk references/VALIDATION_CHECKLIST.md section 2.5 before publish.
EOF
)
else
  WARNINGS=$(cat <<EOF
[validate_workflow returned. Validation is necessary, not sufficient.]
Workflow analyzed: ${NODE_COUNT} node(s); detected:${DETECTED}.

If any of these skills are not already in your context, load them via the Skill tool:${SUGGESTIONS}

This is the gate. Walk these BEFORE publish_workflow. Validation passing means the SDK is well-formed; it does NOT mean the workflow is correct.
EOF
)
fi

jq -n --arg ctx "$WARNINGS" '{
  hookSpecificOutput: {
    hookEventName: "PostToolUse",
    additionalContext: $ctx
  }
}'
