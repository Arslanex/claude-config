#!/usr/bin/env bash
# Runs a check quietly: the full output goes to .cache/logs/<name>.log.
# Success prints "<name>: ok". Failure prints only the lines that matter (at most 60), then the log path.
# Usage: tools/quiet.sh <name> <command> [args...]
set -euo pipefail
[ "$#" -ge 2 ] || { echo "usage: $0 <name> <command> [args...]" >&2; exit 2; }
name="$1"; shift
root="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$root/.cache/logs"
log="$root/.cache/logs/$name.log"
rc=0
"$@" > "$log" 2>&1 || rc=$?
if [ "$rc" -eq 0 ]; then
  echo "$name: ok"
  exit 0
fi
# pytest FAILED/ERROR and short traceback lines, coverage rows and gate, ruff/mypy/lint-imports errors.
pattern='^(FAILED|ERROR)[ :]|^E +|^[^ ]+\.py:[0-9]+|^[^ ]+\.py +[0-9]+ +[0-9]+ |^=+ .*(failed|error).* =+$|[Ee]rror|FAIL|BROKEN|Would reformat|^Found [0-9]+|[0-9]+ failed|[0-9]+ errors? in| -> '
matches="$(grep -E "$pattern" "$log" | grep -v site-packages || true)"
[ -n "$matches" ] || matches="$(tail -n 30 "$log")"
total="$(printf '%s\n' "$matches" | wc -l | tr -d ' ')"
echo "$name: FAILED (exit $rc)"
printf '%s\n' "$matches" | head -n 60
[ "$total" -le 60 ] || echo "... $((total - 60)) more matching lines"
echo "full log: .cache/logs/$name.log"
exit "$rc"
