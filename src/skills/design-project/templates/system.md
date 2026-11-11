<!-- System ADR body (docs.py new adr "<name>: system architecture"). Owner: solution-architect, step 3, written after the data model in the same call. Status stays draft. Only D and API IDs may start a line in this doc; each endpoint or event is an API ID, so a change to it is a contract change. -->
## Context
The stories that shape the system and the accepted docs it follows (INV doc, the project's accepted ARCH docs).

## Components and deployment
#### D-02 Containers
Covers: F-01
(flowchart LR with subgraphs for trust zones; rules in diagrams.md)

## API endpoints and events
- API-01 <method and logical path, or event name>: purpose; caller; entities E-01; stories US-01.

## Key flows
One `sequenceDiagram` per flow that crosses a component or an external system, each under its own `#### D-xx` heading with `Covers:`.

## Choices
| Topic | Choice | Why | Rejected option and why |
|---|---|---|---|

## INV compliance
One line per INV: kept, and how, for example:
- Kept (INV-01): every table has tenant_id and an RLS policy.

## Open points
Every `ASSUMPTION` and `OPEN` item with its default.
