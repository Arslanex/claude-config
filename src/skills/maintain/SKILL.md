---
name: maintain
description: Monthly project health report (make check, docs lint, stale docs, open work) written to one LOG doc. Report only, changes nothing else. Invoke manually with /maintain.
disable-model-invocation: true
allowed-tools: Read, Grep, Glob, Bash(make *), Bash(python3 tools/docs.py *)
---

Produce a monthly project health report. Report and recommend only.

## Preconditions
- If `docs/` or `tools/docs.py` is missing, tell the user to run `cinit` and stop. Do not scaffold anything yourself.

## Steps
1. Run `make check` and note the result (pass/fail, first failing step).
2. Run `python3 tools/docs.py lint` and note errors and warnings.
3. Run `python3 tools/docs.py stale --days 90` and note the stale docs.
   - stale scans only living docs (ADR, ARCH, module, domain, plan); tasks, handoffs and logs are historical records and are not flagged.
4. Run `python3 tools/docs.py index`, then read `docs/05-work/INDEX.md` and summarize draft tasks and handoffs, plus any unfinished items under `## Next steps` in handoffs.
5. Write all findings into a single LOG doc: `python3 tools/docs.py new log "Project health <YYYY-MM>"`. Use these headings: Ozet, Kirmizi seyler, Eskiyen belgeler, Acik isler, Onerilen aksiyonlar.

## Rules
- Never fix, delete or move any file. Write only the one LOG doc (and the generated indexes from step 4).
- Never read secret files (`.env` and similar).
- Keep it short: one line per finding.
- Finish by giving the user the LOG path and the top recommended actions. Do not commit or push.
