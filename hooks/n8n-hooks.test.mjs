import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test, { after } from "node:test";
import { fileURLToPath } from "node:url";

const testDirectory = path.dirname(fileURLToPath(import.meta.url));
const hookScript = path.join(testDirectory, "n8n-hooks.mjs");
const fixtureRoot = fs.mkdtempSync(
  path.join(os.tmpdir(), "n8n hooks with spaces "),
);
const fixtureSkillDirectory = path.join(
  fixtureRoot,
  "skills",
  "using-n8n-skills-official",
);
const metaSkillBody = "---\nname: using-n8n-skills-official\n---\nTest body.\n";

fs.mkdirSync(fixtureSkillDirectory, { recursive: true });
fs.writeFileSync(
  path.join(fixtureSkillDirectory, "SKILL.md"),
  metaSkillBody,
  "utf8",
);

after(() => {
  fs.rmSync(fixtureRoot, { recursive: true, force: true });
});

function newStateDirectory(label) {
  return fs.mkdtempSync(path.join(os.tmpdir(), `n8n-hooks-${label}-`));
}

function invoke(
  action,
  input,
  {
    pluginRoot = fixtureRoot,
    stateDirectory = newStateDirectory("state"),
    pathValue = process.env.PATH,
  } = {},
) {
  const startedAt = Date.now();
  const result = spawnSync(process.execPath, [hookScript, action], {
    encoding: "utf8",
    env: {
      ...process.env,
      CLAUDE_PLUGIN_ROOT: pluginRoot,
      N8N_SKILLS_STATE_DIR: stateDirectory,
      PATH: pathValue,
    },
    input:
      typeof input === "string" ? input : JSON.stringify(input ?? {}),
    timeout: 10_000,
  });
  const stdout = result.stdout.trim();
  return {
    ...result,
    durationMs: Date.now() - startedAt,
    output: stdout ? JSON.parse(stdout) : null,
    stateDirectory,
  };
}

function assertSuccessful(result) {
  assert.equal(result.status, 0, result.stderr);
  assert.equal(result.signal, null);
  assert.ok(result.durationMs < 10_000);
}

test("SessionStart supports startup, resume, clear, and compact", () => {
  const stateDirectory = newStateDirectory("session-events");
  const sessionId = "session-events";

  for (const source of ["startup", "resume"]) {
    const result = invoke(
      "session-start",
      { session_id: sessionId, source },
      { stateDirectory },
    );
    assertSuccessful(result);
    assert.equal(
      result.output.hookSpecificOutput.hookEventName,
      "SessionStart",
    );
    assert.equal(
      result.output.hookSpecificOutput.additionalContext,
      metaSkillBody,
    );
  }

  const ownMarker = path.join(
    stateDirectory,
    `${sessionId}-node-config.loaded`,
  );
  const otherMarker = path.join(
    stateDirectory,
    "other-session-node-config.loaded",
  );
  fs.writeFileSync(ownMarker, "");
  fs.writeFileSync(otherMarker, "");

  const clearResult = invoke(
    "session-start",
    { session_id: sessionId, source: "clear" },
    { stateDirectory },
  );
  assertSuccessful(clearResult);
  assert.equal(fs.existsSync(ownMarker), false);
  assert.equal(fs.existsSync(otherMarker), true);

  fs.writeFileSync(ownMarker, "");
  const compactResult = invoke(
    "session-start",
    { session_id: sessionId, source: "compact" },
    { stateDirectory },
  );
  assertSuccessful(compactResult);
  assert.equal(fs.existsSync(ownMarker), false);
});

test("SessionStart fails open when the meta-skill is unavailable", () => {
  const missingRoot = fs.mkdtempSync(
    path.join(os.tmpdir(), "n8n-hooks-missing-skill-"),
  );
  const result = invoke(
    "session-start",
    { session_id: "missing", source: "startup" },
    { pluginRoot: missingRoot },
  );
  assertSuccessful(result);
  assert.equal(result.output, null);
  fs.rmSync(missingRoot, { recursive: true, force: true });
});

test("one-shot PreToolUse reminders deduplicate by session", () => {
  const actions = [
    "pre-validate-workflow",
    "pre-create-workflow",
    "pre-update-workflow",
    "pre-execute-workflow",
    "pre-test-workflow",
  ];

  for (const action of actions) {
    const stateDirectory = newStateDirectory(action);
    const input = { session_id: `session-${action}` };
    const first = invoke(action, input, { stateDirectory });
    const second = invoke(action, input, { stateDirectory });
    assertSuccessful(first);
    assertSuccessful(second);
    assert.equal(first.output.hookSpecificOutput.hookEventName, "PreToolUse");
    assert.ok(first.output.hookSpecificOutput.additionalContext.length > 50);
    assert.equal(second.output, null);
  }
});

test("get_node_types accepts object and string IDs and repeats risk warnings", () => {
  const stateDirectory = newStateDirectory("get-node");
  const input = {
    session_id: "node-session",
    tool_input: {
      ids: [
        { name: "n8n-nodes-base.code", operation: "runOnceForAllItems" },
        "n8n-nodes-base.dateTime",
      ],
    },
  };

  const first = invoke("pre-get-node-types", input, { stateDirectory });
  const second = invoke("pre-get-node-types", input, { stateDirectory });
  assertSuccessful(first);
  assertSuccessful(second);

  const firstContext = first.output.hookSpecificOutput.additionalContext;
  const secondContext = second.output.hookSpecificOutput.additionalContext;
  assert.match(firstContext, /Before configuring nodes/);
  assert.match(firstContext, /\[Code node detected/);
  assert.match(firstContext, /\[DateTime node detected/);
  assert.doesNotMatch(secondContext, /Before configuring nodes/);
  assert.match(secondContext, /\[Code node detected/);
  assert.match(secondContext, /\[DateTime node detected/);
});

test("get_node_types covers every high-risk node warning", () => {
  const result = invoke("pre-get-node-types", {
    session_id: "all-risk-nodes",
    tool_input: {
      ids: [
        "n8n-nodes-base.set",
        "n8n-nodes-base.merge",
        "n8n-nodes-base.splitInBatches",
        "n8n-nodes-base.dataTable",
      ],
    },
  });
  assertSuccessful(result);

  const context = result.output.hookSpecificOutput.additionalContext;
  assert.match(context, /\[Set node detected/);
  assert.match(context, /\[Merge node detected/);
  assert.match(context, /\[Loop Over Items/);
  assert.match(context, /\[Data Table node detected/);
});

test("PostToolUse returns the fallback when workflow code is absent", () => {
  const result = invoke("post-validate-workflow", {
    session_id: "post-fallback",
    tool_input: {},
  });
  assertSuccessful(result);
  assert.equal(result.output.hookSpecificOutput.hookEventName, "PostToolUse");
  assert.match(
    result.output.hookSpecificOutput.additionalContext,
    /Validation is necessary, not sufficient/,
  );
});

test("PostToolUse detects relevant workflow risks", () => {
  const code = `
node({ type: "n8n-nodes-base.set" })
node({ type: "n8n-nodes-base.code" })
node({ type: "n8n-nodes-base.merge" })
node({ type: "n8n-nodes-base.httpRequest" })
node({ type: "n8n-nodes-base.webhook" })
node({ type: "n8n-nodes-base.dataTable" })
node({ type: "n8n-nodes-langchain.agent" })
const value = $json.value
newCredential("Label")
`;
  const result = invoke("post-validate-workflow", {
    session_id: "post-analysis",
    tool_input: { code },
  });
  assertSuccessful(result);

  const context = result.output.hookSpecificOutput.additionalContext;
  assert.match(context, /Workflow analyzed: 7 node/);
  assert.match(context, /n8n-node-configuration-official/);
  assert.match(context, /n8n-expressions-official/);
  assert.match(context, /n8n-code-nodes-official/);
  assert.match(context, /n8n-loops-official/);
  assert.match(context, /n8n-data-tables-official/);
  assert.match(context, /n8n-credentials-and-security-official/);
  assert.match(context, /n8n-error-handling-official/);
  assert.match(context, /n8n-workflow-lifecycle-official/);
  assert.match(context, /n8n-agents-official/);
});

test("malformed input and unknown actions fail open", () => {
  const malformed = invoke("session-start", "{not-json");
  const unknown = invoke("unknown-action", { session_id: "unknown" });
  assertSuccessful(malformed);
  assertSuccessful(unknown);
  assert.equal(malformed.output, null);
  assert.equal(unknown.output, null);
});

test("hooks do not require Bash, jq, or Python on PATH", () => {
  const result = invoke(
    "session-start",
    { session_id: "node-only", source: "startup" },
    { pathValue: path.dirname(process.execPath) },
  );
  assertSuccessful(result);
  assert.equal(
    result.output.hookSpecificOutput.additionalContext,
    metaSkillBody,
  );
});

test("hooks.json routes every hook through Node with a timeout", () => {
  const config = JSON.parse(
    fs.readFileSync(path.join(testDirectory, "hooks.json"), "utf8"),
  );
  const commands = Object.values(config.hooks).flatMap((groups) =>
    groups.flatMap((group) => group.hooks),
  );

  assert.equal(commands.length, 8);
  for (const hook of commands) {
    assert.match(
      hook.command,
      /^node "\$\{CLAUDE_PLUGIN_ROOT\}\/hooks\/n8n-hooks\.mjs" [a-z-]+$/,
    );
    assert.equal(hook.timeout, 10);
  }
});
