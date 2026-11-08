#!/usr/bin/env bash
# Initialize Claude Code project config from the template. Never overwrites existing files.
# --upgrade: only update tools/docs.py, and only if the template engine version is newer.
set -euo pipefail

usage() { echo "Usage: $0 [--upgrade]"; }

UPGRADE=0
case "${1:-}" in
  "") ;;
  --upgrade) UPGRADE=1 ;;
  -h|--help) usage; exit 0 ;;
  *) usage >&2; exit 1 ;;
esac

T="$HOME/.claude/templates/project"

engine_version() {
  sed -n 's/^DOCS_ENGINE_VERSION *= *\([0-9][0-9]*\).*/\1/p' "$1" 2>/dev/null | head -n 1
}

if [ "$UPGRADE" -eq 1 ]; then
  [ -f tools/docs.py ] || { echo "tools/docs.py not found; run $0 without --upgrade first" >&2; exit 1; }
  new="$(engine_version "$T/tools/docs.py")"
  old="$(engine_version tools/docs.py)"
  new="${new:-0}"
  old="${old:-0}"
  if [ "$new" -le "$old" ]; then
    echo "docs engine is up to date (project v$old, template v$new); nothing changed"
    exit 0
  fi
  cp -p tools/docs.py tools/docs.py.bak
  cp "$T/tools/docs.py" tools/docs.py
  echo "docs engine upgraded: v$old -> v$new (previous copy saved as tools/docs.py.bak)"
  diff -u tools/docs.py.bak tools/docs.py | sed -n '1,80p' || true
  exit 0
fi

mkdir -p .claude
[ -e .claude/settings.json ] || cp "$T/settings.json" .claude/settings.json
[ -e CLAUDE.md ] || cp "$T/CLAUDE.md" CLAUDE.md
[ -e Makefile ] || cp "$T/Makefile" Makefile
mkdir -p .claude/rules
touch .claude/rules/.gitkeep
mkdir -p tools
[ -e tools/docs.py ] || cp "$T/tools/docs.py" tools/docs.py

# Docs skeleton: copy only files that do not exist yet.
if [ -d "$T/docs" ]; then
  while IFS= read -r -d '' f; do
    rel="${f#"$T"/}"
    if [ ! -e "$rel" ]; then
      mkdir -p "$(dirname "$rel")"
      cp "$f" "$rel"
    fi
  done < <(find "$T/docs" -type f ! -name '.DS_Store' -print0 | sort -z)
fi

touch .gitignore
# Make sure the last line is terminated so appended entries do not get glued to it.
if [ -s .gitignore ] && [ -n "$(tail -c 1 .gitignore)" ]; then
  echo >> .gitignore
fi
for l in ".claude/settings.local.json" ".claude/session-state.md" "CLAUDE.local.md" ".obsidian/"; do
  grep -qxF "$l" .gitignore || echo "$l" >> .gitignore
done
echo "Claude project config ready in $(pwd):"
ls -A .claude CLAUDE.md Makefile .gitignore tools docs
