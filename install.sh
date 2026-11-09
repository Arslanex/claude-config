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
done < <(find "$SRC" -type f ! -name '.DS_Store' ! -path '*/__pycache__/*' ! -path '*/.cache/*' -print0 | sort -z)

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
