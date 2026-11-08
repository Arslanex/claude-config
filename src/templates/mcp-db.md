# Database MCP template (per project, never global)

Rules
- Add to the project's `.mcp.json` only when the project needs it.
- Use a dedicated read-only DB user (ideally on a replica). Server flags are a second layer, DB permissions are the real guard.
- Never put passwords in `.mcp.json`. Reference env vars with `${VAR}`; export them in the shell, not in git.
- Pin versions. Verify the package first (npm view / PyPI), and re-check the pin when updating.
- After adding, run `/context` and confirm tools are loaded on demand.

.mcp.json
{
  "mcpServers": {
    "mongodb": {
      "command": "npx",
      "args": ["-y", "mongodb-mcp-server@3.2.2", "--readOnly"],
      "env": {
        "MDB_MCP_CONNECTION_STRING": "${MONGODB_RO_URI}",
        "MDB_MCP_TELEMETRY": "disabled"
      }
    },
    "postgres": {
      "command": "uvx",
      "args": ["postgres-mcp", "--access-mode=restricted"],
      "env": { "DATABASE_URI": "${POSTGRES_RO_URI}" }
    },
    "redis": {
      "command": "uvx",
      "args": ["--from", "redis-mcp-server@latest", "redis-mcp-server"],
      "env": {
        "REDIS_HOST": "${REDIS_HOST}",
        "REDIS_PORT": "${REDIS_PORT}",
        "REDIS_USERNAME": "${REDIS_RO_USER}",
        "REDIS_PWD": "${REDIS_RO_PWD}"
      }
    }
  }
}

Prerequisites
- postgres, redis: `brew install uv` (not installed yet). Pin their versions at first use.
- redis: no server-side read-only flag found; create a Redis ACL user limited to read commands (+@read -@write -@dangerous).
- postgres: encode special characters in the password (URL encoding); use `?sslmode=require` for remote hosts.
