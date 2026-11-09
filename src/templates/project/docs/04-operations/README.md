# Operations

**Purpose:** Runbooks, deployment, environments, monitoring, incident notes.

**What goes here:** Free-form how-to docs, e.g. `deploy.md`, `runbook-db.md`. No secrets, ever.

**File naming:** `<ID>-<kebab-title>.md` for generated docs (e.g. `overview-example-title.md`); lowercase kebab-case otherwise.

**ID prefix:** `RUN` for runbooks (`python3 tools/docs.py new runbook "<title>"`); other files here have no generated IDs

Create docs with `python3 tools/docs.py new <kind> "<title>"`, not by hand.
