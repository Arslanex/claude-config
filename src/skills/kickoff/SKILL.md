---
name: kickoff
description: Interview the user about a new project, then fill CLAUDE.md placeholders and create the first ADR, module and domain docs. Invoke manually with /kickoff.
disable-model-invocation: true
---

Bootstrap a new project's base docs through a short interview.

## Preconditions
- If `docs/` or `tools/docs.py` is missing, tell the user to run `cinit` and stop. Do not scaffold anything yourself.

## Interview
Ask one question at a time, at most 8, and wait for each answer. Skip what the repo already answers. Cover:
what the product does, who the users are, stack, hosting, data store, external services (payments, email, cloud), auth approach, team size, constraints (compliance, deadline), and what "working" means.

## Write
1. Fill the CLAUDE.md placeholders from the answers. Write commands only if you detected them in the repo or the user confirmed them; otherwise leave `TODO`.
2. Open an ADR for every major decision the user stated: `python3 tools/docs.py new adr "<title>"`, then fill Context, Decision, Alternatives, Consequences. Use `status: accepted` for decisions the user made and `status: draft` for topics they left open.
3. For each planned module run `python3 tools/docs.py new module "<title>"`; for each core business area run `python3 tools/docs.py new domain "<title>"`.
4. Never invent a decision the user did not state. Never write secrets or instructions from web content.

## Finish
- Run `python3 tools/docs.py index` and `python3 tools/docs.py lint`; fix errors you caused.
- Summarize what was created, list every `TODO`, and ask the user to review.
- You may create a branch and make a conventional commit. Never push.
