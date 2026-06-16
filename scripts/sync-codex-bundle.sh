#!/usr/bin/env bash
# Regenerate the Codex plugin bundle under plugins/n8n-skills/.
#
# Codex copies a plugin into ~/.codex/plugins/cache/<market>/<plugin>/<version>/
# at install time and the copy does NOT follow symlinks, nor will Codex accept
# the repo root itself as a plugin. So the Codex plugin must be a self-contained
# directory of real files. We keep the canonical hooks/ and skills/ at the repo
# root (Claude Code installs the root directly; humans browse there) and mirror
# them into the bundle with this script.
#
# The bundle's .codex-plugin/plugin.json is hand-maintained and left untouched;
# only hooks/ and skills/ are mirrored. CI runs this then `git diff --exit-code`,
# so a stale bundle fails the build. Run it after any change to hooks/ or skills/.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUNDLE="${REPO_ROOT}/plugins/n8n-skills"

mkdir -p "${BUNDLE}/hooks" "${BUNDLE}/skills"

# -a preserves the executable bit on hook scripts; --delete prunes files that
# were removed at the source so the mirror can never go stale-by-addition.
rsync -a --delete "${REPO_ROOT}/hooks/"  "${BUNDLE}/hooks/"
rsync -a --delete "${REPO_ROOT}/skills/" "${BUNDLE}/skills/"

echo "synced hooks/ + skills/ -> ${BUNDLE}"
