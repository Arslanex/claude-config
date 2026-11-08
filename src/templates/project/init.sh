#!/usr/bin/env bash
# Initialize Claude Code project config from the template. Never overwrites existing files.
set -euo pipefail
T="$HOME/.claude/templates/project"
mkdir -p .claude
[ -e .claude/settings.json ] || cp "$T/settings.json" .claude/settings.json
[ -e CLAUDE.md ] || cp "$T/CLAUDE.md" CLAUDE.md
touch .gitignore
for l in ".claude/settings.local.json" "CLAUDE.local.md"; do
  grep -qxF "$l" .gitignore || echo "$l" >> .gitignore
done
echo "Claude project config ready in $(pwd):"
ls -A .claude CLAUDE.md .gitignore
