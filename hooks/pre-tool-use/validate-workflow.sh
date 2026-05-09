#!/usr/bin/env bash
# Fires before validate_workflow. Validation is the gate before publish.
# This is where Claude needs lifecycle + connections discipline most.
exec "$(dirname "$0")/_emit.sh" "lifecycle-connections" \
"Before validating, run the antipattern scan from n8n-workflow-lifecycle references/VALIDATION_CHECKLIST.md section 2.5 node-by-node: Set nodes feeding only 1 consumer should be inlined; Code nodes doing pure data shaping should be Edit Fields with arrow functions; Merges with 3+ wires need numberOfInputs set explicitly; \$json.x in branchy workflows should be \$('Node').item.json.x; sub-workflow triggers should be Define Below mode unless receiving binary; DateTime nodes should be Luxon expressions. validate_workflow does not catch any of these; only the manual scan does."
