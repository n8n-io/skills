#!/usr/bin/env bash
# Fires before update_workflow. Updates often touch connections, which is
# where the most subtle bugs live (silent dropped wires, merge index off-by-one).
exec "$(dirname "$0")/_emit.sh" "connections" \
"Before updating: invoke the n8n-connections skill via the Skill tool. Verify multi-input/output wiring with get_workflow_details after the update. validate_workflow misses the .to()-inside-.add() trap."
