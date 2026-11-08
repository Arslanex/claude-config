# Claude Code shell helpers. Add to ~/.zshrc:  source ~/.claude/shell/claude.zsh

# Run Claude headless and unattended: edits auto-accepted inside the project, bounded loop.
# Usage: cauto "<task>" [max_turns=30] [max_budget_usd=5]
cauto() {
  [ -z "$1" ] && { echo "usage: cauto \"<task>\" [max_turns] [max_budget_usd]"; return 1; }
  claude -p "$1" --permission-mode acceptEdits --max-turns "${2:-30}" --max-budget-usd "${3:-5}"
  local rc=$?
  osascript -e "display notification \"cauto finished (exit $rc)\" with title \"Claude Code\" sound name \"Glass\""
  return $rc
}

# Initialize Claude Code config (settings.json, CLAUDE.md, .gitignore) in the current project.
cinit() { bash "$HOME/.claude/templates/project/init.sh" "$@"; }
