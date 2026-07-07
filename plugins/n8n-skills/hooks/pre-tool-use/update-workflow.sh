#!/usr/bin/env bash
# Fires before update_workflow. Updates often touch connections, which is
# where the most subtle bugs live (silent dropped wires, merge index off-by-one).
exec "$(dirname "$0")/_emit.sh" "connections" \
"Before updating: verify connections via get_workflow_details after the update. validate_workflow doesn't catch all multi-IO wiring traps. For Merge node specifics see n8n-node-configuration-official references/MERGE_NODE.md; for per-node error outputs see n8n-error-handling-official references/NODE_ERROR_OUTPUTS.md."
