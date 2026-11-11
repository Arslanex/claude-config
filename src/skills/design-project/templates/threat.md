<!-- Threat model body (docs.py new threat "<name>: threat model"). Owner: security-architect, step 4. Edit no other doc; a change needed elsewhere is a FINDING for its owner. -->
## Trust boundaries
User, tenant, admin, external systems, background work.

## Data classification
| Entity | Class (public, internal, personal, secret) | Why |
|---|---|---|

## STRIDE per boundary
| Boundary | Threat | Control | Finding |
|---|---|---|---|

## Abuse cases
One per P1 flow, with the F or US it targets.

## Authorization matrix
| Action and resource | Owner | Manager | Member | Guest | Tenant rule |
|---|---|---|---|---|---|

## Findings
- SEC-01 <CRITICAL/MAJOR/MINOR> <claim> | evidence: <doc and ID block> | class: H3
