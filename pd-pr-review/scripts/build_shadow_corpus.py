#!/usr/bin/env python3
"""Build a categorized historical PR corpus for PD shadow review."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

from pd_pr_review_framework import categorize_shadow_pr


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch merged PD PRs and write a categorized JSONL shadow corpus."
    )
    parser.add_argument("--repo", required=True, help="Path to the local tikv/pd checkout.")
    parser.add_argument("--limit", type=int, default=200, help="Merged PRs to scan.")
    parser.add_argument(
        "--per-category",
        type=int,
        default=10,
        help="Maximum PRs per category in the emitted corpus.",
    )
    parser.add_argument("--out-jsonl", required=True, help="Output JSONL file.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo).resolve()
    if not (repo_root / ".git").exists():
        print("Error: --repo must point at a git checkout.", file=sys.stderr)
        return 1

    prs = gh_json(
        repo_root,
        [
            "pr",
            "list",
            "--state",
            "merged",
            "--limit",
            str(args.limit),
            "--json",
            "number,title,url,mergedAt,body,files",
        ],
    )

    buckets: Dict[str, List[Dict[str, Any]]] = {
        "bugfix": [],
        "schedule-config": [],
        "tso-mcs": [],
        "tests-ci": [],
        "refactor-no-code": [],
    }
    for pr in prs:
        category = categorize_shadow_pr(pr)
        if category in buckets and len(buckets[category]) < args.per_category:
            buckets[category].append(
                {
                    "category": category,
                    "number": pr["number"],
                    "title": pr["title"],
                    "url": pr["url"],
                    "merged_at": pr["mergedAt"],
                    "files": [item["path"] for item in pr.get("files", []) if "path" in item],
                }
            )
        if _looks_like_bugfix(pr) and len(buckets["bugfix"]) < args.per_category:
            buckets["bugfix"].append(
                {
                    "category": "bugfix",
                    "number": pr["number"],
                    "title": pr["title"],
                    "url": pr["url"],
                    "merged_at": pr["mergedAt"],
                    "files": [item["path"] for item in pr.get("files", []) if "path" in item],
                }
            )

    out_path = Path(args.out_jsonl)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as handle:
        for category in ["bugfix", "schedule-config", "tso-mcs", "tests-ci", "refactor-no-code"]:
            for record in buckets[category]:
                handle.write(json.dumps(record, sort_keys=True) + "\n")

    print(
        json.dumps(
            {category: len(records) for category, records in buckets.items()},
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def gh_json(repo_root: Path, args: list[str]) -> Any:
    result = subprocess.run(
        ["gh", *args],
        cwd=repo_root,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "").strip()
        raise SystemExit(message or "gh command failed")
    return json.loads(result.stdout or "[]")


def _looks_like_bugfix(pr: Dict[str, Any]) -> bool:
    title = str(pr.get("title", "")).lower()
    body = str(pr.get("body", "")).lower()
    return any(token in title or token in body for token in ["fix", "bug", "panic", "regression"])


if __name__ == "__main__":
    raise SystemExit(main())
