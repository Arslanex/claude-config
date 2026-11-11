<!-- Performance doc body (docs.py new perf "<name>: performance"). Owner: performance-architect, step 4. Input: the load assumptions of the strategy ADR. No load test: every measurement is `deferred: perf-team`. -->
## Load model
The strategy ADR's load assumptions this doc uses, by reference; a problem with them is a PERF finding for the strategy-architect.

## SLO per flow
| Flow | IDs | Latency target | Error rate | Measurement |
|---|---|---|---|---|
| <flow name> | F-01, US-01 | | | deferred: perf-team |

## Capacity
Database size after 12 months, the indexes frequent queries need (logical table and columns), cache and queue needs, connection pool size. Every number names its source.

## Scaling triggers
The measured value that moves a strategy decision from "now" to "ideal".

## Next steps
What the perf team measures first, each `deferred: perf-team`.

## Findings
- PERF-01 <CRITICAL/MAJOR/MINOR> <claim> | evidence: <doc and ID block>
