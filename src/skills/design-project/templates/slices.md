<!-- Delivery slices body (docs.py new plan "<name>: delivery slices"). Owner: product-manager, step 5. Each slice becomes one dev task at handoff: its US criteria form the Definition of done and its Verification lines the planned verification. -->
## Slices
### S0 Walking skeleton: <outcome>
- Stories: US-01
- Features: F-01
- Entities: E-01
- Endpoints and events: API-01
- Screens: sign-in, home
- Security: SEC-01
- Performance: PERF-01
- Verification: isolation test for SEC-01, tenant A cannot read tenant B.
- Verification: SLO of the sign-in flow, deferred: perf-team.

### S1 <vertical slice outcome>
- Stories: US-02
- Features: F-01
- Verification: <test kind and what it shows>.

Rules: S0 runs end to end and deploys; later slices are vertical and ordered by value and dependency. Every P1 F is in a slice, every story in exactly one slice, every SEC and PERF item in a slice or `deferred: perf-team`. A criterion that cannot be tested in an earlier slice moves to the right one. Write `Doğrulama:` instead of `Verification:` in a Turkish doc.

## Late features
Features proposed after gate A, as M rows with `proposed` status in the catalog; list their IDs here, or `none`.
