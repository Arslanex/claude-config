# SaaS team specification (profile: fastapi-saas)

Status: draft. Scope: the `fastapi-saas` profile only. Other modes (library, mvp, video) get their own team file later; the core (agents, skills, gates) is shared.

## Principles

1. The Conductor is the main session itself. Subagents cannot spawn subagents, so the other roles are subagents that return a short report.
2. Roles talk through files, not chat. The contract is the task file in `docs/`: goal, acceptance criteria, paths the role may write. Reports have a fixed shape: changed files, evidence commands, open risks.
3. Write areas are disjoint, so independent work runs in parallel.
4. The author is never the verifier of their own work.
5. Evidence before claims: command output, red proof for new tests, coverage. "Done" alone is not accepted.
6. Job size decides which roles run (below). The Conductor records the size and why in the task file; the Devil's Advocate or the User may raise it.
7. The team prepares deploy packages; it does not deploy.

## Job size

| Size | Example | Roles |
|---|---|---|
| XS | one file, ~20 lines | Developer + `make check` |
| S | one module's behaviour | Developer + Tester |
| M | new endpoint, schema change | Architect (short note) + Developers + Tester + Devil's Advocate (one light round) |
| L | new module, auth, external dependency, money or security | full flow, all roles, security-reviewer mandatory |

## Roles

| Role | Does | May write | Never |
|---|---|---|---|
| Conductor (main session) | splits the request, sizes it, routes by table, parallelises, checks evidence, keeps the task list | task files, handoffs, merges | product code, skipping a gate, accepting work without evidence |
| System Architect | structure, module boundaries, data model, API contract, ADR/ARCH | `docs/` (ADR, ARCH, domain, plan) | code; marking an ADR accepted |
| Backend Developer | service code, migrations, unit tests with the code | paths named in the task, under `backend/` | compose/Docker/CI, frontend, architecture decisions, weakening tests |
| Frontend Developer | UI, component tests, types from the API contract | `frontend/` (dormant until it exists) | changing the backend contract alone |
| Tester | before: failing acceptance tests from the criteria; after: independent verification, red proof, coverage, flaky tracking | `tests/integration`, `tests/e2e`, `tests/contract`, test infrastructure | product code (returns findings) |
| DevOps | Docker, compose, local CI, ports, image and container hygiene, healthchecks, deploy packages | `deploy/`, `tools/`, CI templates, `.env.example` | deploying, `prune -a`, volumes, other projects' resources |
| MLOps | model and data pipelines, experiment tracking, evaluation | `ml/`, `pipelines/` | paid API or GPU use without the budget gate. Dormant in this profile. |
| Devil's Advocate | evidence-based counter-case before plans/ADRs, after diffs, at closing ("what did we not verify") | one review file | code. Every objection needs a concrete scenario or command; at most 2 rounds. |
| User | decision owner, the gates below | everything | – |

Existing reviewers stay: `arch-reviewer` checks diffs against ADR/ARCH; `security-reviewer` is mandatory for auth, secrets, dependencies and network changes and for size L. `file-explorer` and `structure-explorer` are cheap discovery helpers for the Conductor and Architect.

## Flow (M and L)

1. User gives a task (draft) and the Conductor sizes it.
2. Architect drafts the ADR; Devil's Advocate argues against it; the User approves the ADR (one gate).
3. Tester writes failing acceptance tests; Backend, Frontend and DevOps work in their own areas.
4. Tester verifies independently; arch-reviewer and security-reviewer as required.
5. Devil's Advocate reviews the diff and the "not verified" list.
6. Conductor merges and writes the handoff.

## Gates: the only reasons to ask the User

1. Money: any paid service or resource, or anything above the monthly cap (default 0 USD; cap 20 USD/month for paid development use).
2. Security: a new secret, opening external access, a change beyond the ADR's auth model, a destructive command outside the project.
3. Irreversible data operations (destructive migration).
4. A critical Devil's Advocate objection that the Conductor rejects.
5. A loop unresolved after three attempts.
6. Planning approval, once per project: scope, ADR set, budget cap.

Everything else proceeds without asking: adding a dependency, ports, cleanup of this project's labelled images, merging, docs status.

Hooks already enforce the money and security gates (`guard`, `dep-guard`, `edit-guard`, `stop-gate`); roles cannot override them.

## Acceptance rule

Docs are `draft` until verified. A task or handoff becomes `accepted` only when the Tester's independent evidence file exists (verify-full, smoke, e2e green). The author cannot accept their own work. The evidence record stays in `docs/`.

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

| Role | Skills | MCP / tools |
|---|---|---|
| Conductor | kickoff, maintain, remember, conduct (new) | `gh` CLI |
| Architect | postgres-skills (RLS, indexes, partitioning), FastAPI skill | Context7 |
| Backend | FastAPI, postgres foundational, modern-python, python-testing-patterns | Context7, postgres-mcp (dev/test DB only) |
| Frontend | react-best-practices, webapp-testing | Context7, Playwright MCP |
| Tester | python-testing-patterns, Playwright best practices | pytest, Playwright, coverage |
| DevOps | docker/skills, postgres connection management | Docker via `tools/dockerw`, platform MCPs |
| security-reviewer | semgrep, insecure-defaults (Trail of Bits) | semgrep CLI |
| Devil's Advocate | none | read-only |

Community skills are read and pinned in `skills.lock` (source, commit, hash, review date) before use; `make skills-verify` fails the check if a pin drifts. Open question: the frontend stack (default React + TypeScript + Vite).
