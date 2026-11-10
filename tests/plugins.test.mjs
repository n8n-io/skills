import { afterAll, expect, test } from 'vitest';
import { readFileSync, readdirSync, existsSync, mkdtempSync, cpSync, rmSync } from 'node:fs';
import { join, dirname, resolve, basename } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';
import { parse } from 'yaml';

const root = fileURLToPath(new URL('../', import.meta.url));
const read = (file) => readFileSync(join(root, file), 'utf8');
const json = (file) => JSON.parse(read(file));
const scratch = mkdtempSync(join(tmpdir(), 'n8n plugin test '));
afterAll(() => rmSync(scratch, { recursive: true, force: true }));

const walk = (dir) => readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
  const file = join(dir, entry.name);
  return entry.isDirectory() ? walk(file) : [file];
});

test('all clients use one release version and the shared hook file', () => {
  const version = json('package.json').version;
  for (const client of ['claude', 'codex', 'antigravity']) {
    expect(json(`.${client}-plugin/plugin.json`).version).toBe(version);
  }
  expect(json('.claude-plugin/marketplace.json').plugins[0].version).toBe(version);
  const shared = './hooks/agent-hooks.json';
  expect(json('.claude-plugin/plugin.json').hooks).toBe(shared);
  expect(json('.codex-plugin/plugin.json').hooks).toBe(shared);
  expect(existsSync(join(root, shared))).toBe(true);
  expect(existsSync(join(root, 'hooks/hooks.json'))).toBe(false);
});

test('the native connection prompts for a full URL without filtering tools or overriding OAuth', () => {
  const servers = json('mcp_config.json').mcpServers;
  expect(Object.keys(servers)).toEqual(['n8n-mcp']);
  const server = servers['n8n-mcp'];
  expect(server.url).toBe('${N8N_MCP_URL}');
  expect(server.variables.map((variable) => variable.name)).toEqual(['N8N_MCP_URL']);
  for (const field of ['headers', 'oauth', 'authProviderType', 'enabledTools', 'disabledTools', 'command']) {
    expect(server).not.toHaveProperty(field);
  }
});

for (const file of walk(join(root, 'skills')).filter((file) => basename(file) === 'SKILL.md')) {
  test(`skill loads without truncation: ${basename(dirname(file))}`, () => {
    const content = readFileSync(file, 'utf8');
    const match = /^---\r?\n([\s\S]*?)\r?\n---\r?\n([\s\S]*)$/.exec(content);
    expect(match).not.toBeNull();
    const { name, description } = parse(match[1]);
    expect(name).toBe(basename(dirname(file)));
    expect(description).toMatch(/^Use when/);
    expect(description.length).toBeLessThanOrEqual(1024);
    expect(content.split('\n').length).toBeLessThanOrEqual(500);
    expect(Buffer.byteLength(match[2])).toBeLessThanOrEqual(24000);
  });
}

test('relative links in skills and installation docs resolve', () => {
  const files = [...walk(join(root, 'skills')), join(root, 'README.md'), join(root, '.antigravity-plugin/README.md')];
  for (const file of files.filter((file) => file.endsWith('.md'))) {
    const content = readFileSync(file, 'utf8').replace(/```[^]*?```/g, '').replace(/`[^`]*`/g, '');
    for (const match of content.matchAll(/\[[^\]]*\]\(([^\s)]+)\)/g)) {
      const target = match[1].split('#')[0];
      if (!target || /^(?:[a-z]+:|\/)/i.test(target)) continue;
      expect(existsSync(resolve(dirname(file), decodeURIComponent(target))), `${file}: ${target}`).toBe(true);
    }
  }
});

test('the native rule resolves the router after a relocated install', () => {
  cpSync(join(root, 'rules'), join(scratch, 'rules'), { recursive: true });
  cpSync(join(root, 'skills'), join(scratch, 'skills'), { recursive: true });
  const rule = readFileSync(join(scratch, 'rules/AGENTS.md'), 'utf8');
  const reference = /@(\S+)/.exec(rule);
  expect(reference).not.toBeNull();
  const router = resolve(scratch, 'rules', reference[1]);
  expect(router).toBe(join(scratch, 'skills/using-n8n-skills-official/SKILL.md'));
  expect(readFileSync(router, 'utf8')).toBe(read('skills/using-n8n-skills-official/SKILL.md'));
});
