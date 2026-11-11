#!/usr/bin/env bash
# Copy src/ into ~/.claude, backing up any file it replaces to
# ~/.claude.bak-<timestamp>/. Use --dry-run to only print the plan.
set -euo pipefail

usage() { echo "Usage: $0 [--dry-run]"; }

DRY_RUN=0
case "${1:-}" in
  "") ;;
  --dry-run) DRY_RUN=1 ;;
  -h|--help) usage; exit 0 ;;
  *) usage >&2; exit 1 ;;
esac

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$ROOT/src"
DEST="$HOME/.claude"
BACKUP="$HOME/.claude.bak-$(date +%Y%m%d-%H%M%S)"

[ -d "$SRC" ] || { echo "missing $SRC" >&2; exit 1; }

# Files that left the global install (a profile ships them into the project now).
# An installed copy is backed up, then removed, so it cannot shadow or outlive the profile's.
# The old planning skill was renamed to design-project (docs/design/planning-process.md 3.1); its templates
# come first, so the last rmdir removes its folder.
RETIRED=(
  agents/architect.md
  agents/backend.md
  agents/frontend.md
  agents/tester.md
  agents/devops.md
  agents/arch-reviewer.md
  skills/conduct/SKILL.md
  skills/plan-product/templates/architecture.md
  skills/plan-product/templates/data-model.md
  skills/plan-product/templates/plan.md
  skills/plan-product/templates/task.md
  skills/plan-product/templates/ux.md
  skills/plan-product/diagrams.md
  skills/plan-product/preview.py
  skills/plan-product/protocol.md
  skills/plan-product/question-bank.md
  skills/plan-product/SKILL.md
)

if [ "$DRY_RUN" -eq 1 ]; then
  echo "[dry-run] source: $SRC"
  echo "[dry-run] target: $DEST"
  echo "[dry-run] backup: $BACKUP (only if existing files are replaced)"
else
  mkdir -p "$DEST"
fi

while IFS= read -r -d '' file; do
  rel="${file#"$SRC"/}"
  if [ -e "$DEST/$rel" ]; then
    if [ "$DRY_RUN" -eq 1 ]; then
      echo "[dry-run] backup  $DEST/$rel -> $BACKUP/$rel"
    else
      mkdir -p "$BACKUP/$(dirname "$rel")"
      cp -p "$DEST/$rel" "$BACKUP/$rel"
    fi
  fi
  if [ "$DRY_RUN" -eq 1 ]; then
    echo "[dry-run] copy    $SRC/$rel -> $DEST/$rel"
  else
    mkdir -p "$DEST/$(dirname "$rel")"
    cp -pf "$file" "$DEST/$rel"
    echo "installed $rel"
  fi
done < <(find "$SRC" -type f ! -name '.DS_Store' ! -path '*/__pycache__/*' ! -path '*/.cache/*' ! -path '*/.venv/*' ! -path '*/.pytest_cache/*' ! -path '*/.mypy_cache/*' ! -path '*/.ruff_cache/*' -print0 | sort -z)

for rel in "${RETIRED[@]}"; do
  [ -e "$DEST/$rel" ] || continue
  if [ "$DRY_RUN" -eq 1 ]; then
    echo "[dry-run] retire  $DEST/$rel -> $BACKUP/$rel"
  else
    mkdir -p "$BACKUP/$(dirname "$rel")"
    cp -p "$DEST/$rel" "$BACKUP/$rel"
    rm -f "$DEST/$rel"
    rmdir "$DEST/$(dirname "$rel")" 2>/dev/null || true
    echo "retired $rel"
  fi
done

# templates/ belongs to this repo alone: a template file that left src/ is backed up and removed,
# so cinit never copies a stale file (for example a renamed architecture doc) into a new project.
if [ -d "$DEST/templates" ]; then
  while IFS= read -r -d '' file; do
    rel="${file#"$DEST"/}"
    [ -e "$SRC/$rel" ] && continue
    if [ "$DRY_RUN" -eq 1 ]; then
      echo "[dry-run] prune   $DEST/$rel -> $BACKUP/$rel"
    else
      mkdir -p "$BACKUP/$(dirname "$rel")"
      cp -p "$file" "$BACKUP/$rel"
      rm -f "$file"
      echo "pruned $rel"
    fi
  done < <(find "$DEST/templates" -type f ! -name '.DS_Store' ! -path '*/__pycache__/*' ! -path '*/.cache/*' ! -path '*/.venv/*' ! -path '*/.pytest_cache/*' ! -path '*/.mypy_cache/*' ! -path '*/.ruff_cache/*' -print0 | sort -z)
  [ "$DRY_RUN" -eq 1 ] || find "$DEST/templates" -mindepth 1 -type d -empty -delete
fi

# Where this repo lives, so the promote skill can carry project changes back to src/.
if [ "$DRY_RUN" -eq 1 ]; then
  echo "[dry-run] write   $DEST/config-source <- $ROOT"
else
  printf '%s\n' "$ROOT" > "$DEST/config-source"
fi

if [ "$DRY_RUN" -eq 1 ]; then
  echo "[dry-run] chmod   555 $DEST/hooks/*"
  echo "[dry-run] nothing was changed"
else
  if [ -d "$DEST/hooks" ]; then
    find "$DEST/hooks" -type f -exec chmod 555 {} +
  fi
  if [ -d "$BACKUP" ]; then
    echo "backup saved to $BACKUP"
  fi
fi
