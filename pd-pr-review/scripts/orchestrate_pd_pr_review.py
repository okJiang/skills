#!/usr/bin/env python3
"""Build normalized context and a lane execution plan for a PD PR review."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from pd_pr_review_framework import build_risk_map, normalize_pr_context


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch PR context from gh and emit a normalized PD PR review plan."
    )
    parser.add_argument("--repo", required=True, help="Path to the local tikv/pd checkout.")
    parser.add_argument("--pr", required=True, help="PR number or URL.")
    parser.add_argument("--out", help="Optional file path for the JSON plan.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = find_git_root(Path(args.repo))
    if repo_root is None:
        print("Error: --repo is not inside a Git repository.", file=sys.stderr)
        return 1

    if not ensure_gh_auth(repo_root):
        return 1

    pr_number = extract_pr_number(args.pr)
    pr_payload = gh_json(
        repo_root,
        [
            "pr",
            "view",
            str(pr_number),
            "--json",
            "number,title,body,files,baseRefOid,headRefOid,url",
        ],
    )
    diff_text = gh_text(repo_root, ["pr", "diff", str(pr_number)])
    checks_payload = fetch_checks_payload(repo_root, pr_number)
    codeowners_text = read_optional_file(repo_root / ".github" / "CODEOWNERS")

    issue_payload = None
    issue_number = extract_issue_number(str(pr_payload.get("body", "")))
    if issue_number is not None:
        issue_payload = gh_json(
            repo_root,
            ["issue", "view", str(issue_number), "--json", "number,title,body,url,state"],
        )

    context = normalize_pr_context(
        pr_number=pr_number,
        pr_payload=pr_payload,
        issue_payload=issue_payload,
        diff_text=diff_text,
        codeowners_text=codeowners_text,
        checks_payload=checks_payload,
    )
    context["repo_path"] = str(repo_root)
    risk_map = build_risk_map(context)
    context["risk_tags"] = risk_map["risk_tags"]

    plan = {
        "context": context,
        "risk_map": risk_map,
        "selected_lanes": risk_map["selected_lanes"],
        "suggested_checks": risk_map["suggested_checks"],
        "lane_suggested_checks": risk_map["lane_suggested_checks"],
        "result_schema": str(
            (Path(__file__).resolve().parents[1] / "references" / "skill-result-schema.json")
        ),
    }

    payload = json.dumps(plan, indent=2, sort_keys=True)
    if args.out:
        Path(args.out).write_text(payload + "\n", encoding="utf-8")
    print(payload)
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
    return json.loads(result.stdout or "{}")


def fetch_checks_payload(repo_root: Path, pr_number: int) -> Any:
    primary_fields = ["name", "state", "conclusion", "detailsUrl"]
    result = subprocess.run(
        ["gh", "pr", "checks", str(pr_number), "--json", ",".join(primary_fields)],
        cwd=repo_root,
        text=True,
        capture_output=True,
    )
    if result.returncode == 0:
        return json.loads(result.stdout or "[]")

    fallback_fields = select_check_fields(result.stderr or result.stdout or "")
    if not fallback_fields:
        message = (result.stderr or result.stdout or "").strip()
        raise SystemExit(message or "gh pr checks failed")

    return gh_json(
        repo_root,
        ["pr", "checks", str(pr_number), "--json", ",".join(fallback_fields)],
    )


def select_check_fields(message: str) -> list[str]:
    available = []
    collecting = False
    for raw_line in message.splitlines():
        line = raw_line.rstrip()
        if line.startswith("Available fields:"):
            collecting = True
            continue
        if not collecting:
            continue
        stripped = line.strip()
        if not stripped:
            continue
        available.append(stripped)

    fallback_order = ["name", "state", "bucket", "link", "startedAt", "completedAt", "workflow"]
    return [field for field in fallback_order if field in available]


def gh_text(repo_root: Path, args: list[str]) -> str:
    result = subprocess.run(
        ["gh", *args],
        cwd=repo_root,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "").strip()
        raise SystemExit(message or "gh command failed")
    return result.stdout


def ensure_gh_auth(repo_root: Path) -> bool:
    result = subprocess.run(
        ["gh", "auth", "status"],
        cwd=repo_root,
        text=True,
        capture_output=True,
    )
    if result.returncode == 0:
        return True
    message = (result.stderr or result.stdout or "").strip()
    print(message or "Error: gh auth status failed.", file=sys.stderr)
    return False


def find_git_root(path: Path) -> Optional[Path]:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=path,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        return None
    return Path(result.stdout.strip())


def extract_pr_number(value: str) -> int:
    match = re.search(r"(\d+)(?:/)?$", value)
    if match is None:
        raise SystemExit("Error: unable to parse PR number.")
    return int(match.group(1))


def extract_issue_number(body: str) -> Optional[int]:
    match = re.search(r"Issue Number:\s*(?:Close|Closes|Fixes|Ref)?\s*#(\d+)", body, re.IGNORECASE)
    if match is None:
        return None
    return int(match.group(1))


def read_optional_file(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
