import { afterAll, expect, test } from 'vitest';
import { readFileSync, readdirSync, existsSync, mkdtempSync, rmSync } from 'node:fs';
import { join, dirname, resolve, basename, relative } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';
import { parse } from 'yaml';
import { buildAntigravityPlugin } from '../.antigravity-plugin/build.mjs';

const root = fileURLToPath(new URL('../', import.meta.url));
const scratch = mkdtempSync(join(tmpdir(), 'n8n plugin test '));
const bundle = join(scratch, 'plugin with spaces');
const read = (file) => readFileSync(join(bundle, file), 'utf8');
const json = (file) => JSON.parse(read(file));
afterAll(() => rmSync(scratch, { recursive: true, force: true }));

const walk = (dir) => readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
  const file = join(dir, entry.name);
  return entry.isDirectory() ? walk(file) : [file];
});
const sourceSkills = walk(join(root, 'skills')).map((file) => ({
  file: relative(root, file),
  content: readFileSync(file),
}));
buildAntigravityPlugin(bundle);

test('the bundle uses the repository version and current logo', () => {
  const version = JSON.parse(readFileSync(join(root, 'package.json'), 'utf8')).version;
  expect(json('plugin.json').version).toBe(version);
  expect(read(json('plugin.json').logo)).toBe(
    readFileSync(join(root, '.antigravity-plugin/assets/n8n-logo.svg'), 'utf8'),
  );
});

test('the bundle excludes other client manifests and hooks', () => {
  for (const path of ['.claude-plugin', '.codex-plugin', 'opencode', 'hooks', 'hooks.json']) {
    expect(existsSync(join(bundle, path))).toBe(false);
  }
  expect(existsSync(join(bundle, 'LICENSE'))).toBe(true);
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

for (const file of walk(join(bundle, 'skills')).filter((file) => basename(file) === 'SKILL.md')) {
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

test('the bundle preserves every shared skill file byte for byte', () => {
  const router = join('skills', 'using-n8n-skills-official', 'SKILL.md');
  for (const { file, content } of sourceSkills) {
    const target = file === router ? join(dirname(file), 'PROTOCOL.md') : file;
    expect(readFileSync(join(bundle, target)), file).toEqual(content);
  }
  expect(read('skills/using-n8n-skills-official/SKILL.md')).toContain('[PROTOCOL.md](PROTOCOL.md)');
  expect(walk(join(bundle, 'skills')).filter((file) => basename(file) === 'SKILL.md')).toHaveLength(15);
});

test('building the bundle does not modify the source skills', () => {
  for (const { file, content } of sourceSkills) {
    expect(readFileSync(join(root, file)), file).toEqual(content);
  }
});

test('relative links in the packaged skills and documentation resolve', () => {
  for (const file of walk(bundle).filter((file) => file.endsWith('.md'))) {
    const content = readFileSync(file, 'utf8').replace(/```[^]*?```/g, '').replace(/`[^`]*`/g, '');
    for (const match of content.matchAll(/\[[^\]]*\]\(([^\s)]+)\)/g)) {
      const target = match[1].split('#')[0];
      if (!target || /^(?:[a-z]+:|\/)/i.test(target)) continue;
      expect(existsSync(resolve(dirname(file), decodeURIComponent(target))), `${file}: ${target}`).toBe(true);
    }
  }
});

test('the native rule resolves the entry skill after a relocated install', () => {
  const reference = /@(\S+)/.exec(read('rules/AGENTS.md'));
  expect(reference).not.toBeNull();
  const router = resolve(bundle, 'rules', reference[1]);
  expect(router).toBe(join(bundle, 'skills/using-n8n-skills-official/SKILL.md'));
  expect(readFileSync(router, 'utf8')).toBe(read('skills/using-n8n-skills-official/SKILL.md'));
});
