#!/usr/bin/env bash
# context7-guard hook'unu sentetik girdiyle dener (claude gerekmez).
set -uo pipefail
H="$(cd "$(dirname "$0")/.." && pwd)/src/hooks/context7-guard.py"
fail=0
run() { python3 -c 'import json,sys; print(json.dumps({"tool_name":"mcp__context7__query-docs","tool_input":{"libraryId":"/tiangolo/fastapi","query":sys.argv[1]}}))' "$1" | python3 "$H" 2>&1; echo "rc=$?"; }
deny()  { out=$(run "$1"); if grep -q 'rc=2' <<<"$out" && grep -q 'context7-guard' <<<"$out"; then echo "ok   durdurur: ${1:0:50}"; else echo "FAIL durdurur: $1 -> [$out]"; fail=1; fi; }
allow() { out=$(run "$1"); if [ "$out" = "rc=0" ]; then echo "ok   gecer   : $1"; else echo "FAIL gecer   : $1 -> [$out]"; fail=1; fi; }
allow 'How to declare a dependency with yield in FastAPI'
allow 'SQLAlchemy 2 async session expire_on_commit'
allow 'pydantic v2 model_config extra forbid'
deny  $'def f():\n    return 1'
deny  'why does ```x = 1``` fail'
deny  'error in /Users/enesa/Projects/app/service.py'
deny  'DATABASE_URL=postgresql://u:p@h/db fails'
deny  'connect postgresql+asyncpg://user:pw@db:5432/app'
deny  'my api_key: abc123 is rejected'
deny  'sk-ant-abcdefghijklmnopqrstuvwx invalid'
deny  "$(printf 'a%.0s' {1..301})"
if printf 'xx' | python3 "$H"; then echo "ok   sessiz  : bozuk girdi"; else echo "FAIL bozuk girdi"; fail=1; fi
if [ $fail = 0 ]; then echo "PASS"; else echo "FAILED"; exit 1; fi
