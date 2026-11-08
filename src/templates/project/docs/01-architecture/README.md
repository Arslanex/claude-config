# Architecture

**Purpose:** How the system is built: modules, interfaces, dependencies.

**What goes here:** One doc per module in `modules/`; the generated dependency graph lives in `graph.md`.

**File naming:** `<ID>-<kebab-title>.md` for generated docs (e.g. `ARCH-0001-example-title.md`); lowercase kebab-case otherwise.

**ID prefix:** `ARCH-NNNN`

Create docs with `python3 tools/docs.py new <kind> "<title>"`, not by hand.
