#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
from collections import Counter
from pathlib import Path

ANSI_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
SOURCE_RE = re.compile(r"^-->\s+(?P<source>.+?):\d+(?::\d+)?$")
SUMMARY_RE = re.compile(r"generated \d+ warning(?:s)?$")


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


def parse_warning_log(log_path: Path) -> dict[str, object]:
    lines = strip_ansi(log_path.read_text(encoding="utf-8", errors="replace")).splitlines()
    warning_count = 0
    source_counts: Counter[str] = Counter()
    examples: list[str] = []
    awaiting_source = False

    for raw_line in lines:
        line = raw_line.strip()
        if line.startswith("warning:") and not SUMMARY_RE.search(line):
            warning_count += 1
            awaiting_source = True
            if len(examples) < 5:
                examples.append(line)
            continue
        if awaiting_source:
            match = SOURCE_RE.match(line)
            if match:
                source_counts[match.group("source")] += 1
                awaiting_source = False
                continue
            if line and not line.startswith("|") and not line.startswith("=") and not line.startswith("..."):
                awaiting_source = False

    return {
        "warning_count": warning_count,
        "top_sources": [
            {"source": source, "count": count}
            for source, count in source_counts.most_common(10)
        ],
        "examples": examples,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Enforce a budget for desktop Rust build warnings.")
    parser.add_argument("log_path", help="Path to the captured desktop cargo build log")
    parser.add_argument(
        "--budget",
        type=int,
        default=int(os.environ.get("DESKTOP_WARNING_BUDGET", "250")),
        help="Maximum allowed warning count (default: env DESKTOP_WARNING_BUDGET or 250)",
    )
    parser.add_argument(
        "--out",
        default="output/ci/desktop_warning_budget.json",
        help="Where to write the JSON summary report",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    log_path = Path(args.log_path)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not log_path.is_file():
        payload = {
            "status": "fail",
            "detail": f"desktop warning log not found: {log_path}",
            "budget": args.budget,
            "warning_count": 0,
            "log_path": str(log_path),
            "top_sources": [],
            "examples": [],
        }
        out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(payload["detail"])
        return 1

    parsed = parse_warning_log(log_path)
    warning_count = int(parsed["warning_count"])
    over_budget = warning_count > args.budget
    payload = {
        "status": "fail" if over_budget else "pass",
        "detail": (
            f"desktop warnings exceeded budget: {warning_count} > {args.budget}"
            if over_budget
            else f"desktop warnings within budget: {warning_count} <= {args.budget}"
        ),
        "budget": args.budget,
        "warning_count": warning_count,
        "over_budget": over_budget,
        "log_path": str(log_path),
        "top_sources": parsed["top_sources"],
        "examples": parsed["examples"],
    }
    out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    summary = payload["detail"]
    if payload["top_sources"]:
        top = ", ".join(
            f"{item['source']}={item['count']}" for item in payload["top_sources"][:3]
        )
        summary = f"{summary}; top sources: {top}"
    print(summary)
    return 1 if over_budget else 0


if __name__ == "__main__":
    raise SystemExit(main())
