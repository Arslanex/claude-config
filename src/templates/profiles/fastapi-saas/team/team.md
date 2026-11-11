# SaaS team specification (profile: fastapi-saas)

Status: draft. Scope: the `fastapi-saas` profile only. Other modes (library, mvp, video) get their own team file later.

This file, the role agents (`.claude/agents/`) and `/saas-fastapi` (`.claude/skills/`) ship with the profile and live in the project: `cinit --kind fastapi-saas` (new project) or `cinit --kind fastapi-saas --team-only` (existing repo). A project without the profile has none of these roles. Shared by every profile and installed globally: hooks and gates, `security-reviewer`, `devils-advocate`, `file-explorer`, `structure-explorer`, the `kickoff`, `maintain`, `remember` skills, and the planning team: `/design-project` (Lead, main session) with `strategy-architect`, `product-manager`, `solution-architect`, `ux-designer`, `security-architect`, `performance-architect`, `quality-engineer` and `plan-critic`. Planning hands its slices to this team as task files once its handoff manifest is committed; `/saas-fastapi <task>` starts each one.

## Principles

1. The Conductor is the main session itself. Subagents cannot spawn subagents, so the other roles are subagents that return a short report.
2. Roles talk through files, not chat. The contract is the task file in `docs/`: goal, acceptance criteria, paths the role may write. Reports have a fixed shape: changed files, evidence commands, open risks.
3. Write areas are disjoint, so independent work runs in parallel.
4. The author is never the verifier of their own work.
5. Evidence before claims: command output, red proof for new tests, coverage. "Done" alone is not accepted.
6. Job size decides which roles run (below). The Conductor records the size and why in the task file; the Devil's Advocate or the User may raise it.
7. The team prepares deploy packages; it does not deploy.
8. Whatever reaches the User (a report, a question, a request for approval) is written in plain sentences and answers four things: the result, what changes and where, what is expected, and why.
9. No role starts a long-running or background process on the host (a server, a watcher, `&`, `nohup`): the sandbox cannot stop it, so the User would have to. Servers and stacks run in containers through `dockerw compose up -d` and stop with `dockerw compose down`. Commands that exit on their own (tests, lint, builds) run on the host as usual.
10. Roles always run with fake workers. Every external or paid service (LLM, payment, mail and similar) has a fake adapter, selected by `WORKER_MODE` (`fake` by default; ARCH-0007), and every test and test stack uses it. Tests against the real services are marked `live` and only the User runs them (`make test-live`, with `WORKER_MODE=live` in the root `.env`). No role sets `live`, runs a live test or reads `.env`.
11. Review is proportionate. CRITICAL is the only level that blocks a merge or a handoff: data loss, an authorization or tenant-isolation bypass, a secret or personal-data leak, losing or charging money, or code that does not build or fails its acceptance tests. A logic bug at an edge or a limit and a convenience problem are at most MAJOR: fixed in the same task when cheap, otherwise a follow-up. A re-review after a fix only checks that the earlier findings are fixed and raises a new finding only when it is CRITICAL; anything else goes to the follow-ups list in the handoff, never blocks and opens no new round.
12. Roles build only what the task's acceptance criteria need: no extra abstraction, config or feature "for later".
13. Checks stay few and quiet. During work a role runs only the affected tests (`make test-unit T=<test file or test id>`, the same for `test-integration`) and the full `make check` once before handing off. The Tester runs its full verification once; after a fix it reruns only the failing tests plus `make check`. Make targets print `<target>: ok` or only the failing lines (`tools/quiet.sh`; `V=1` gives the full output). On a failure a role reads only the failing part of `.cache/logs/<target>.log` with grep or a line range, never the whole log.
14. Tests cover the acceptance criteria, the real edge cases from the plan and every bug found (red first). No test duplicates what another test already covers, no test checks framework or library behaviour, and one parametrized test replaces copies.

## Job size

| Size | Example | Roles |
|---|---|---|
| XS | one file, ~20 lines | Developer + `make check` |
| S | one module's behaviour | Developer + Tester |
| M | new endpoint, schema change | Architect (short note) + Developers + Tester + Devil's Advocate (one light round) |
| L | new module, auth, external dependency, money or security | full flow, all roles, security-reviewer mandatory |

Token budget rules:
- Ask the Architect for the smallest plan that meets the definition of done from the first draft. Every plan item names the DoD line it serves; anything else goes to a later slice.
- Keep the ADR short: decisions and the user approvals only. Long rationale goes in a separate doc that roles read only when they need it.
- Size a slice that touches one module as S, even when it comes from `/design-project`. S has no Architect round and no Devil's Advocate round.

## Roles

| Role | Does | May write | Never |
|---|---|---|---|
| Conductor (main session) | splits the request, sizes it, routes by table, parallelises, checks evidence, keeps the task list | task files, handoffs, merges | product code, skipping a gate, accepting work without evidence |
| System Architect | structure, module boundaries, data model, API contract, ADR/ARCH | `docs/` (ADR, ARCH, domain, plan) | code; marking an ADR accepted |
| Backend Developer | service code, migrations, unit tests with the code | paths named in the task, under `backend/` | compose/Docker/CI, frontend, architecture decisions, weakening tests |
| Frontend Developer | UI architecture, design system and page mockups (design flow), UI, component tests, types from the API contract | `frontend/` (dormant until it exists); in a design task also its docs and `docs/01-architecture/ui/` | changing the backend contract alone |
| Tester | before: failing acceptance tests from the criteria; after: independent verification, red proof, coverage, flaky tracking | `tests/integration`, `tests/e2e`, `tests/smoke`, `tests/support` (the only groups `test_tests_layout.py` allows besides `unit`); `frontend/e2e/` (Playwright) | product code (returns findings) |
| DevOps | Docker, compose, local CI, ports, image and container hygiene, healthchecks, deploy packages | `deploy/`, `tools/`, CI templates, `.env.example` | deploying, `prune -a`, volumes, other projects' resources |
| MLOps | model and data pipelines, experiment tracking, evaluation | `ml/`, `pipelines/` | paid API or GPU use without the budget gate. Dormant in this profile. |
| Devil's Advocate | evidence-based counter-case before plans/ADRs, after diffs, at closing ("what did we not verify") | one review file | code. Every objection needs a concrete scenario or command; at most 2 rounds. |
| User | decision owner, the gates below | everything | – |

Existing reviewers stay: `arch-reviewer` checks diffs against ADR/ARCH; `security-reviewer` is mandatory for auth, secrets, dependencies and network changes and for size L. `file-explorer` and `structure-explorer` are cheap discovery helpers for the Conductor and Architect.

## Flow (M and L)

1. User gives a task (draft) and the Conductor sizes it.
2. Architect drafts the ADR and writes the module plan and the endpoint list into the task file; Devil's Advocate argues against it; the User approves the ADR (one gate).
3. Contract step: Backend writes only the schemas and route signatures and runs `make openapi`; `docs/api/openapi.json` is committed.
4. On that contract, in parallel: Backend implements the services, Frontend generates its types and builds the screens, Tester writes failing acceptance and contract tests, DevOps works in its own area.
5. Tester verifies independently; arch-reviewer checks placement and layers; security-reviewer as required.
6. Devil's Advocate reviews the diff and the "not verified" list.
7. Conductor merges and writes the handoff, with its follow-ups list.

## UI design flow (frontend M and L)

Frontend work of size M or L goes through these steps before and while screens are built. Frontend runs each step with `ui-design`; the planning UX doc (screen map, journeys) is its input when the task references it.

1. UI architecture: the page map and navigation, and the 3 most used pages (for example the dashboard).
2. Design system on those 3 pages: colours, typography, spacing, layout and grid, core components, written as CSS tokens in one file under `frontend/` plus static HTML mockups in `docs/01-architecture/ui/` that link the same file. The User approves or asks for changes (gate 7, once per project).
3. Mockups of all other pages with the approved rules.
4. When every page has a mockup, Frontend builds the pages one by one, importing the same tokens file.
5. After each page, Tester writes its Playwright e2e tests and runs them in the e2e container (UI e2e, below).

## Shared artifacts

Roles meet in three files, never in each other's code.

| Artifact | Written by | Read by | Changed by |
|---|---|---|---|
| Module plan (task file): files, layer, placement reason (ARCH-0006) | Architect | Backend, arch-reviewer | Architect only; a file outside the plan is a question |
| API contract `docs/api/openapi.json` (ARCH-0007) | generated by Backend (`make openapi`) | Frontend (generated types), Tester (contract tests) | Architect's decision; `make check` fails on a silent change |
| Acceptance criteria (task file) | Conductor | every role | Conductor, with the User |

Tests by owner: Backend and Frontend write the unit and component tests of their own code; Tester owns `integration`, `e2e`, `smoke`, the contract tests and the Playwright UI e2e tests (`frontend/e2e/`), and never edits product code. A bug found by Tester goes back to the author with a reproduction.

## Gates: the only reasons to ask the User

1. Money: any paid service or resource, or anything above the monthly cap (default 0 USD; cap 20 USD/month for paid development use).
2. Security: a new secret, opening external access, a change beyond the ADR's auth model, a destructive command outside the project.
3. Irreversible data operations (destructive migration).
4. A critical Devil's Advocate objection (CRITICAL as in principle 11) that the Conductor rejects.
5. A loop unresolved after three attempts.
6. Planning approval, once per project: scope, ADR set, budget cap.
7. Design system approval, once per project: the design system doc and the mockups of the top 3 pages. The User approves or asks for changes; changes go back to Frontend and the same question is asked again.

Everything else proceeds without asking: ports, cleanup of this project's labelled containers and untagged images (`dockerw clean --apply`), merging, docs status. A new dependency is not on that list: the Architect decides it and `dep-guard` asks the User when it is installed.

Hooks already enforce the money and security gates (`guard`, `dep-guard`, `edit-guard`, `stop-gate`); roles cannot override them.

The team improves its own role, skill and team files (`.claude/agents/`, `.claude/skills/`, `.claude/team.md`) without asking: `edit-guard` approves such an edit when it keeps the permission fields (`tools`, `allowed-tools`, `permissionMode`, `mcpServers`, `hooks`) as they are. A change to those fields, to a settings file or to a verification file goes to the User. When an improvement is general, the Conductor tells the User to carry it to claude-config with `/promote`.

## Acceptance rule

Docs are `draft` until verified. A task or handoff becomes `accepted` only when the Tester's independent evidence file exists (verify-full, smoke, e2e green). The author cannot accept their own work. The evidence record stays in `docs/`.

Risks from planning: a task from `/design-project` has a section `Doğrulanacak riskler` (finding ID, the risk, the proposed solution, how to verify it, `must-verify` for CRITICAL items). The Conductor passes it to the roles. Backend and Frontend build the proposed solution, or a better one with a note. The Tester verifies each item with a test (red first where possible) and writes one line next to the item in the task file: `doğrulandı` with the test id, `başarısız, denenen: <alternative>` (then fixed and verified again), or `risk kabul` (only with the User's approval, never for a must-verify item). A must-verify item that is not `doğrulandı` blocks acceptance; any other open item goes to the follow-ups. The handoff summary lists the results in one short table: ID, result, evidence.

`make verify-full` calls docker inside make, so an agent cannot run it in the sandbox. The Tester runs the same steps one by one instead (the list is in the Tester role) and records each command with its result in the evidence file; that record counts as verify-full. A step the Tester could not run is UNKNOWN in the record, never green. The User may still run the real `make verify-full`; it is optional.

The steps, each as its own command from the project directory:
1. `make sast`
2. `dockerw compose -f deploy/compose.yaml -f deploy/compose.test.yaml down` (the test database is tmpfs, so this drops its data; never add `-v`)
3. `dockerw compose -f deploy/compose.yaml -f deploy/compose.test.yaml up -d --wait postgres redis`
4. `make migrate-check`
5. `make test-integration`
6. `dockerw compose -f deploy/compose.yaml -f deploy/compose.test.yaml down`, also when an earlier step failed

Steps 4 and 5 need `sandbox.network.allowLocalBinding` in the project (`/grant local-binding`). Without it they fail on localhost: they are UNKNOWN and go to the User.

## Local run

Until the User says to move local run to Docker, the app runs on the host through three scripts the User starts: `deploy/start.sh`, `deploy/stop.sh` and `deploy/restart.sh` (all call `deploy/local.sh`). Postgres and redis run in containers from `compose.development.yaml`; api, worker and web run on the host with reload, `WORKER_MODE=fake` unless the root `.env` says otherwise, logs and pid files in `.cache/local/`. No app image is built for local run, so no untagged images pile up.

- No role runs these scripts (principle 9). A role that adds a process, port, env variable or migration step updates `deploy/local.sh` in the same task and checks it with `bash -n deploy/local.sh`; the handoff tells the User to run `deploy/restart.sh`.
- When the User says to switch to Docker (usually once development ends and the User's feedback rounds start), DevOps moves api, worker and web into `compose.development.yaml`, writes the commands into `deploy/README.md` and records the switch in the task file. The scripts stay until the User asks to remove them.

## UI e2e

Chromium cannot start inside the Claude Code sandbox, so the Playwright tests run only in the `e2e` container of `deploy/compose.test.yaml` (official Playwright image, pinned; `@playwright/test` in `frontend/package.json` pins the same version). The `api` service runs there with `WORKER_MODE: fake`. Specs and `playwright.config.ts` live in `frontend/e2e/`; results and screenshots land in `frontend/e2e-results/`. Only when `frontend/` exists, the Tester runs from the project directory, after steps 1 to 5 above, each as its own command:
1. `dockerw compose -f deploy/compose.yaml -f deploy/compose.test.yaml --profile e2e run --rm e2e`
2. `dockerw compose -f deploy/compose.yaml -f deploy/compose.test.yaml --profile e2e down`, also when step 1 failed; it replaces step 6 above.
3. `dockerw clean --apply`: each run rebuilds the api image and leaves the old one untagged; this removes this project's untagged images and stopped containers.

The User may run the same with `make test-ui`. Tests against the real external services are not part of any of this: the User runs them with `make test-live`.

## DevOps platform connectors

DevOps prepares a deploy package for any topology: single VPS + Compose, Cloudflare + a separate container host, or a distributed multi-host layout. The package is the env-variable contract, production compose overlays, CI templates, a smoke script, rollback notes and run guides.

Each platform is one record: official skill, MCP, permission rule. Adding Vercel or another platform means adding one record, not changing the roles.

| Platform | Skills | MCP | Permissions |
|---|---|---|---|
| Docker | docker/skills (pinned tag) | – (`tools/dockerw`) | project-scoped only |
| Cloudflare | cloudflare/skills | `cloudflare-api` (`execute` asks) | read allowed, writes ask |
| Vercel | vercel-labs/agent-skills (later) | later | later |

MCP servers are given per agent, not globally loaded into the Conductor, so tool schemas do not bloat every conversation.

## Skills and MCP by role

Small skills a role needs on every task are preloaded from the `skills:` list in its agent file. Large reference skills are not preloaded, to keep the agent's context small: the agent loads them with the Skill tool only when the condition in its "Skills (load only when the task needs them)" section holds. A subagent has only the tools its `tools:` line names, so `Skill` and any MCP server a role needs are listed there. This table mirrors the agent files.

| Role | Preloaded | On demand (Skill tool) | MCP / tools |
|---|---|---|---|
| Conductor (main session) | none | saas-fastapi, design-project, kickoff, maintain, remember, promote, placement-audit | `gh` CLI, every installed skill and MCP |
| Architect | placement-audit | postgres-skills | Context7 (`mcp__context7__*`) |
| Backend | new-feature, new-lib-package, migration, api-contract | python-testing-patterns | Context7 (`mcp__context7__*`), `make` targets |
| Frontend | api-contract | ui-design, react-best-practices, frontend-design | Playwright MCP (`mcp__playwright__*`), Context7 (`mcp__context7__*`) |
| Tester | api-contract | python-testing-patterns, webapp-testing | Playwright MCP (`mcp__playwright__*`), Context7 (`mcp__context7__*`), pytest, coverage |
| DevOps | docker-destructive-guardrails | docker-project-foundations, docker-compose-patterns, docker-build-strategies | Context7 (`mcp__context7__*`), Docker via `tools/dockerw` |
| security-reviewer, arch-reviewer, Devil's Advocate | none | none | read-only; the Conductor runs `make sast` and hands its output to security-reviewer |

Context7 sends the query text to context7.com: a query names the library and the question, never project code, data or secrets. `make sast` (semgrep, pinned version, metrics off) is not in `make check` because its registry rules change over time; it runs in `verify-full` and on every L task. Still a candidate, wired to no role: insecure-defaults.

Community skills are read and pinned in `skills.lock` (source, commit, hash, review date) before use; `make skills-verify` fails the check if a pin drifts. Open question: the frontend stack (default React + TypeScript + Vite).
