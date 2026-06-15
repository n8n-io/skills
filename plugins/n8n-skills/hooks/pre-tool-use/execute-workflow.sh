#!/usr/bin/env bash
# Fires before execute_workflow. Production runs are where unhandled errors
# bite, so surface error-handling discipline before pulling the trigger.
exec "$(dirname "$0")/_emit.sh" "error-handling" \
"Before executing: invoke the n8n-error-handling skill via the Skill tool. API-shaped workflows (webhook to respond) handle errors on every fallible node. Map status codes to cause: caller's fault is 4xx, your fault is 5xx. Confirm error branches are wired and respond-to-webhook returns a structured response with the right code on failure paths."
