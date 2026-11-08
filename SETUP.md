# Setup on a new machine

Order matters. Steps marked (you) are run by you, not by an agent.

1. **Claude Code** — install it following the official docs: https://docs.claude.com/en/docs/claude-code/setup
2. **Node.js** — required because the Playwright MCP server runs through `npx`. Any recent LTS works; install it with your own tool (fnm, nvm, brew...).
3. **GitHub CLI** — install `gh` (for example `brew install gh`), then run `gh auth login`.
4. **Claude config** (you):
   ```bash
   ./install.sh --dry-run   # prints the plan, changes nothing
   ./install.sh             # copies src/ into ~/.claude, backing up what it replaces
   ```
5. **MCP servers** (you):
   ```bash
   ./setup-mcp.sh --dry-run # prints the plan, changes nothing
   ./setup-mcp.sh           # adds the servers from mcp/servers.json, skips existing ones
   ```
6. **Shell helpers** — add this line to `~/.zshrc` (`cauto`, `cinit`):
   ```bash
   source ~/.claude/shell/claude.zsh
   ```
7. **Ghostty notifications** — allow notifications for Ghostty in macOS System Settings. If your setup needs more (for example a Ghostty config option), add your own notes here.
8. **Cloudflare login** — open Claude Code, run `/mcp` and authenticate `cloudflare-api` with Cloudflare (OAuth).

## Not in this repo

- Account-level and plugin skills (reinstall or sign in again; add your own tools here).
- `~/.claude.json` (it holds state and credentials; never commit it).
- All secrets and logins: tokens, API keys, `gh` auth, Cloudflare OAuth.
