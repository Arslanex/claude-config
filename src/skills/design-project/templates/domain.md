<!-- Data model body for one domain (docs.py new domain "<area>"). Owner: solution-architect, step 3. Logical model only: migrations, ORM classes and layers belong to the dev team. Only D and E IDs may start a line in this doc; each entity is an E ID, so a change to it is a contract change. -->
## Overview
What this domain keeps and which F and US need it.

## Data model
#### D-01 ERD: <domain>
Covers: F-01
(erDiagram, table first, at most 12 entities; rules in diagrams.md)

## Entities
### E-01 <table_name>
- Meaning: one sentence; the F and US it serves (F-01, US-01).
- Key and uniqueness: `id` UUIDv7; unique rules (per tenant).
- Tenant rule: `tenant_id`, isolation, who may read and write.
- Lifecycle: create, update, archive or delete, restore; history kept or not.
- Volume: expected rows per tenant after 12 months.

## Lifecycle
One `stateDiagram-v2` per entity with states, each under its own `#### D-xx` heading.

## Rules and lock order
- Rule (BR-01): what the database or the service enforces.
- Lock order: the order in which rows are locked when one action writes several entities.

## Open points
Every `ASSUMPTION` and `OPEN` item with its default.
