---
name: new-lib-package
description: Create a lib package as a small library in the fastapi-saas layout - public API, schema, errors, one entry module and part sub-packages (ARCH-0006). Use before adding or restructuring anything under lib/.
---

Create or restructure a package under `backend/src/<pkg>/lib/`. Read `docs/01-architecture/ARCH-0006-*.md` first.

## 1. Does it belong in lib?
Yes only if it is library-like (a comprehensive piece made of parts, with no knowledge of any feature) or several feature groups use it. Code that one feature group uses lives in that group's `helpers/`. "Might be useful later" is not a reason.

## 2. Design the public API before any file
Write down, in the task file or the package docstring:
- the entry functions (usually one to three) and what each takes and returns;
- the parts: the stages or components the work naturally splits into (for example `extract`, `rules`, `report`), each with one responsibility.
If you cannot name the parts, the code is a helper, not a library.

## 3. Layout
```
lib/<package>/
├── __init__.py   public API only (`__all__`); the docstring introduces the package
├── schema.py     input and output types of the public API
├── errors.py     the package's error codes
├── <entry>.py    one orchestrating module (for example pipeline.py), if needed
└── <part>/       inner modules, one sub-package per part or stage
```
- Nothing else at the package root. No loose module directly under `lib/`.
- `__init__` exposes the entry functions and their types, not every inner name.

## 4. Rules
- Pure: no import of `features`, `interface`, `worker` or `config`. Settings, keys and limits arrive as parameters.
- I/O only through an `infra` object the caller passes in; the package never builds a client itself.
- No import of another lib package. A neutral shared package needs an ADR and an entry in `NEUTRAL_LIBS` (`tests/unit/test_architecture_placement.py`).
- Callers import from the package root only (`<pkg>.lib.<package>`).

## 5. Split by content
A part gets its own module or sub-package for a content reason: separate responsibility, different consumer, pure versus gateway code, a different stage. Never because a file is long.

## 6. Check
`make check`: unit tests mirror the package under `backend/tests/unit/lib/<package>/` with 100% branch coverage.
