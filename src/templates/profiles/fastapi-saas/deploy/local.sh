#!/usr/bin/env bash
# Local run without app images: postgres and redis in Docker, api, worker and web on the host.
# The User runs these scripts (start.sh, stop.sh, restart.sh); agents never start host processes.
# Used until the User switches local run to Docker (compose.development.yaml).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN="$ROOT/.cache/local"
COMPOSE=(docker compose -f "$ROOT/deploy/compose.yaml" -f "$ROOT/deploy/compose.development.yaml")

alive() {
  local pid
  pid="$(cat "$RUN/$1.pid" 2>/dev/null)" || return 1
  kill -0 "$pid" 2>/dev/null
}

launch() {
  # set -m gives each job its own process group, so stop also ends reloader children.
  local name="$1" dir="$2"
  shift 2
  if alive "$name"; then
    echo "$name: already running"
    return
  fi
  set -m
  (cd "$dir" && exec "$@") >"$RUN/$name.log" 2>&1 &
  echo $! >"$RUN/$name.pid"
  set +m
  echo "$name: started, log $RUN/$name.log"
}

start() {
  mkdir -p "$RUN"
  if [ -f "$ROOT/.env" ]; then
    set -a
    . "$ROOT/.env"
    set +a
  fi
  export DATABASE_URL="${DATABASE_URL:-postgresql+asyncpg://dev:dev@localhost:5432/dev}"
  export WORKER_MODE="${WORKER_MODE:-fake}"
  "${COMPOSE[@]}" up -d --wait postgres redis
  (cd "$ROOT/backend" && uv run alembic upgrade head)
  launch api "$ROOT/backend" uv run uvicorn PKG_NAME.interface.http.app:app --reload --host 127.0.0.1 --port 8000
  if [ -e "$ROOT/backend/src/PKG_NAME/worker.py" ] || [ -d "$ROOT/backend/src/PKG_NAME/worker" ]; then
    launch worker "$ROOT/backend" uv run python -m PKG_NAME.worker
  fi
  if [ -f "$ROOT/frontend/package.json" ]; then
    launch web "$ROOT/frontend" npm run dev
  fi
  echo "api: http://127.0.0.1:8000  WORKER_MODE=$WORKER_MODE"
}

stop() {
  local name pid
  for name in web worker api; do
    if alive "$name"; then
      pid="$(cat "$RUN/$name.pid")"
      kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid"
      echo "$name: stopped"
    fi
    rm -f "$RUN/$name.pid"
  done
  # stop keeps the containers; the dev data lives in the named volumes pgdata and redisdata.
  "${COMPOSE[@]}" stop postgres redis
}

case "${1:-}" in
  start) start ;;
  stop) stop ;;
  restart) stop; start ;;
  *) echo "usage: deploy/local.sh start|stop|restart" >&2; exit 2 ;;
esac
