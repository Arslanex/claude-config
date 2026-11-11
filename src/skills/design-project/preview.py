#!/usr/bin/env python3
"""
Render the plan review page that the user opens at each gate.

Usage: preview.py <project root, docs folder or doc>... -o <out.html> [--plan PLAN-id]

preview_model reads the docs and the run state (<PLAN-id>.run.json) through plan_state; preview_render writes the
page with the stylesheet and script from preview_assets/. The page is one file that opens from file://; it loads a
pinned Mermaid from a CDN when it is opened and shows the Mermaid source when that script cannot load.
Without a run.json the page still shows the docs. This script makes no network call. Python 3 stdlib only.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from preview_model import (DEFAULT_CALL_LIMIT, DEFAULT_CALL_WARN, FINDING_KINDS, Model, build,  # noqa: E402,F401
                           eligibility, track_of)
from preview_render import render, render_track  # noqa: E402,F401


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render the plan review page from plan docs and the run state.")
    parser.add_argument("paths", nargs="+", type=Path, help="project root, docs folder or docs")
    parser.add_argument("-o", "--out", type=Path, required=True, help="output HTML file")
    parser.add_argument("--plan", help="plan ID whose run.json to read (default: the newest)")
    args = parser.parse_args(argv)
    try:
        model = build(args.paths, args.plan)
    except FileNotFoundError as error:
        print(f"error: not found: {error}", file=sys.stderr)
        return 2
    if not (model.diagrams or model.items or model.findings or model.state or model.pending):
        print("error: nothing to show: no mermaid blocks, plan rows or run state found", file=sys.stderr)
        return 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(model, args.plan or "", args.out.resolve().parent), encoding="utf-8")
    findings = set(model.findings) | {i["id"] for i in model.of_kind(*FINDING_KINDS)}
    print(f"{args.out.resolve()} ({len(model.diagrams)} diagrams)")
    print(f"{len(model.of_kind('F'))} features, {len(findings)} findings")
    return 0


if __name__ == "__main__":
    sys.exit(main())
