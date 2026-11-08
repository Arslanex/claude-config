#!/usr/bin/env bash
# Register the MCP servers listed in mcp/servers.json with Claude Code.
# Servers that `claude mcp get` already knows are skipped. Use --dry-run to only print the plan.
set -euo pipefail

usage() { echo "Usage: $0 [--dry-run]"; }

DRY_RUN=0
case "${1:-}" in
  "") ;;
  --dry-run) DRY_RUN=1 ;;
  -h|--help) usage; exit 0 ;;
  *) usage >&2; exit 1 ;;
esac

ROOT="$(cd "${BASH_SOURCE[0]%/*}" && pwd)"
MANIFEST="$ROOT/mcp/servers.json"

command -v claude >/dev/null 2>&1 || { echo "error: 'claude' not found in PATH; install Claude Code first (see SETUP.md)" >&2; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "error: 'python3' not found in PATH" >&2; exit 1; }
[ -f "$MANIFEST" ] || { echo "error: missing $MANIFEST" >&2; exit 1; }

# Flatten the manifest into tab-separated records (no empty fields):
#   S name scope transport arg...   server and its claude-mcp-add arguments
#   E name VAR                      required environment variable name
#   N name text                     post-install note
plan="$(python3 - "$MANIFEST" <<'PY'
import json, sys
for s in json.load(open(sys.argv[1]))["servers"]:
    args = s["command"] if s["transport"] == "stdio" else [s["url"]]
    print("\t".join(["S", s["name"], s["scope"], s["transport"], *args]))
    for var in s.get("env_required", []):
        print("\t".join(["E", s["name"], var]))
    if s.get("post_install"):
        print("\t".join(["N", s["name"], s["post_install"]]))
PY
)"

notes=()
while IFS=$'\t' read -r -a f; do
  case "${f[0]}" in
    S)
      name="${f[1]}"; scope="${f[2]}"; transport="${f[3]}"; args=("${f[@]:4}")
      if claude mcp get "$name" >/dev/null 2>&1; then
        echo "skip   $name (already configured)"
        continue
      fi
      if [ "$transport" = "stdio" ]; then
        cmd=(claude mcp add --scope "$scope" --transport stdio "$name" -- "${args[@]}")
      else
        cmd=(claude mcp add --scope "$scope" --transport "$transport" "$name" "${args[@]}")
      fi
      if [ "$DRY_RUN" -eq 1 ]; then
        echo "[dry-run] add    ${cmd[*]}"
      else
        "${cmd[@]}"
        echo "added  $name"
      fi
      ;;
    E)
      # Only report whether the variable is set; never its value.
      var="${f[2]}"
      [ -n "${!var:-}" ] || echo "warning: ${f[1]} needs environment variable $var, which is not set" >&2
      ;;
    N) notes+=("${f[1]}: ${f[2]}") ;;
  esac
done <<< "$plan"

if [ "${#notes[@]}" -gt 0 ]; then
  echo
  echo "Next steps:"
  for n in "${notes[@]}"; do echo "  - $n"; done
fi
[ "$DRY_RUN" -eq 1 ] && echo "[dry-run] nothing was changed"
exit 0
