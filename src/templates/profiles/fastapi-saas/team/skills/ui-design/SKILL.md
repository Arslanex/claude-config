---
name: ui-design
description: UI design flow of the saas team for the frontend role - UI architecture and the top 3 pages, the design system with its CSS tokens, static HTML mockups of every page, then the build page by page. Use for frontend L or M work.
---

The design flow of the saas team (`.claude/team.md`, Flow). The Conductor runs one step per task; you do the step the task names and return your report. Read the task's UX doc IDs first when the task references them (screen map, journeys, states from `/design-project`); reuse them, never redo them.

## Where things live
- UI architecture doc and design system doc: `python3 tools/docs.py new module "UI architecture"` and `python3 tools/docs.py new module "Design system"`; name both paths in your report. If tools/docs.py is missing, write them under docs/ by hand.
- Design tokens: one CSS file of custom properties under `frontend/` (default `frontend/src/styles/tokens.css`, or where the repo's frontend rules say). The build imports this same file; never copy a value into a component.
- Mockups: one static HTML file per page under `docs/01-architecture/ui/`, linking the tokens file by a relative path, so the user opens it in a browser with no server and no build. No framework, no CDN, no script beyond what a state toggle needs.

## Step 1: UI architecture
- Page map: every page, its route as the user sees it, who reaches it, and the navigation between pages (a Mermaid diagram plus a table).
- Pick the 3 most used pages (for example the dashboard) and write why, from the journeys or the stories.

## Step 2: design system on the top 3 pages
- Load the `frontend-design` skill first and follow it: a deliberate visual direction, not browser or template defaults.
- Define and write down: colours (with contrast that passes WCAG AA), typography (families, scale, weights, line heights), spacing scale, layout and grid (breakpoints, columns, max widths), and the core components (button, input, select, table, card, navigation, dialog, toast, empty, loading and error states).
- Write every value as a token in the tokens file, and mock up the 3 pages with it at desktop and at phone width.
- Stop here. The Conductor shows the doc and the 3 mockups to the user for the design system approval (once per project). On "change", apply the changes and return again; never go to step 3 without the approval recorded in the design system doc.

## Step 3: all pages
- Mock up every other page from the page map with the approved tokens and components only. A new token or component is a change to the design system: list it in the report as a question, do not add it silently.
- Each page shows its loading, error and empty states (a state toggle in the mockup is enough).

## Step 4: build, one page at a time
- Only when every page mockup exists. One page per task, in the page map order the task names.
- Build it with the repo's stack, importing the same tokens file; reuse the core components; match the mockup.
- Component tests come with the code. The Tester then writes and runs the Playwright e2e tests of the page (`.claude/team.md`, UI e2e).

## Report
Add to your normal report: the doc and mockup paths, the tokens file path, and for step 2 the one-paragraph summary the Conductor shows the user.
