<!-- Final package body (docs.py new plan "<name>: final package"). Written by the Lead at gate B from the index and the docs; the user fills the `karar` column. -->
## Features
| Feature | Status | Priority | Slice | Origin | D |
|---|---|---|---|---|---|

## Architecture
Strategy summary (now, ideal, triggers, INV, load assumptions), the data model and the system architecture in a few lines each, with links to their docs.

## Security, performance and quality
Security summary, expected load, SLO, capacity and next steps, traceability rate and planned verification.

## Handoff eligibility
yes, or no with the H codes and the IDs behind them. Only a CRITICAL finding with no proposed solution (open or disputed) blocks.

## Risks for the dev team
| ID | Severity | Risk | Proposed solution | Slice |
|---|---|---|---|---|

Every finding with a proposed solution (çözüm önerildi) and every accepted risk; a CRITICAL one is marked mutlaka doğrula. Planning does not verify them: each goes into the task file of its slice under "Doğrulanacak riskler" and the dev team tries and closes it.

## To decide
| ID | Item | Default | karar |
|---|---|---|---|

Proposed features, open risks outside H (MINOR findings that stayed open included, and from `status` `risks` the tasks and rechecks that closing did not run at the call budget and the `geliştirme ekibine not` items a check call or closing handed to the dev team), disputed findings, collected ASSUMPTION and OPEN items. The ID cell is the item's ID; a row without one (an ASSUMPTION, a dropped recheck) starts with the task that wrote it and a colon, for example `quality: matrix complete`, so a `değiştir` goes back to that task. Values the user writes: onayla, risk kabul, değiştir or kapsamdan çıkar (approve, accept-risk, modify, descope); `kapsamdan çıkar` takes an F, US or BR row and restarts nothing.

## Process cost
Role calls per model, tokens (may be unknown), estimated cost, user contacts, duration.
