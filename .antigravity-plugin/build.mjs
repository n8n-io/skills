import { cpSync, mkdirSync, renameSync, rmSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const source = dirname(fileURLToPath(import.meta.url));
const root = join(source, '..');

export function buildAntigravityPlugin(output) {
  mkdirSync(output, { recursive: true });
  for (const entry of ['plugin.json', 'README.md', 'mcp_config.json', 'assets', 'rules']) {
    cpSync(join(source, entry), join(output, entry), { recursive: true });
  }
  cpSync(join(root, 'LICENSE'), join(output, 'LICENSE'));
  cpSync(join(root, 'skills'), join(output, 'skills'), { recursive: true });

  // Antigravity limits skill bodies to 24 KB. Reference files keep the full protocol.
  const router = join(output, 'skills', 'using-n8n-skills-official');
  renameSync(join(router, 'SKILL.md'), join(router, 'PROTOCOL.md'));
  cpSync(join(source, 'router.md'), join(router, 'SKILL.md'));
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const output = join(root, 'dist', 'antigravity');
  rmSync(output, { recursive: true, force: true });
  buildAntigravityPlugin(output);
  console.log(`Built Antigravity plugin at ${output}`);
}
