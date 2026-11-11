<!-- Quality plan body (docs.py new quality "<name>: quality plan"). Owner: quality-engineer, step 6. Never the dev team's tests and never the traceability matrix by hand. -->
## Traceability review
The rate `plan_state.py check` reports, and each `D: none` reason approved or turned into a finding.

## Planned verification
| Test kind | Claim | Slice | Pass condition |
|---|---|---|---|
| isolation | SEC-01 | S0 | |
| measurement, deferred: perf-team | PERF-01 | S1 | |

A line or row that starts with an ID defines it, so the first column is never an ID.

## Cheap performance guards
Page limit on list endpoints, an index for each frequent query, a ceiling on queries per request.

## Process metrics
Traceability rate, open questions, finding close rate, role calls, user contacts.

## Findings
- QA-01 <CRITICAL/MAJOR/MINOR> <claim> | evidence: <doc and ID block>
