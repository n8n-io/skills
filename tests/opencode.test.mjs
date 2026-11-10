import { afterAll, beforeAll, expect, test } from 'vitest';
import { mkdtempSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';

const scratch = mkdtempSync(join(tmpdir(), 'n8n-opencode-test-'));
const previousTmp = process.env.TMPDIR;
let plugin;
beforeAll(async () => {
  process.env.TMPDIR = scratch;
  const { default: createPlugin } = await import('../opencode/plugin.ts');
  plugin = await createPlugin({});
});
afterAll(() => {
  if (previousTmp === undefined) delete process.env.TMPDIR;
  else process.env.TMPDIR = previousTmp;
  rmSync(scratch, { recursive: true, force: true });
});

test('OpenCode registers canonical skills once and restores the router after compaction', async () => {
  const config = {};
  await plugin.config(config);
  await plugin.config(config);
  expect(config.skills.paths).toHaveLength(1);
  const output = { system: [] };
  await plugin['experimental.chat.system.transform']({}, output);
  await plugin['experimental.chat.system.transform']({}, output);
  expect(output.system).toHaveLength(1);
  expect(output.system[0]).toContain('| `search_workflow_executions` |');
  const compact = { context: [] };
  await plugin['experimental.session.compacting']({ sessionID: 'oc-compact' }, compact);
  expect(compact.context[0]).toContain('Using n8n Skills');
  expect(compact.context[0]).toContain('| `search_workflow_executions` |');
});

test('OpenCode reads the moved hook table and handles both MCP result formats', async () => {
  for (const [index, output] of [{ output: 'result' }, { content: [{ type: 'text', text: 'result' }] }].entries()) {
    await plugin['tool.execute.after']({ tool: 'n8n_mcp_get_node_types', sessionID: `oc-node-${index}`, args: { ids: [{ name: 'n8n-nodes-base.code' }] } }, output);
    expect(JSON.stringify(output)).toContain('Code node detected');
  }
  const output = { content: [] };
  await plugin['tool.execute.after']({ tool: 'n8n_mcp_validate_workflow', sessionID: 'oc-validate', args: { code: 'node({type: "n8n-nodes-base.code"})' } }, output);
  expect(JSON.stringify(output)).toContain('n8n-code-nodes-official');
});

test('OpenCode excludes unrelated tools and rearms reminders after compaction', async () => {
  const unrelated = { output: 'unchanged' };
  await plugin['tool.execute.after']({ tool: 'github_validate_workflow', sessionID: 'oc-other', args: {} }, unrelated);
  expect(unrelated.output).toBe('unchanged');
  const input = { tool: 'n8n_mcp_create_workflow_from_code', sessionID: 'oc-rearm', args: {} };
  const first = { output: '' };
  await plugin['tool.execute.after'](input, first);
  expect(first.output).toContain('n8n-workflow-lifecycle-official');
  const repeated = { output: '' };
  await plugin['tool.execute.after'](input, repeated);
  expect(repeated.output).toBe('');
  await plugin['experimental.session.compacting']({ sessionID: 'oc-rearm' }, { context: [] });
  await plugin['tool.execute.after'](input, repeated);
  expect(repeated.output).toContain('n8n-workflow-lifecycle-official');
});
