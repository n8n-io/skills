#!/usr/bin/env bash
# Fires before create_workflow_from_code. New workflow means readability
# and subworkflow-reuse decisions need to happen before code lands.
exec "$(dirname "$0")/_emit.sh" "lifecycle-subworkflows" \
"Before creating: invoke n8n-workflow-lifecycle-official (node groups for logical steps, sticky notes, descriptions, naming) and n8n-subworkflows-official (search existing sub-workflows by tag before duplicating logic) via the Skill tool."
