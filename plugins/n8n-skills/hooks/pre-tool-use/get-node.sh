#!/usr/bin/env bash
# Fires before get_node_types. Two jobs:
#
# 1. Generic node-config reminder. Fires once per session (deduped by marker).
# 2. High-risk-node-specific reminders: Set, Code, Merge, splitInBatches
#    (Loop Over Items), DateTime, dataTable. These fire EVERY time the agent
#    looks up the node type, not just once per session. Reasoning: a re-lookup
#    of one of these node types is almost always the agent considering ANOTHER
#    instance of the antipattern. Once-per-session dedup misses every Code/Set
#    decision after the first.
#
# Why per-node hooks rather than just the meta-skill: the agent reads the
# meta-skill at session start, decides on an approach, and slips during build.
# Catching the node-type lookup is the closest moment to the actual decision
# that we have a hard signal for.

set -uo pipefail

INPUT="$(cat)"

if ! command -v jq >/dev/null 2>&1; then
  exit 0
fi

SESSION_ID="$(echo "${INPUT}" | jq -r '.session_id // empty' 2>/dev/null)"
[ -z "${SESSION_ID}" ] && exit 0

# Extract all .name fields from the requested node IDs. Handles both the
# typed-object form ({ name, resource, operation }) and the raw-string form.
NODE_NAMES="$(echo "${INPUT}" | jq -r '
  (.tool_input.ids // []) |
  map(if type == "object" then .name else . end) |
  .[]
' 2>/dev/null)"

STATE_DIR="${TMPDIR:-/tmp}/n8n-skills-state"
mkdir -p "${STATE_DIR}" 2>/dev/null || exit 0

has_marker() {
  [ -f "${STATE_DIR}/${SESSION_ID}-$1.loaded" ]
}

set_marker() {
  touch "${STATE_DIR}/${SESSION_ID}-$1.loaded" 2>/dev/null
}

matches() {
  echo "${NODE_NAMES}" | grep -qiE "$1"
}

WARNINGS=""

# Generic node-config reminder. Deduped: fires only on the first
# get_node_types call per session, since this reminder is general-purpose
# and re-firing it adds nothing.
if ! has_marker "node-config"; then
  WARNINGS+="Before configuring nodes: invoke the n8n-node-configuration skill via the Skill tool. Operation-aware configuration, property dependencies, never assume parameters. Always inspect via the type definitions you're about to fetch."
  set_marker "node-config"
fi

# High-risk-node warnings: NOT deduped. Each lookup fires the warning fresh.
# The agent re-considering Code, Set, Merge, etc. mid-build is the exact
# moment we want to surface these reminders, regardless of whether they
# fired earlier in the session.

if matches '(^|\.)set$'; then
  WARNINGS+="

[Set node detected in this lookup]
STOP and invoke the n8n-expressions skill via the Skill tool NOW. The most common antipattern in this whole pack: Set nodes feeding only ONE downstream consumer.

If the only purpose of this Set node is to map fields for the next node (before an Insert/Update Data Table node, before an Email/Slack body, before a Respond to Webhook, etc.), DELETE the Set node and put the expressions DIRECTLY in the next node's parameter slots. The Data Table Insert node has expression slots for every column. The Email node has an expression slot for the body. Use them.

A Set node is only justified when 2+ downstream consumers reference the same derived value, OR when branches converge and need a stable shape (use a NoOp node in that case for naming, not a Set), OR as the FINAL node of a sub-workflow shaping the return contract (the implicit consumer is every caller, so it earns its place as the API boundary; name it 'Return')."
fi

if matches '(^|\.)code$'; then
  WARNINGS+="

[Code node detected in this lookup]
STOP and invoke the n8n-code-nodes skill via the Skill tool NOW. Decision order: expression first, then arrow function inside Edit Fields, THEN Code node only if those genuinely cannot do the job.

Default to JavaScript. Only use Python when the user explicitly asked for it (\"use Python\", \"I'm a Python shop\"). The user mentioning data analysis is NOT an explicit ask.

Valid Code-node use cases are narrow: multi-source aggregation across the whole dataset (\$('A').all() AND \$('B').all() in one place), external libraries (lodash etc.), or stateful transforms. NOT \"transform one item's fields with .map/.filter/.find\", that's Edit Fields with an arrow function expression, much cleaner.

DO NOT reach for Code just because the operation involves crypto or XML. Both have native n8n nodes:
- Crypto/HMAC/hashing: use the Crypto node (n8n-nodes-base.crypto). It does SHA, HMAC, encrypt/decrypt, random.
- XML/SOAP/RSS parsing: use the XML node (n8n-nodes-base.xml). After parsing, the result is plain JSON; extract fields with Edit Fields and arrow functions, not another Code node.
These are the most common false positives for 'this needs a Code node'.

PER-OPERATION CHECK. A Code node doing N things probably has N native answers. Read the body and ask for EACH operation:
- this.helpers.httpRequest(...) -> use the HTTP Request node.
- Manual pagination loop (while (more) { start += page; ... }) -> HTTP Request's Pagination option.
- Regex parsing structured response (/<id>...<\\/id>/g, etc.) -> XML node for XML, JSON.parse for JSON.
- crypto.createHash / crypto.createHmac -> Crypto node.

Identity Code nodes (return \$('SomeNode').all() or return \$input.all()) are ALWAYS WRONG. They re-emit upstream data, which means the workflow shape is wrong: the downstream consumer should branch off the upstream directly, or the per-item-vs-aggregate context mismatch should be solved with fan-out, not a Code-node bridge.

Quick tests:
- Can you describe the Code node's job as \"take this one item and...\"? If yes, wrong tool.
- Did you search_nodes for the operation before writing Code? Crypto, XML, regex, date math, HTTP, file I/O all have native nodes or expression-level support."
fi

if matches '(^|\.)merge$'; then
  WARNINGS+="

[Merge node detected in this lookup]
STOP and invoke the n8n-node-configuration skill via the Skill tool, especially references/MERGE_NODE.md, NOW. Two silent failure modes:

1. Merge defaults to 2 inputs. If 3+ sources converge into this Merge, set numberOfInputs explicitly (or the equivalent param on your n8n version) to match. Otherwise the third+ sources silently drop at runtime even though the connection lines are drawn.

2. useDataOfInput is 1-indexed but .input(n) is 0-indexed. Translation rule: useDataOfInput: \"N\" matches .input(N - 1). Off-by-one silently passes data from the wrong branch."
fi

if matches '(^|\.)splitInBatches$'; then
  WARNINGS+="

[Loop Over Items (splitInBatches) detected in this lookup]
STOP and invoke the n8n-loops skill via the Skill tool NOW.

First question: do you actually need this? Default per-item iteration probably handles your case WITHOUT a Loop Over Items node. Just connect the source to the consumer; n8n iterates automatically. Loop Over Items is for: rate limiting (process N at a time with a Wait between), chunked bulk API calls, per-batch error handling, polling a long-running job (with reset: true and a \$runIndex safety ceiling).

Output indexes (this is a common slip): output 0 is DONE (fires once at end), output 1 is LOOP (fires per batch). Easy to wire backwards."
fi

if matches '(^|\.)dateTime$'; then
  WARNINGS+="

[DateTime node detected in this lookup]
STOP. The DateTime node is almost always wrong. Invoke the n8n-expressions skill via the Skill tool NOW.

Date math, formatting, and parsing all work in Luxon expressions inline at the consumer field:
  {{ DateTime.fromISO(\$('Source').item.json.created_at).toFormat('yyyy-MM-dd') }}
  {{ DateTime.now().minus({ days: 7 }).toISO() }}

If you genuinely need the DateTime node (rare), justify it explicitly. Default is: use Luxon in the consumer's expression slot, no separate node."
fi

if matches '(^|\.)dataTable$'; then
  WARNINGS+="

[Data Table node detected in this lookup]
STOP and invoke the n8n-data-tables skill via the Skill tool NOW. Several gotchas that catch people:

1. THREE COLUMNS ARE SYSTEM-MANAGED: id (auto-serial), createdAt, updatedAt. Don't declare them; they're always there. Use them in queries.

2. NO JSON / OBJECT / ARRAY COLUMN TYPES. Only string / number / boolean / date. For nested data, use a string column with JSON.stringify() on write and JSON.parse() on read, postfixed with _object (key_insights_object, topics_object). The postfix is the contract.

3. STORAGE FORMAT IS NOT INTERFACE FORMAT. If your sub-workflow stores arrays as stringified _object columns, parse them BEFORE returning. Don't make callers JSON.parse storage details. Both fresh-path and cached-path returns must produce the SAME natural shape.

4. NO FOREIGN KEYS, but design relationally. Reference rows by id, name columns explicitly (paper_id, customer_id), enforce integrity in workflow logic. n8n won't cascade.

5. THE 'CURRENTLY NO ITEMS EXIST' UI QUIRK is real. SDK saves manual mapping as { mappingMode: 'defineBelow', value: {...} }; the UI's renderer expects schema array too and shows empty without it. Runtime persists fine. Verify via get_workflow_details, don't add a Set node to 'fix' it.

6. ANCHOR DATA REFERENCES TO STABLE NODES. Don't reference \$json.x in column slots when an intermediate (HTTP file response, Extract from File, Aggregate) stripped json. Use \$('Source Node').item.json.x or a Merge convergence anchor. Silent NULL columns in inserts are how this trap surfaces.

7. DON'T ADD A SET NODE BEFORE INSERT to 'shape the input.' Map directly in the Insert node's per-column slots, OR rename upstream fields to enable auto-map mode."
fi

[ -z "${WARNINGS}" ] && exit 0

jq -n --arg ctx "${WARNINGS}" '{
  hookSpecificOutput: {
    hookEventName: "PreToolUse",
    additionalContext: $ctx
  }
}'
