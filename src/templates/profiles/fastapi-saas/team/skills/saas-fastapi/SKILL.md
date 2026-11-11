---
name: saas-fastapi
description: Run a task or request as the fastapi-saas team Conductor - size it (XS/S/M/L), route it to role subagents through a task file, run the fix loop, ask the user only at the gates. Invoke manually with /saas-fastapi <task or request>
argument-hint: <task path or request>
disable-model-invocation: true
---

Run this request as the Conductor of the saas team (`.claude/team.md`): $ARGUMENTS

Print two lines first: what you will do, and when the user is needed (only the gates in section 5). With no argument, list the open tasks under `docs/05-work/tasks/` (status not `done`) and name the next one, the lowest slice whose `depends_on` are done, as the exact `/saas-fastapi <task path>` command, then stop.
You are the main session. You size, route, check evidence and report. You write no product code or tests yourself. Roles are the installed subagents (names in the routing table); each returns a short report in its own output contract, so do not restate their rules.

Pre-flight: before the first role runs, check what the roles will need to run tests (installed dependencies, a test command in the repo's rules). If something is missing, ask the user once for all of it in a single message. If the project's `.claude/settings.local.json` lacks `sandbox.network.allowLocalBinding`, the same message offers `/grant local-binding` so `tester` runs the integration tests itself.

## 1. Size
Record the size and why in the task file. If unsure, start one size smaller; the devils-advocate or the user may raise it.
- XS: one file or a small fix. The matching role once, then `make check`.
- S: one role's behaviour. That role, then `tester`.
- M: several roles. `architect` ADR draft and module plan -> `devils-advocate` -> user accepts the ADR -> `backend` contract step (schemas, route signatures, `make openapi`) -> `backend` / `frontend` / `tester` in parallel on that contract -> `arch-reviewer` -> `devils-advocate` closing round. `tester` writes the failing acceptance tests from the criteria and the contract while the developers implement. Frontend work of size M or L runs the UI design flow (`.claude/team.md`), one task per step; a page is built only after the design system approval and when every page has a mockup.
- L: new feature or project. Get the planning approval once (scope, ADR set, budget cap), then run as M; a task made by `/design-project` already has it (gate G3), so its slice runs as M with its inputs: the strategy ADR, the INV doc, the threat model, the performance doc, the system ADR, DOM, UX and the slice's planned verifications; run `make sast` and give its output to `security-reviewer`, which is mandatory.

## 2. Routing
| Work | Agent |
|---|---|
| Module boundaries, data model, API contract, new dependency, auth model; a question a role returned as "not mine" | `architect` |
| Service/API code, migrations (written, never run), unit tests | `backend` |
| UI design flow steps (`ui-design`), UI code, component tests | `frontend` |
| Acceptance tests, Playwright UI e2e (in the e2e container), independent verification, red proof | `tester` |
| Docker, compose, ports, healthchecks, env contract, deploy package | `devops` |
| Counter-case against an ADR, plan or finished work | `devils-advocate` |
| Diff against ARCH-0005/0006 | `arch-reviewer` |
| Auth, secrets, dependencies, network, migrations, grants | `security-reviewer` |
| Where is X / unfamiliar codebase | `file-explorer` / `structure-explorer` |
`mlops` is dormant: no agent exists, do not route to it. Roles with disjoint write paths run in parallel in one message.

## 3. Task file
Create it with `python3 tools/docs.py new task "<title>"`, then fill:
- Goal: one sentence.
- Definition of done: the acceptance criteria, each testable.
- Notes: size and why, the role, the writable paths (one per line).
- Module plan: written by the `architect` (file, layer, reason; ARCH-0006). Developers create no file outside it.

For `architect`, also create the ADR draft with `python3 tools/docs.py new adr "<title>"` and name its path in the task file; the architect has no shell.

If tools/docs.py is missing in the target repo, create the task file by hand under docs/tasks/ and leave it untracked; do not commit it.

Give a role only the task file path and the context it needs (ADR numbers, file paths), never the whole chat.

A task with `handoff` in its front matter comes from `/design-project`. Start it only when its handoff manifest `.cache/plan/handoff/<handoff>/manifest.json` has `"state": "committed"`; otherwise say the planning handoff is not finished and stop. Its Notes name the plan and the IDs (F, US, INV, D, SEC, PERF): look each up in `docs/05-work/plans/<PLAN-id>.index.md` and read only those line ranges, never whole plan docs; give roles the same ID list and the index path. Write the verification evidence (test names, commands, results) into its `Evidence:` line in Notes, which planning left as `pending`. Pass its `Doğrulanacak riskler` section to every role: `backend` and `frontend` build each proposed solution (or a better one, noted); `tester` verifies each item and writes its result next to it (`doğrulandı` with the test id, `başarısız, denenen: <alternative>`, or `risk kabul` only with the user's approval and never for `must-verify`).

## 4. Fix loop
1. `tester` reports a finding (criterion, reproduction).
2. Send it with the task file to `backend` or `frontend` to fix; `tester` re-verifies with only the failing tests plus `make check`. A re-review or re-verification gets the earlier findings and checks only those. A new finding blocks only when it is CRITICAL (`.claude/team.md` principle 11); anything else goes to the follow-ups list in the handoff and opens no new round.
3. At most three attempts at the same finding; then stop and ask the user.

A task is accepted only on the tester's evidence, and never while a `must-verify` risk is not `doğrulandı`; other open risks go to the follow-ups. The author never accepts their own work.

## 5. Ask the user
Only these; everything else proceeds without asking. The one-time pre-flight message about missing dependencies is the only other exception.
1. Money: a paid service or resource, or anything over the monthly cap.
2. Security: a new secret, external access, anything beyond the accepted auth model.
3. Irreversible data operations.
4. A critical `devils-advocate` objection you reject (CRITICAL as in `.claude/team.md` principle 11).
5. A loop unresolved after three attempts.
6. Design system approval, once per project: show the design system doc and the top 3 page mockups (paths from `frontend`); the user approves or asks for changes, which go back to `frontend`.

Word every question and report plainly, so it answers four things: the result so far, what changes and where, what you expect, and why it is needed.

The planning approval (size L) is asked once per project. Accepting an ADR is the user's step inside M and L, not a new question.

## 6. Finish
- Give the user a short summary in Turkish: what was done, every UNKNOWN, the follow-ups, the risk results as one short table (ID, result, evidence), what is needed from them. A `risk kabul` for an open risk that is not `must-verify` is asked here.
- Do not paste the role reports. Do not commit or push unless asked.

## 7. Safety
- No deploy: `devops` only prepares the package. Docker only through the bare `dockerw`. No `.env*` file. Roles always run with fake workers; live tests are the user's. The roles already enforce this: never steer work against it; a role's refusal is final, report it.

## Model choice
- Default `sonnet`; `architect` runs `opus` (set in its file).
- Only for size L or after three failed attempts may you suggest `opus` for another role. Suggest, do not switch silently: add a cost note (monthly cap 20 USD) and let the user decide.
