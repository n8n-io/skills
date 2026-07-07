#!/usr/bin/env bash
# Fires before test_workflow. test_workflow auto-pins triggers + credentialed
# + HTTP Request nodes; Code, Edit Fields, If, Data Tables, Execute Command,
# file ops, and sub-workflow calls run for real. Surface this before the call.
exec "$(dirname "$0")/_emit.sh" "testing" \
"Before testing: invoke the n8n-workflow-lifecycle-official skill via the Skill tool. test_workflow auto-pins triggers, credentialed nodes, and HTTP Request nodes; Code, Edit Fields, If, Data Tables, Execute Command, file ops, and sub-workflow calls run for real. Ask the user before running if any have user-visible side effects. prepare_test_pin_data returns schemas only, you generate the values. Pin data is per-execution only with no visual indicator in the execution viewer; tell the user which nodes were pinned after running."
