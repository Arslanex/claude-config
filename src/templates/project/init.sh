#!/usr/bin/env bash
# Initialize Claude Code project config from the template. Never overwrites existing files.
# --upgrade: only update tools/docs.py, and only if the template engine version is newer.
set -euo pipefail

usage() { echo "Usage: $0 [--upgrade] [--kind <profile> [--pkg <python_package>]]"; }

UPGRADE=0
KIND=""
PKG=""
while [ $# -gt 0 ]; do
  case "$1" in
    --upgrade) UPGRADE=1; shift ;;
    --kind) KIND="${2:-}"; [ -n "$KIND" ] || { usage >&2; exit 1; }; shift 2 ;;
    --pkg) PKG="${2:-}"; case "$PKG" in ""|[0-9]*|*[!a-z0-9_]*) usage >&2; exit 1 ;; esac; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; exit 1 ;;
  esac
done

T="$HOME/.claude/templates/project"
if [ -n "$KIND" ] && [ ! -d "$T/../profiles/$KIND" ]; then echo "unknown profile: $KIND" >&2; exit 1; fi

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

subst() { [ -n "$PKG" ] && { sed -i.bak "s/__PKG__/$PKG/g" "$1" && rm -f "$1.bak"; } || true; }
# Profile (--kind): copy missing files, never overwrite; differing files get a .proposed copy.
if [ -n "$KIND" ]; then
  P="$T/../profiles/$KIND"
  [ -d "$P" ] || { echo "unknown profile: $KIND" >&2; exit 1; }
  while IFS= read -r -d '' f; do
    rel="${f#"$P"/}"
    dst="$rel"
    [ -n "$PKG" ] && dst="${rel//__PKG__/$PKG}"
    tmp="$(mktemp "${TMPDIR:-/tmp}/init.XXXXXX")"
    cp "$f" "$tmp"
    subst "$tmp"
    if [ ! -e "$dst" ]; then
      mkdir -p "$(dirname "$dst")"
      cp -p "$f" "$dst"
      subst "$dst"
    elif ! cmp -s "$tmp" "$dst"; then
      cp "$f" "$dst.proposed"
      subst "$dst.proposed"
      echo "conflict: $dst exists; wrote $dst.proposed"
    fi
    rm -f "$tmp"
  done < <(find "$P" -type f ! -name '.DS_Store' ! -name 'gitignore.lines' -print0 | sort -z)
  echo "$KIND" > .claude/profile
fi
[ -e .claude/settings.json ] || cp "$T/settings.json" .claude/settings.json
[ -e CLAUDE.md ] || cp "$T/CLAUDE.md" CLAUDE.md
[ -e Makefile ] || cp "$T/Makefile" Makefile
mkdir -p .claude/rules
touch .claude/rules/.gitkeep
mkdir -p tools
[ -e tools/docs.py ] || cp "$T/tools/docs.py" tools/docs.py
mkdir -p tools/git-hooks
[ -e tools/git-hooks/pre-push ] || { cp "$T/tools/git-hooks/pre-push" tools/git-hooks/pre-push; chmod +x tools/git-hooks/pre-push; }

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
for l in ".claude/settings.local.json" ".claude/session-state.md" "CLAUDE.local.md" ".obsidian/" ".env" ".env.*" ".DS_Store"; do
  grep -qxF "$l" .gitignore || echo "$l" >> .gitignore
done
if [ -n "$KIND" ] && [ -f "$T/../profiles/$KIND/gitignore.lines" ]; then
  while IFS= read -r l; do
    if [ -n "$l" ] && ! grep -qxF "$l" .gitignore; then echo "$l" >> .gitignore; fi
  done < "$T/../profiles/$KIND/gitignore.lines"
fi
echo "Claude project config ready in $(pwd):"
ls -A .claude CLAUDE.md Makefile .gitignore tools docs
echo "Enable the pre-push gate (runs make check before every push): make hooks"
