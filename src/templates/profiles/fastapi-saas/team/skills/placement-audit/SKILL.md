---
name: placement-audit
description: Read-only audit of a backend against the placement, interface and lib rules (ARCH-0006) - scattered helpers, code in the wrong layer, flat lib packages, fat routes and commands. Reports moves, changes nothing.
allowed-tools: Read, Grep, Glob, Bash(python3 tools/docs.py *)
---

Audit the backend's file placement and report what should move. Report and recommend only: never move, edit or delete a file.

## Rules to audit against
Read `docs/01-architecture/ARCH-0006-*.md` (or the repo's own equivalents named in CLAUDE.md). If the repo's written rules differ, the repo wins; say which rule set you used.

## What to look for
1. Helpers
   - A `helpers/` file with one small function and one caller: belongs in the service as a private function.
   - A helper nobody in its feature group imports: dead.
   - A helper exported from a feature root or used by another feature group: belongs in `lib/`.
   - Several helper files that together form one library-like piece (parts, stages, shared types): candidate `lib/<package>/`.
   - Catch-all names: `utils`, `common`, `misc`, `shared`, `helper`.
2. Wrong layer
   - Under `infra/`: code that crosses no network, disk or process boundary (pure hashing, token encoding, parsing, rules).
   - HTTP-only code (headers, cookies, CSRF, rate limits) outside `interface/http/`.
   - Security code: say for each piece which rule places it (one feature group -> helpers; library-like or several groups -> `lib/security`; HTTP-only -> `interface/http/security`; external verification -> `infra`).
3. lib packages
   - Loose modules at a package root beyond `__init__`, `schema`, `errors` and one entry module; loose modules directly under `lib/`.
   - An `__init__` that re-exports inner names wholesale; callers importing inner modules; lib packages importing each other.
4. Interface
   - A route, CLI command or worker job with a business rule, a query, data processing, or an `infra`/`lib` import.
   - A route or command module that does not mirror a feature group, or serves several sub-features in one file.
5. Splits
   - Files split with no content reason, and files that mix two responsibilities. Judge by content (responsibility, consumer, pure versus gateway, stage); never recommend a split or a merge because of a line count.

## Report
Write one LOG doc with `python3 tools/docs.py new log "Placement audit <YYYY-MM>"` (or print the report if the repo has no `tools/docs.py`). One line per finding:
`<current path> -> <proposed place> | rule | reason | callers to update`
Group by the five headings above, most valuable move first, and end with a suggested order of work in small, separately testable steps. Do not commit.
