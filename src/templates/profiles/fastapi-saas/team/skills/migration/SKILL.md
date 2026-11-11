---
name: migration
description: Write a safe Alembic migration in a fastapi-saas project - append only, backward compatible expand/contract, never touch a released migration. Use before creating or reviewing any database migration.
---

Write a database migration. Migrations are written by the Backend role and applied by the user (or the deploy pipeline); never apply one to a database that is not the dev or test one.

## Rules
1. Append only: a new migration goes at the end of the chain. A migration that reached the main branch is never edited, deleted or renamed; fix a mistake with a new migration.
2. Backward compatible (expand, then contract): additions first. Dropping, renaming or narrowing a column or table is a separate migration in a later release. The previous release's code must run against the new schema, so a failed deploy can roll back the code without rolling back the database.
3. One migration task at a time: if another open task is writing a migration, do not write a second one; report it.
4. Squashing migrations needs the user's explicit approval and only happens before production exists.
5. A destructive step (drop, rewrite, backfill that overwrites) is an irreversible data operation: ask the user first.

## Steps
1. Change the models under `infra/database/models` (they derive from `Base`; constraint names come from its naming convention).
2. Generate: `cd backend && uv run alembic revision --autogenerate -m "<what changes>"`. Needs `DATABASE_URL` for the dev or test database.
3. Read the generated file. Autogenerate misses data moves, some type changes and server defaults: write those by hand. Write a real `downgrade()`.
4. Rename = add new, copy, switch the code, drop old in a later release. Never `op.alter_column(..., new_column_name=...)` on a live table in one step.
5. New `NOT NULL` column on an existing table: add it nullable or with a server default, backfill, then tighten in a later migration.
6. Row-level security: a new tenant-scoped table gets its policy in the same migration (the security-reviewer checks `RLS-MISSING`).

## Check
- `make migrate-check` (upgrade to head on the test database, then `alembic check` for drift between models and migrations).
- `make verify-full` for the full database-backed run.
- In the report say: the migration is written, not applied; what it changes; whether any step is irreversible.
