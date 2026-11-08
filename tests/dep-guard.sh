#!/usr/bin/env bash
# dep-guard hook'unu sentetik girdiyle dener (claude gerekmez).
set -uo pipefail
H="$(cd "$(dirname "$0")/.." && pwd)/src/hooks/dep-guard.py"
fail=0
run() { python3 -c 'import json,sys; print(json.dumps({"tool_name":"Bash","tool_input":{"command":sys.argv[1]}}))' "$1" | python3 "$H"; }
ask()    { out=$(run "$1"); if grep -q '"permissionDecision": "ask"' <<<"$out"; then echo "ok   sorar   : $1"; else echo "FAIL sorar   : $1 -> [$out]"; fail=1; fi; }
silent() { out=$(run "$1"); if [ -z "$out" ]; then echo "ok   sessiz  : $1"; else echo "FAIL sessiz  : $1 -> [$out]"; fail=1; fi; }
ask    'uv add httpx'
ask    'uv pip install requests'
ask    'pip install requests'
ask    'python3 -m pip install -U rich'
ask    'npm install -D vitest'
ask    'cd backend && uv add fastapi'
ask    'FOO=1 pnpm add zod'
ask    'cargo add serde'
ask    'brew install jq'
silent 'uv sync'
silent 'npm install'
silent 'npm ci'
silent 'uv run pytest'
silent 'echo "uv add x"'
silent 'git commit -m "uv add y"'
silent 'make check'
silent 'pip list'
if printf 'xx' | python3 "$H" | grep -q .; then echo "FAIL bozuk girdi"; fail=1; else echo "ok   sessiz  : bozuk girdi"; fi
if [ $fail = 0 ]; then echo "PASS"; else echo "FAILED"; exit 1; fi
