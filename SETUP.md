# Setup on a new machine

Order matters. Steps marked (you) are run by you, not by an agent.

1. **Claude Code** — install it following the official docs: https://docs.claude.com/en/docs/claude-code/setup
2. **Node.js** — required because the Playwright MCP server runs through `npx`. Any recent LTS works; install it with your own tool (fnm, nvm, brew...).
3. **Docker Desktop and uv** — needed by fastapi-saas projects: Docker Desktop for the test stack (agents reach it only through `dockerw`), `uv` for the Python backend (`brew install uv`). The hooks and the planning scripts run on the macOS system `python3` (3.9 or newer); nothing else is required for them.
4. **GitHub CLI** — install `gh` (for example `brew install gh`), then run `gh auth login`.
5. **Claude config** (you):
   ```bash
   ./install.sh --dry-run   # prints the plan, changes nothing
   ./install.sh             # copies src/ into ~/.claude, backing up what it replaces
   ```
6. **MCP servers** (you):
   ```bash
   ./setup-mcp.sh --dry-run # prints the plan, changes nothing
   ./setup-mcp.sh           # adds the servers from mcp/servers.json, skips existing ones
   ```
7. **dockerw** (you) — the only way agents reach Docker; installed outside the project tree so a sandboxed agent cannot edit it:
   ```bash
   tools/install-dockerw.sh --root ~/Projects   # --root: the directory your projects live under
   ```
8. **Locked skills** (you) — third-party skills pinned in `skills.lock`:
   ```bash
   make skills-install               # dry run
   make skills-install ARGS=--apply  # install the approved ones into ~/.claude/skills
   make skills-verify                # installed copies still match the pinned hashes
   ```
9. **Pre-push gate for this repo** (you): `make hooks` (runs `make check` before every push).
10. **Shell helpers** — add this line to `~/.zshrc` (`cauto`, `cfull`, `cinit`):
   ```bash
   source ~/.claude/shell/claude.zsh
   ```
   Profiles (modes) are per project; nothing role-specific is installed globally:
   ```bash
   cinit                                        # base only: CLAUDE.md, Makefile, docs/, pre-push gate
   cinit --kind fastapi-saas --pkg <package>    # new project: scaffold + saas team in .claude/
   cinit --kind fastapi-saas --team-only        # existing repo: only .claude/agents, skills, team.md
   ```
   After a template update the session-start hint says the team files are stale. Re-run the same command:
   changed files arrive as `<file>.proposed`; add `--apply` to replace the team files directly (previous copy kept as `<file>.bak`).
11. **Ghostty notifications** — allow notifications for Ghostty in macOS System Settings. If your setup needs more (for example a Ghostty config option), add your own notes here.
12. **Cloudflare login** — open Claude Code, run `/mcp` and authenticate `cloudflare-api` with Cloudflare (OAuth).

## Not in this repo

- Account-level and plugin skills (reinstall or sign in again; add your own tools here).
- `~/.claude.json` (it holds state and credentials; never commit it).
- All secrets and logins: tokens, API keys, `gh` auth, Cloudflare OAuth.
