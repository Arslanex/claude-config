---
name: api-contract
description: Work with the API contract docs/api/openapi.json in a fastapi-saas project - regenerate it, read a contract diff, generate frontend types, write contract tests (ARCH-0007). Use before adding or changing an endpoint or its consumers.
---

The API contract is `docs/api/openapi.json`. Code is the single source (service schemas and route signatures); the file is generated and committed. Read `docs/01-architecture/ARCH-0007-*.md` first.

## Commands
- `make openapi`: regenerate the contract from the code.
- `make openapi-check` (part of `make check`): fails when the committed file differs from the code.
- Never edit the JSON by hand.

## Backend: contract first
1. Write `XIn`/`XOut` in the feature's `schema.py` and the route signature (path, method, status code, return type). Leave the service body for later.
2. `make openapi`, then `git diff docs/api/openapi.json`.
3. Report the diff: added paths, changed fields, anything removed or renamed.
4. Removing or renaming a path or field, changing a type or a status code breaks consumers: stop and return the question to the Architect. Adding an optional field or a new path is compatible.

## Frontend: generated types
- Types come from the contract, never typed by hand. Use the repo's own script if `package.json` has one; otherwise propose `openapi-typescript` (a new dev dependency: the Architect decides, the user approves the install):
  `npx openapi-typescript ../docs/api/openapi.json -o src/shared/api/schema.d.ts`
- Regenerate after every contract change and fix the compile errors; a compile error is the contract telling you what changed.
- A field the screen needs but the contract lacks is a question for the Architect, not a local type.

## Tester: contract tests
- For each path in the contract: the status codes it declares, the response shape, the required fields of the request.
- Write them from the contract and the acceptance criteria, not from the implementation; they can be written as soon as the contract is committed.
- A response that differs from the contract is a bug report (path, expected from the contract, actual).

## When `openapi-check` is red
- You changed a schema or a route on purpose: `make openapi`, review the diff, mention it in your report.
- You did not mean to change the API: revert the schema or route change.
