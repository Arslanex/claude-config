# claude-config
Versioned, portable copy of the user's Claude Code setup (~/.claude).

## Commands
- Test: `python3 -m unittest discover -s tests -v`
- Install (user runs this, not the agent): `./install.sh --dry-run`, then `./install.sh`

## Architecture
- `src/` mirrors the ~/.claude layout: settings.json, CLAUDE.md, hooks/, agents/, skills/, templates/
- Global = profile-independent only (hooks, explorers, `security-reviewer`, `devils-advocate`, design-project/grant/kickoff/maintain/promote/remember, and the planning team `strategy-architect`, `product-manager`, `ux-designer`, `solution-architect`, `security-architect`, `performance-architect`, `quality-engineer`, `plan-critic` that `/design-project` leads)
- `src/templates/profiles/<kind>/` is a mode: scaffold + `team/` (role agents, skills, team spec), which `cinit --kind <kind>` installs into the project's `.claude/`
- `tests/` unittest suite for hooks/guard.py and hooks/notify.py
- `install.sh` copies src/ into ~/.claude, backing up anything it replaces

## Conventions
- Python 3 stdlib only. Shell: bash with `set -euo pipefail`.
- Never commit secrets, tokens, .env files or ~/.claude.json.

## Definition of done
- All unit tests pass. `install.sh --dry-run` only prints a plan and changes nothing.

## Gotchas
- Never write to ~/.claude directly (Edit is denied there). Work only on the copies in src/.
- guard.py blocks a whole compound command if one part is risky; run risky parts separately.
- The sandbox refuses writes to any `.claude/agents` directory, so a profile keeps its agents under `team/agents`; init.sh maps `team/` to `.claude/`.
- notify.py writes OSC 777 to the terminal tty (Ghostty); osascript is only the fallback.
