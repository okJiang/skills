#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from typing import Any


FAILURE_STATES = {
    "ACTION_REQUIRED",
    "CANCELLED",
    "ERROR",
    "FAILURE",
    "STALE",
    "STARTUP_FAILURE",
    "TIMED_OUT",
}

STATICS_NAMES = {"statics", "check pd / statics"}


def run_gh(repo: str, args: list[str]) -> str:
    proc = subprocess.run(
        ["gh", *args],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0 and not proc.stdout:
        raise RuntimeError(proc.stderr.strip() or f"gh {' '.join(args)} failed")
    return proc.stdout


def normalize_pr(value: str) -> int:
    if value.isdigit():
        return int(value)
    match = re.search(r"/pull/(\d+)", value)
    if match:
        return int(match.group(1))
    raise ValueError(f"unsupported PR value: {value}")


def load_checks(repo: str, pr_number: int) -> list[dict[str, Any]]:
    output = run_gh(repo, ["pr", "checks", str(pr_number), "--json", "name,state,link"])
    return json.loads(output or "[]")


def pick_statics(checks: list[dict[str, Any]]) -> dict[str, Any] | None:
    for check in checks:
        name = str(check.get("name", "")).strip().lower()
        if name in STATICS_NAMES or "static" in name:
            return check
    return None


def has_conflict(pr: dict[str, Any]) -> bool:
    mergeable = str(pr.get("mergeable") or "").upper()
    merge_state = str(pr.get("mergeStateStatus") or "").upper()
    return mergeable == "CONFLICTING" or merge_state == "DIRTY"


def load_pr(repo: str, pr_number: int) -> dict[str, Any]:
    output = run_gh(
        repo,
        [
            "pr",
            "view",
            str(pr_number),
            "--json",
            "number,title,url,headRefName,baseRefName,mergeable,mergeStateStatus",
        ],
    )
    return json.loads(output)


def load_pr_numbers(repo: str, author: str, limit: int) -> list[int]:
    output = run_gh(
        repo,
        [
            "pr",
            "list",
            "--author",
            author,
            "--state",
            "open",
            "--limit",
            str(limit),
            "--json",
            "number",
        ],
    )
    return [int(item["number"]) for item in json.loads(output or "[]")]


def summarize_pr(repo: str, pr_number: int) -> dict[str, Any]:
    pr = load_pr(repo, pr_number)
    checks = load_checks(repo, pr_number)
    statics = pick_statics(checks)

    statics_state = None
    statics_link = None
    if statics is not None:
        statics_state = statics.get("state")
        statics_link = statics.get("link")

    problems: list[str] = []
    if statics_state in FAILURE_STATES:
        problems.append("statics")
    if has_conflict(pr):
        problems.append("conflict")

    return {
        "number": pr["number"],
        "title": pr["title"],
        "url": pr["url"],
        "headRefName": pr["headRefName"],
        "baseRefName": pr["baseRefName"],
        "mergeable": pr.get("mergeable"),
        "mergeStateStatus": pr.get("mergeStateStatus"),
        "staticsState": statics_state,
        "staticsLink": statics_link,
        "problems": problems,
    }


def render_text(results: list[dict[str, Any]], include_clean: bool, author: str) -> None:
    if not results:
        print(f"No open tikv/pd PRs for {author} matched statics failures or merge conflicts.")
        return

    for item in results:
        problems = ",".join(item["problems"]) if item["problems"] else "clean"
        print(
            f"PR #{item['number']} [{problems}] "
            f"statics={item['staticsState'] or '-'} "
            f"mergeable={item['mergeable'] or '-'} "
            f"mergeState={item['mergeStateStatus'] or '-'} "
            f"branch={item['headRefName']}"
        )
        print(f"  {item['title']}")
        print(f"  {item['url']}")
        if item["staticsLink"]:
            print(f"  statics: {item['staticsLink']}")
        if include_clean and not item["problems"]:
            print("  no actionable statics/conflict issue detected")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inspect okJiang's open tikv/pd PRs for statics failures or merge conflicts."
    )
    parser.add_argument("--repo", default=".", help="Path inside the tikv/pd repo")
    parser.add_argument("--author", default="okJiang", help="GitHub author login")
    parser.add_argument("--limit", type=int, default=30, help="Maximum open PRs to inspect")
    parser.add_argument("--pr", help="Specific PR number or URL")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    parser.add_argument(
        "--include-clean",
        action="store_true",
        help="Include clean PRs in the output instead of only actionable ones",
    )
    args = parser.parse_args()

    try:
        if args.pr:
            pr_numbers = [normalize_pr(args.pr)]
        else:
            pr_numbers = load_pr_numbers(args.repo, args.author, args.limit)
        results = [summarize_pr(args.repo, number) for number in pr_numbers]
    except Exception as exc:  # pragma: no cover - CLI guardrail
        print(str(exc), file=sys.stderr)
        return 2

    show_clean = args.include_clean or bool(args.pr)
    if not show_clean:
        results = [item for item in results if item["problems"]]

    if args.json:
        print(json.dumps(results, indent=2, sort_keys=True))
    else:
        render_text(results, show_clean, args.author)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
