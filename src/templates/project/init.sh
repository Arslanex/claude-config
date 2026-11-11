#!/usr/bin/env bash
# Initialize Claude Code project config from the template. Never overwrites existing files.
# --upgrade: only update tools/docs.py, and only if the template engine version is newer.
# --team-only (with --kind): install only the profile's team files (role agents, skills, team spec)
# into .claude/; for an existing repo that keeps its own layout.
# --apply (with --kind): replace team files that differ from the template (previous copy kept as
# <file>.bak) instead of writing <file>.proposed, and remove team files an earlier install of the
# profile wrote that the profile no longer ships (also kept as <file>.bak). Without --apply such
# files are only listed. Scaffold files are never replaced.
# .claude/profile holds the profile name, team=<hash> and one file=<path> line per installed team file.
# RETIRED_TEAM lists team files that left every profile; --apply backs them up and removes them even
# when the stamp has no file list (an install made by an older cinit). Without --apply they are listed.
set -euo pipefail

RETIRED_TEAM=(
  .claude/skills/conduct/SKILL.md
)

usage() { echo "Usage: $0 [--upgrade] [--kind <profile> [--pkg <python_package>] [--team-only] [--apply]]"; }

UPGRADE=0
KIND=""
PKG=""
TEAM_ONLY=0
APPLY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --upgrade) UPGRADE=1; shift ;;
    --team-only) TEAM_ONLY=1; shift ;;
    --apply) APPLY=1; shift ;;
    --kind) KIND="${2:-}"; [ -n "$KIND" ] || { usage >&2; exit 1; }; shift 2 ;;
    --pkg) PKG="${2:-}"; case "$PKG" in ""|[0-9]*|*[!a-z0-9_]*) usage >&2; exit 1 ;; esac; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; exit 1 ;;
  esac
done

if [ -z "$KIND" ] && [ $((TEAM_ONLY + APPLY)) -gt 0 ]; then usage >&2; exit 1; fi

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

# Hash of the profile's team files; stamped into .claude/profile so the detect-profile hook can
# tell when the template moved on. Keep the algorithm identical to hooks/detect-profile.py.
team_hash() {
  [ -d "$1" ] || return 0
  python3 - "$1" <<'PY'
import hashlib
import sys
from pathlib import Path

root = Path(sys.argv[1])
h = hashlib.sha256()
for rel in sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file() and p.name != ".DS_Store"):
    h.update(rel.encode() + b"\0" + (root / rel).read_bytes() + b"\0")
print(h.hexdigest())
PY
}

subst() { [ -n "$PKG" ] && { sed -i.bak "s/PKG_NAME/$PKG/g" "$1" && rm -f "$1.bak"; } || true; }
# Profile (--kind): copy missing files, never overwrite; differing files get a .proposed copy.
if [ -n "$KIND" ]; then
  P="$T/../profiles/$KIND"
  [ -d "$P" ] || { echo "unknown profile: $KIND" >&2; exit 1; }
  team_list="$(mktemp "${TMPDIR:-/tmp}/init-team.XXXXXX")"
  while IFS= read -r -d '' f; do
    rel="${f#"$P"/}"
    # team/ holds the profile's role agents, skills and team spec; it installs into .claude/.
    case "$rel" in
      team/*) is_team=1; dst=".claude/${rel#team/}" ;;
      *) if [ "$TEAM_ONLY" -eq 1 ]; then continue; fi; is_team=0; dst="$rel" ;;
    esac
    [ -n "$PKG" ] && dst="${dst//PKG_NAME/$PKG}"
    if [ "$is_team" -eq 1 ]; then printf '%s\n' "$dst" >> "$team_list"; fi
    tmp="$(mktemp "${TMPDIR:-/tmp}/init.XXXXXX")"
    cp "$f" "$tmp"
    subst "$tmp"
    if [ ! -e "$dst" ]; then
      mkdir -p "$(dirname "$dst")"
      cp -p "$f" "$dst"
      subst "$dst"
    elif cmp -s "$tmp" "$dst"; then
      :
    elif [ "$APPLY" -eq 1 ] && [ "$is_team" -eq 1 ]; then
      cp -p "$dst" "$dst.bak"
      cp "$tmp" "$dst"
      rm -f "$dst.proposed"
      echo "updated: $dst (previous copy saved as $dst.bak)"
    else
      cp "$f" "$dst.proposed"
      subst "$dst.proposed"
      echo "conflict: $dst exists; wrote $dst.proposed"
    fi
    rm -f "$tmp"
  done < <(find "$P" -type f ! -name '.DS_Store' ! -name 'gitignore.lines' ! -path '*/.cache/*' ! -path '*/.venv/*' ! -path '*/__pycache__/*' ! -path '*/.pytest_cache/*' ! -path '*/.mypy_cache/*' ! -path '*/.ruff_cache/*' -print0 | sort -z)
  # Team files of the previous install (file= lines of the old stamp) that left the profile.
  keep="$(mktemp "${TMPDIR:-/tmp}/init-keep.XXXXXX")"
  if [ -f .claude/profile ]; then
    if ! grep -q '^file=' .claude/profile && [ -e .claude/team.md ]; then
      echo "note: .claude/profile has no file list (an older cinit wrote it); team files that left the profile cannot be found this time"
    fi
    while IFS= read -r old; do
      # The stamp is project content: accept only plain paths inside .claude/.
      case "$old" in
        .claude/*) ;;
        *) continue ;;
      esac
      case "$old" in *..*|*[!A-Za-z0-9._/-]*) continue ;; esac
      grep -qxF "$old" "$team_list" && continue
      [ -f "$old" ] || continue
      if [ "$APPLY" -eq 1 ]; then
        cp -p "$old" "$old.bak"
        rm -f "$old"
        echo "removed: $old (no longer in profile $KIND; previous copy saved as $old.bak)"
      else
        printf '%s\n' "$old" >> "$keep"
        echo "stale: $old is no longer in profile $KIND; run again with --apply to remove it (a .bak copy is kept)"
      fi
    done < <(sed -n 's/^file=//p' .claude/profile)
  fi
  for old in "${RETIRED_TEAM[@]}"; do
    [ -f "$old" ] || continue
    grep -qxF "$old" "$team_list" && continue
    grep -qxF "$old" "$keep" && continue
    if [ "$APPLY" -eq 1 ]; then
      cp -p "$old" "$old.bak"
      rm -f "$old"
      echo "removed: $old (retired team file; previous copy saved as $old.bak)"
    else
      echo "stale: $old is a retired team file; run again with --apply to remove it (a .bak copy is kept)"
    fi
  done
  stamp="$(team_hash "$P/team")"
  echo "$KIND" > .claude/profile
  if [ -n "$stamp" ]; then echo "team=$stamp" >> .claude/profile; fi
  sort -u "$team_list" "$keep" | sed 's/^/file=/' >> .claude/profile
  rm -f "$team_list" "$keep"
fi
if [ "$TEAM_ONLY" -eq 1 ]; then
  echo "Team files of profile $KIND ready in $(pwd)/.claude:"
  ls -A .claude
  exit 0
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
for l in ".claude/settings.local.json" ".claude/session-state.md" "CLAUDE.local.md" ".obsidian/" ".env" ".env.*" ".DS_Store" "*.proposed"; do
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
