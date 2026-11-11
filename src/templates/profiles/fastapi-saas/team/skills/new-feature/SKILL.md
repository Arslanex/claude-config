---
name: new-feature
description: Create or extend a backend feature in the fastapi-saas layout - service, schema, errors, helpers, route, wiring and tests in the right places (ARCH-0005, 0006). Use before adding a feature, sub-feature or endpoint.
---

Add a feature (or sub-feature) the way this repo's architecture expects. Read `docs/01-architecture/ARCH-0005-*.md` and `ARCH-0006-*.md` first; the task file's Module plan decides the file list.

## 1. Decide the shape
- New feature group `features/<group>/` when the work has its own data and rules; a sub-feature `features/<group>/<sub>/` when it is a separate use-case group with its own `In`/`Out` and error codes inside an existing group.
- Do not create a feature for code another feature would only call as a function: that is a helper (one group) or a `lib` package (several groups).

## 2. Files, in this order
1. `schema.py`: `XIn` for every method input, `XOut` for every output. JSON field names are the API contract.
2. `errors.py`: the feature's error codes (code, kind, message). No HTTP status here.
3. `service.py`: one class; dependencies (unit of work, settings, gateways) come through the constructor. Every public method takes `...In` and returns `...Out` or `None`; request context (`actor=`, `client=`) is keyword-only. The service never commits and imports no SQLAlchemy.
4. `__init__.py`: re-export the service, its schemas and errors (`__all__`). Never re-export a helper.
5. `helpers/<purpose>.py`: only when the placement rules send code there (below).
6. `interface/http/routes/<group>.py` (or `routes/<group>/<sub>.py`): one function per endpoint that turns the request into `XIn`, calls one service method and returns `XOut`. Wire the service in `interface/http/deps/`.
7. CLI command or worker job for the same work calls the same service method.

## 3. Where does extra code go (first yes wins)
1. Crosses a network, disk or process boundary -> `infra/<gate>/`.
2. HTTP-only -> `interface/http/middleware/` or `interface/http/security/`.
3. Used by this feature group only -> its `helpers/` (the sub-feature's if only one sub-feature uses it).
4. Library-like or used by several groups -> `lib/<package>/` (skill `new-lib-package`).
A single small function with one caller stays a private function in `service.py`. Fixed names for recurring roles: `views.py` (model -> `Out`), `policy.py` (rules, permissions), `access.py` (access gate). Never `utils`, `common`, `misc`.

## 4. Contract first
For an endpoint: after step 1 and the route signatures, run `make openapi` and report the contract diff (skill `api-contract`) before writing the service body.

## 5. Tests
- Unit tests mirror the source path under `backend/tests/unit/`; branch coverage is 100%.
- Integration, e2e and contract tests belong to the Tester; do not write them.

## 6. Check
`make check`. A red `test_architecture_placement.py` names the file and the rule; fix the placement, never the test.
