#!/usr/bin/env node

import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const hookDirectory = path.dirname(fileURLToPath(import.meta.url));
const pluginRoot =
  process.env.CLAUDE_PLUGIN_ROOT || path.resolve(hookDirectory, "..");
const stateDirectory =
  process.env.N8N_SKILLS_STATE_DIR ||
  path.join(os.tmpdir(), "n8n-skills-state");
const action = process.argv[2] || "";

const reminders = {
  "pre-validate-workflow": {
    marker: "lifecycle-connections",
    text: "Before validating, run the antipattern scan from n8n-workflow-lifecycle-official references/VALIDATION_CHECKLIST.md section 2 node-by-node: Set nodes feeding only 1 consumer should be inlined; Code nodes doing pure data shaping should be Edit Fields with arrow functions; Merges with 3+ wires need numberOfInputs set explicitly; $json.x in branchy workflows should be $('Node').item.json.x; sub-workflow triggers should be Define Below mode unless receiving binary; DateTime nodes should be Luxon expressions. validate_workflow does not catch any of these; only the manual scan does.",
  },
  "pre-create-workflow": {
    marker: "lifecycle-subworkflows",
    text: "Before creating: invoke n8n-workflow-lifecycle-official (node groups for logical steps, sticky notes, descriptions, naming) and n8n-subworkflows-official (search existing sub-workflows by tag before duplicating logic) via the Skill tool.",
  },
  "pre-update-workflow": {
    marker: "connections",
    text: "Before updating: verify connections via get_workflow_details after the update. validate_workflow doesn't catch all multi-IO wiring traps. For Merge node specifics see n8n-node-configuration-official references/MERGE_NODE.md; for per-node error outputs see n8n-error-handling-official references/NODE_ERROR_OUTPUTS.md.",
  },
  "pre-execute-workflow": {
    marker: "error-handling",
    text: "Before executing: invoke the n8n-error-handling-official skill via the Skill tool. API-shaped workflows (webhook to respond) handle errors on every fallible node. Map status codes to cause: caller's fault is 4xx, your fault is 5xx. Confirm error branches are wired and respond-to-webhook returns a structured response with the right code on failure paths.",
  },
  "pre-test-workflow": {
    marker: "testing",
    text: "Before testing: invoke the n8n-workflow-lifecycle-official skill via the Skill tool. test_workflow auto-pins triggers, credentialed nodes, and HTTP Request nodes; Code, Edit Fields, If, Data Tables, Execute Command, file ops, and sub-workflow calls run for real. Ask the user before running if any have user-visible side effects. prepare_test_pin_data returns schemas only, you generate the values. Pin data is per-execution only with no visual indicator in the execution viewer; tell the user which nodes were pinned after running.",
  },
};

function readInput() {
  const raw = fs.readFileSync(0, "utf8").trim();
  return raw ? JSON.parse(raw) : {};
}

function hookOutput(eventName, additionalContext) {
  return {
    hookSpecificOutput: {
      hookEventName: eventName,
      additionalContext,
    },
  };
}

function emit(output) {
  if (output) {
    process.stdout.write(`${JSON.stringify(output)}\n`);
  }
}

function safeSessionId(input) {
  const sessionId = input?.session_id;
  if (typeof sessionId !== "string" || !sessionId) {
    return "";
  }
  if (/^[A-Za-z0-9._-]+$/.test(sessionId)) {
    return sessionId;
  }
  return `~${Buffer.from(sessionId, "utf8").toString("base64url")}`;
}

function markerPath(sessionId, markerName) {
  return path.join(stateDirectory, `${sessionId}-${markerName}.loaded`);
}

function ensureStateDirectory() {
  fs.mkdirSync(stateDirectory, { recursive: true });
}

function setMarker(sessionId, markerName) {
  ensureStateDirectory();
  try {
    fs.writeFileSync(markerPath(sessionId, markerName), "", { flag: "wx" });
    return true;
  } catch (error) {
    if (error?.code === "EEXIST") {
      return false;
    }
    throw error;
  }
}

function hasMarker(sessionId, markerName) {
  return fs.existsSync(markerPath(sessionId, markerName));
}

function resetMarkers(sessionId) {
  if (!sessionId || !fs.existsSync(stateDirectory)) {
    return;
  }
  const prefix = `${sessionId}-`;
  for (const entry of fs.readdirSync(stateDirectory)) {
    if (entry.startsWith(prefix) && entry.endsWith(".loaded")) {
      fs.rmSync(path.join(stateDirectory, entry), { force: true });
    }
  }
}

function sessionStart(input) {
  const sessionId = safeSessionId(input);
  if (
    (input?.source === "clear" || input?.source === "compact") &&
    sessionId
  ) {
    resetMarkers(sessionId);
  }

  try {
    fs.mkdirSync(path.join(os.homedir(), ".cache", "n8n-skills"), {
      recursive: true,
    });
  } catch {
    // The cache is optional and the hook must fail open.
  }

  const metaSkill = path.join(
    pluginRoot,
    "skills",
    "using-n8n-skills-official",
    "SKILL.md",
  );
  if (!fs.existsSync(metaSkill)) {
    return null;
  }
  return hookOutput("SessionStart", fs.readFileSync(metaSkill, "utf8"));
}

function oneShotReminder(input, reminder) {
  const sessionId = safeSessionId(input);
  if (!sessionId || !setMarker(sessionId, reminder.marker)) {
    return null;
  }
  return hookOutput("PreToolUse", reminder.text);
}

function nodeNames(input) {
  const ids = input?.tool_input?.ids;
  if (!Array.isArray(ids)) {
    return [];
  }
  return ids
    .map((id) => (id && typeof id === "object" ? id.name : id))
    .filter((name) => typeof name === "string");
}

function matchesNode(names, expression) {
  return names.some((name) => expression.test(name));
}

function getNodeTypesReminder(input) {
  const sessionId = safeSessionId(input);
  if (!sessionId) {
    return null;
  }

  ensureStateDirectory();
  const names = nodeNames(input);
  const warnings = [];

  if (!hasMarker(sessionId, "node-config")) {
    warnings.push(
      "Before configuring nodes: invoke the n8n-node-configuration-official skill via the Skill tool. Operation-aware configuration, property dependencies, never assume parameters. Always inspect via the type definitions you're about to fetch.",
    );
    setMarker(sessionId, "node-config");
  }

  if (matchesNode(names, /(^|\.)set$/i)) {
    warnings.push(`[Set node detected in this lookup]
STOP and invoke the n8n-expressions-official skill via the Skill tool NOW. The most common antipattern in this whole pack: Set nodes feeding only ONE downstream consumer.

If the only purpose of this Set node is to map fields for the next node (before an Insert/Update Data Table node, before an Email/Slack body, before a Respond to Webhook, etc.), DELETE the Set node and put the expressions DIRECTLY in the next node's parameter slots. The Data Table Insert node has expression slots for every column. The Email node has an expression slot for the body. Use them.

A Set node is only justified when 2+ downstream consumers reference the same derived value, OR when branches converge and need a stable shape (use a NoOp node in that case for naming, not a Set), OR as the FINAL node of a sub-workflow shaping the return contract (the implicit consumer is every caller, so it earns its place as the API boundary; name it 'Return').`);
  }

  if (matchesNode(names, /(^|\.)code$/i)) {
    warnings.push(`[Code node detected in this lookup]
STOP and invoke the n8n-code-nodes-official skill via the Skill tool NOW. Decision order: expression first, then arrow function inside Edit Fields, THEN Code node only if those genuinely cannot do the job.

Default to JavaScript. Only use Python when the user explicitly asked for it ("use Python", "I'm a Python shop"). The user mentioning data analysis is NOT an explicit ask.

Valid Code-node use cases are narrow: multi-source aggregation across the whole dataset ($('A').all() AND $('B').all() in one place), external libraries (lodash etc.), or stateful transforms. NOT "transform one item's fields with .map/.filter/.find", that's Edit Fields with an arrow function expression, much cleaner.

DO NOT reach for Code just because the operation involves crypto or XML. Both have native n8n nodes:
- Crypto/HMAC/hashing: use the Crypto node (n8n-nodes-base.crypto). It does SHA, HMAC, encrypt/decrypt, random.
- XML/SOAP/RSS parsing: use the XML node (n8n-nodes-base.xml). After parsing, the result is plain JSON; extract fields with Edit Fields and arrow functions, not another Code node.
These are the most common false positives for 'this needs a Code node'.

PER-OPERATION CHECK. A Code node doing N things probably has N native answers. Read the body and ask for EACH operation:
- this.helpers.httpRequest(...) -> use the HTTP Request node.
- Manual pagination loop (while (more) { start += page; ... }) -> HTTP Request's Pagination option.
- Regex parsing structured response (/<id>...<\\/id>/g, etc.) -> XML node for XML, JSON.parse for JSON.
- crypto.createHash / crypto.createHmac -> Crypto node.

Identity Code nodes (return $('SomeNode').all() or return $input.all()) are ALWAYS WRONG. They re-emit upstream data, which means the workflow shape is wrong: the downstream consumer should branch off the upstream directly, or the per-item-vs-aggregate context mismatch should be solved with fan-out, not a Code-node bridge.

Quick tests:
- Can you describe the Code node's job as "take this one item and..."? If yes, wrong tool.
- Did you search_nodes for the operation before writing Code? Crypto, XML, regex, date math, HTTP, file I/O all have native nodes or expression-level support.`);
  }

  if (matchesNode(names, /(^|\.)merge$/i)) {
    warnings.push(`[Merge node detected in this lookup]
STOP and invoke the n8n-node-configuration-official skill via the Skill tool, especially references/MERGE_NODE.md, NOW. Two silent failure modes:

1. Merge defaults to 2 inputs. If 3+ sources converge into this Merge, set numberOfInputs explicitly (or the equivalent param on your n8n version) to match. Otherwise the third+ sources silently drop at runtime even though the connection lines are drawn.

2. useDataOfInput is 1-indexed but .input(n) is 0-indexed. Translation rule: useDataOfInput: "N" matches .input(N - 1). Off-by-one silently passes data from the wrong branch.`);
  }

  if (matchesNode(names, /(^|\.)splitInBatches$/i)) {
    warnings.push(`[Loop Over Items (splitInBatches) detected in this lookup]
STOP and invoke the n8n-loops-official skill via the Skill tool NOW.

First question: do you actually need this? Default per-item iteration probably handles your case WITHOUT a Loop Over Items node. Just connect the source to the consumer; n8n iterates automatically. Loop Over Items is for: rate limiting (process N at a time with a Wait between), chunked bulk API calls, per-batch error handling, polling a long-running job (with reset: true and a $runIndex safety ceiling).

Output indexes (this is a common slip): output 0 is DONE (fires once at end), output 1 is LOOP (fires per batch). Easy to wire backwards.`);
  }

  if (matchesNode(names, /(^|\.)dateTime$/i)) {
    warnings.push(`[DateTime node detected in this lookup]
STOP. The DateTime node is almost always wrong. Invoke the n8n-expressions-official skill via the Skill tool NOW.

Date math, formatting, and parsing all work in Luxon expressions inline at the consumer field:
  {{ DateTime.fromISO($('Source').item.json.created_at).toFormat('yyyy-MM-dd') }}
  {{ DateTime.now().minus({ days: 7 }).toISO() }}

If you genuinely need the DateTime node (rare), justify it explicitly. Default is: use Luxon in the consumer's expression slot, no separate node.`);
  }

  if (matchesNode(names, /(^|\.)dataTable$/i)) {
    warnings.push(`[Data Table node detected in this lookup]
STOP and invoke the n8n-data-tables-official skill via the Skill tool NOW. Several gotchas that catch people:

1. THREE COLUMNS ARE SYSTEM-MANAGED: id (auto-serial), createdAt, updatedAt. Don't declare them; they're always there. Use them in queries.

2. NO JSON / OBJECT / ARRAY COLUMN TYPES. Only string / number / boolean / date. For nested data, use a string column with JSON.stringify() on write and JSON.parse() on read, postfixed with _object (key_insights_object, topics_object). The postfix is the contract.

3. STORAGE FORMAT IS NOT INTERFACE FORMAT. If your sub-workflow stores arrays as stringified _object columns, parse them BEFORE returning. Don't make callers JSON.parse storage details. Both fresh-path and cached-path returns must produce the SAME natural shape.

4. NO FOREIGN KEYS, but design relationally. Reference rows by id, name columns explicitly (paper_id, customer_id), enforce integrity in workflow logic. n8n won't cascade.

5. THE 'CURRENTLY NO ITEMS EXIST' UI QUIRK is real. SDK saves manual mapping as { mappingMode: 'defineBelow', value: {...} }; the UI's renderer expects schema array too and shows empty without it. Runtime persists fine. Verify via get_workflow_details, don't add a Set node to 'fix' it.

6. ANCHOR DATA REFERENCES TO STABLE NODES. Don't reference $json.x in column slots when an intermediate (HTTP file response, Extract from File, Aggregate) stripped json. Use $('Source Node').item.json.x or a Merge convergence anchor. Silent NULL columns in inserts are how this trap surfaces.

7. DON'T ADD A SET NODE BEFORE INSERT to 'shape the input.' Map directly in the Insert node's per-column slots, OR rename upstream fields to enable auto-map mode.`);
  }

  return warnings.length
    ? hookOutput("PreToolUse", warnings.join("\n\n"))
    : null;
}

function postValidateWorkflow(input) {
  const code =
    typeof input?.tool_input?.code === "string" ? input.tool_input.code : "";
  if (!code) {
    return hookOutput(
      "PostToolUse",
      "[validate_workflow returned. Validation is necessary, not sufficient.] If n8n-workflow-lifecycle-official is not already in your context, load it via the Skill tool and walk references/VALIDATION_CHECKLIST.md section 2 before publish.",
    );
  }

  const has = (signature) => code.includes(signature);
  const detectedFlags = {
    Set: has("n8n-nodes-base.set"),
    Code: has("n8n-nodes-base.code"),
    Merge: has("n8n-nodes-base.merge"),
    Loop: has("n8n-nodes-base.splitInBatches"),
    DateTime: has("n8n-nodes-base.dateTime"),
    SubWorkflowTrigger: has("n8n-nodes-base.executeWorkflowTrigger"),
    DataTable: has("n8n-nodes-base.dataTable"),
    Agent: has("n8n-nodes-langchain.agent"),
    Webhook: has("n8n-nodes-base.webhook"),
    HttpRequest: has("n8n-nodes-base.httpRequest"),
    RespondToWebhook: has("n8n-nodes-base.respondToWebhook"),
    Schedule: has("n8n-nodes-base.scheduleTrigger"),
  };
  const hasChatTrigger = has("langchain.chatTrigger");
  const hasNewCredential = has("newCredential(");
  const hasDollarJson = /\$json\./.test(code);
  const nodeCount = (code.match(/type:\s*['"]n8n-/g) || []).length;

  const suggestions = [];
  if (detectedFlags.Merge) {
    suggestions.push(
      "n8n-node-configuration-official references/MERGE_NODE.md (Merge: numberOfInputs vs wire count, useDataOfInput off-by-one)",
    );
  }

  const expressionReasons = [];
  if (detectedFlags.Set) expressionReasons.push("Set antipattern");
  if (detectedFlags.DateTime) expressionReasons.push("DateTime → Luxon");
  if (hasDollarJson) expressionReasons.push("$json refs");
  if (expressionReasons.length) {
    suggestions.push(
      `n8n-expressions-official (${expressionReasons.join(", ")})`,
    );
  }
  if (detectedFlags.Code) {
    suggestions.push(
      "n8n-code-nodes-official (Code detected: alternatives review)",
    );
  }
  if (detectedFlags.Loop || detectedFlags.HttpRequest) {
    suggestions.push("n8n-loops-official (Loop Over Items / pagination)");
  }
  if (detectedFlags.SubWorkflowTrigger) {
    suggestions.push(
      "n8n-subworkflows-official (sub-workflow trigger: Define Below mode + return-shape rules)",
    );
  }
  if (detectedFlags.DataTable) {
    suggestions.push(
      "n8n-data-tables-official (Data Table: schema, dedup, _object column rules)",
    );
  }
  if (
    hasNewCredential ||
    detectedFlags.HttpRequest ||
    detectedFlags.Webhook ||
    detectedFlags.RespondToWebhook
  ) {
    suggestions.push(
      "n8n-credentials-and-security-official (auth surface present)",
    );
  }
  if (
    detectedFlags.Webhook ||
    detectedFlags.RespondToWebhook ||
    detectedFlags.Schedule ||
    hasChatTrigger ||
    detectedFlags.Agent
  ) {
    suggestions.push(
      "n8n-error-handling-official (unattended / webhook workflow: error branches required)",
    );
  }
  if (nodeCount > 6) {
    suggestions.push(
      "n8n-workflow-lifecycle-official (>6 nodes: sticky notes, descriptions capturing the why)",
    );
  }
  if (detectedFlags.Agent) {
    suggestions.push(
      "n8n-agents-official (LangChain agent detected)",
    );
  }

  const detected =
    Object.entries(detectedFlags)
      .filter(([, present]) => present)
      .map(([name]) => name)
      .join(" ") || "(none of the high-risk node types)";

  let context = `[validate_workflow returned. Validation is necessary, not sufficient.]
Workflow analyzed: ${nodeCount} node(s); detected: ${detected}.
`;
  if (suggestions.length) {
    context += `
If any of these skills are not already in your context, load them via the Skill tool:
- ${suggestions.join("\n- ")}

This is the gate. Walk these BEFORE publish_workflow. Validation passing means the SDK is well-formed; it does NOT mean the workflow is correct.`;
  } else {
    context += `
No high-risk patterns surfaced. If anything in this workflow is non-trivial, load n8n-workflow-lifecycle-official via the Skill tool and walk references/VALIDATION_CHECKLIST.md section 2 before publish.`;
  }
  return hookOutput("PostToolUse", context);
}

function run(input) {
  if (action === "session-start") {
    return sessionStart(input);
  }
  if (action === "pre-get-node-types") {
    return getNodeTypesReminder(input);
  }
  if (action === "post-validate-workflow") {
    return postValidateWorkflow(input);
  }
  if (reminders[action]) {
    return oneShotReminder(input, reminders[action]);
  }
  return null;
}

try {
  emit(run(readInput()));
} catch {
  // Hooks are advisory. Fail open instead of blocking a Codex or Claude session.
}
