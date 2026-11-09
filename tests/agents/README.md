# Agent regression harness

Runs each case in `cases/` through `claude -p` and checks the reviewer agent's findings.
- Agents are read from `src/agents/` (not the installed copy) and passed via `--agents` JSON, selected with `--agent`.
- Per case: expected IDs present, forbidden IDs absent, clean cases answer `NO FINDINGS`.
- Any tool outside the agent's frontmatter `tools` (seen as `tool_use` in the stream-json) fails the case.

## Adding a case
1. Create `cases/<name>/` with `input.patch` (short, single-topic unified diff).
2. Add `case.json`: `agent`, `expect` (IDs that must appear), `forbid` (IDs that must not), `clean` (true = must say `NO FINDINGS`).
3. Clean cases: `expect` is empty and `forbid` lists every ID in the agent's dictionary.

## Running
- `make agent-eval` calls the model once per case, so it costs tokens and is not part of `make check`.
- `make test` runs `tests/test_agent_harness.py`, which is deterministic and never calls claude.

## ID dictionary
The finding-ID dictionary lives only in the agent body (`src/agents/<agent>.md`); the tests check every case ID against it.
