<!-- Feature catalog body (docs.py new plan "<name>: feature catalog"). Owner: product-manager, step 2; G2 freezes it. Fill every section in one call; an empty section says `none` and why. A line that starts with an ID defines it, so each F, M, G and R is defined once, by its row in the decision table. -->
## Decision table
| ID | Kind | Title | Priority | Size | Source | INV impact | karar |
|---|---|---|---|---|---|---|---|
| F-01 | F | <brief feature> | P1 | M | brief F-01 | none | |
| M-01 | M | <missing feature> | P2 | S | <why it is missing> | none | |
| G-01 | G | <gap between features> | P2 | S | <which features> | none | |
| R-01 | R | <industry recommendation> | P3 | M | <page title>, source_verified: yes | INV-01 | |

Kinds: F the user's feature, M missing, G gap, R recommendation (at most 10, each with a verified source, rationale, size, suggested priority, dependency and INV impact). The `karar` column stays empty; at gate A the user writes kabul, ret, değiştir, ertele or ekle (accept, reject, modify, defer or add).

## Rationale
- Rationale (M-01): why it is needed and what it depends on. A rationale line never starts with the ID.

## Stories
- US-01 (F-01) As a <user kind>, I want <capability>, so that <outcome>.
  - When <trigger>, the system shall <response>.
  - If <unwanted condition>, then the system shall <response>.
- US-02 (F-01) As a <user kind>, I want <another capability>, so that <outcome>.
  - When <trigger>, the system shall <response>.

Every story names its F. Criteria are EARS sentences, indented under their story, in the doc language (Turkish: `<tetik> olduğunda sistem <yanıt>.`, `Eğer <durum>, sistem <yanıt>.`).

## Rules
- BR-01 (F-01) A business rule that holds across stories.

## Domains
Business areas the features fall into, one line each with their F IDs. The Lead creates one data model doc per area for step 3.

## Open points
Every `ASSUMPTION` and `OPEN` item with its default.
