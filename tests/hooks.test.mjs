import { afterAll, expect, test } from 'vitest';
import { mkdtempSync, rmSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const root = fileURLToPath(new URL('../', import.meta.url));
const scratch = mkdtempSync(join(tmpdir(), 'n8n-hooks-test-'));
const env = { ...process.env, TMPDIR: scratch, CLAUDE_PLUGIN_ROOT: root };
afterAll(() => rmSync(scratch, { recursive: true, force: true }));
const hook = (script, input) => {
  const result = spawnSync('bash', [join(root, 'hooks', script)], {
    env, encoding: 'utf8', input: JSON.stringify(input), timeout: 10000,
  });
  expect(result.status, result.stderr).toBe(0);
  return result.stdout.trim() ? JSON.parse(result.stdout) : null;
};
const context = (result) => result?.hookSpecificOutput?.additionalContext ?? '';

for (const source of ['startup', 'resume', 'clear', 'compact']) {
  test(`shared session hook restores the router on ${source}`, () => {
    const result = context(hook('session-start.sh', { source, session_id: source }));
    expect(result).toContain('Using n8n Skills');
    expect(result).toContain('| `search_workflow_executions` |');
  });
}

for (const source of ['clear', 'compact']) {
  test(`shared reminders rearm after ${source}`, () => {
    const input = { session_id: `rearm-${source}` };
    expect(context(hook('pre-tool-use/create-workflow.sh', input))).toContain('n8n-workflow-lifecycle-official');
    expect(hook('pre-tool-use/create-workflow.sh', input)).toBeNull();
    hook('session-start.sh', { ...input, source });
    expect(context(hook('pre-tool-use/create-workflow.sh', input))).toContain('n8n-workflow-lifecycle-official');
  });
}

test('all configured shared pre-tool scripts still emit their reminders', () => {
  const config = JSON.parse(readFileSync(join(root, 'hooks/agent-hooks.json'), 'utf8'));
  for (const [index, entry] of config.hooks.PreToolUse.entries()) {
    const script = entry.hooks[0].command.split('/hooks/')[1];
    const result = hook(script, { session_id: `configured-${index}`, tool_input: { ids: [{ name: 'n8n-nodes-base.code' }] } });
    expect(result.hookSpecificOutput.hookEventName).toBe('PreToolUse');
    expect(context(result)).not.toBe('');
  }
});

test('post-validation routing still detects node types in SDK code', () => {
  const result = hook('post-tool-use/validate-workflow.sh', {
    session_id: 'validation', tool_input: { code: 'node({type: "n8n-nodes-base.code"})' },
  });
  expect(context(result)).toContain('n8n-code-nodes-official');
});
