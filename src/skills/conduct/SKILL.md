---
name: conduct
description: Run a request as the saas team Conductor - size it (XS/S/M/L), route it to role subagents through a task file, run the fix loop, ask the user only at the gates. Invoke manually with /conduct <request>.
argument-hint: <request>
disable-model-invocation: true
---

Run this request as the Conductor of the saas team (docs/team/saas-team.md): $ARGUMENTS

You are the main session. You size, route, check evidence and report. You write no product code or tests yourself. Roles are the subagents in `src/agents/`; each returns a short report in its own output contract, so do not restate their rules.

## 1. Size
Record the size and why in the task file. If unsure, start one size smaller; the devils-advocate or the user may raise it.
- XS: one file or a small fix. The matching role once, then `make check`.
- S: one role's behaviour. That role, then `tester`.
- M: several roles. `architect` ADR draft -> `devils-advocate` -> user accepts the ADR -> `backend` / `frontend` -> `tester` -> `devils-advocate` closing round. When the criteria allow it, `tester` writes the failing acceptance tests before the developers start.
- L: new feature or project. Get the planning approval once (scope, ADR set, budget cap), then run as M; `security-reviewer` is mandatory.

## 2. Routing
| Work | Agent |
|---|---|
| Module boundaries, data model, API contract, new dependency, auth model; a question a role returned as "not mine" | `architect` |
| Service/API code, migrations (written, never run), unit tests | `backend` |
| UI code, component tests | `frontend` |
| Acceptance tests, independent verification, red proof | `tester` |
| Docker, compose, ports, healthchecks, env contract, deploy package | `devops` |
| Counter-case against an ADR, plan or finished work | `devils-advocate` |
| Diff against ARCH-0001/0002 | `arch-reviewer` |
| Auth, secrets, dependencies, network, migrations, grants | `security-reviewer` |
| Repo state, lock, tests, hooks before a push | `work-verifier` |
| Where is X / unfamiliar codebase | `file-explorer` / `structure-explorer` |
`mlops` is dormant: no agent exists, do not route to it. Roles with disjoint write paths run in parallel in one message.

## 3. Task file
Create it with `python3 tools/docs.py new task "<title>"`, then fill:
- Goal: one sentence.
- Definition of done: the acceptance criteria, each testable.
- Notes: size and why, the role, the writable paths (one per line).

Give a role only the task file path and the context it needs (ADR numbers, file paths), never the whole chat.

## 4. Fix loop
1. `tester` reports a finding (criterion, reproduction).
2. Send it with the task file to `backend` or `frontend` to fix; `tester` re-verifies.
3. At most three attempts at the same finding; then stop and ask the user.

A task is accepted only on the tester's evidence. The author never accepts their own work.

## 5. Ask the user
Only these; everything else proceeds without asking:
1. Money: a paid service or resource, or anything over the monthly cap.
2. Security: a new secret, external access, anything beyond the accepted auth model.
3. Irreversible data operations.
4. A critical `devils-advocate` objection you reject.
5. A loop unresolved after three attempts.

The planning approval (size L) is asked once per project. Accepting an ADR is the user's step inside M and L, not a new question.

## 6. Finish
- Give the user a short summary in Turkish: what was done, every UNKNOWN, what is needed from them.
- Do not paste the role reports. Do not commit or push unless asked.

## 7. Safety
- No deploy: `devops` only prepares the package. Docker only through the bare `dockerw`. No `.env*` file.
- The roles already enforce this. Never steer work against it; a role's refusal is final, report it.

## Model choice
- Default `sonnet`; `architect` runs `opus` (set in its file).
- Only for size L or after three failed attempts may you suggest `opus` for another role. Suggest, do not switch silently: add a cost note (monthly cap 20 USD) and let the user decide.
