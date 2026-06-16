#!/usr/bin/env bash
# Fires before create_workflow_from_code. New workflow means readability
# and subworkflow-reuse decisions need to happen before code lands.
# TEMPORARY: when search_workflows exposes tag-based filtering, update the
# message below to mention tags as the primary discovery mechanism.
exec "$(dirname "$0")/_emit.sh" "lifecycle-subworkflows" \
"Before creating: invoke n8n-workflow-lifecycle (sticky notes, descriptions capturing the why, naming) and n8n-subworkflows (search existing reusable sub-workflows by name/prefix before duplicating logic) via the Skill tool."
