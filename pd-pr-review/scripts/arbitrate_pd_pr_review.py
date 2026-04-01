#!/usr/bin/env python3
"""Turn lane result JSON into dry-run output or GitHub comments."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List

from pd_pr_review_framework import arbitrate_skill_results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Dry-run or post PD PR review comments from lane result JSON files."
    )
    parser.add_argument("--context-json", required=True, help="Normalized context JSON file.")
    parser.add_argument(
        "--result-json",
        action="append",
        default=[],
        help="Lane result JSON file. Pass this flag multiple times.",
    )
    parser.add_argument("--post", action="store_true", help="Post comments through gh.")
    parser.add_argument(
        "--user-approved",
        action="store_true",
        help="Required together with --post to confirm explicit user approval.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    context_payload = json.loads(Path(args.context_json).read_text(encoding="utf-8"))
    context = context_payload.get("context", context_payload)
    lane_results = [json.loads(Path(path).read_text(encoding="utf-8")) for path in args.result_json]
    decision = arbitrate_skill_results(context=context, lane_results=lane_results)

    if not args.post:
        print(json.dumps(decision, indent=2, sort_keys=True))
        return 0

    if not args.user_approved:
        print("Error: posting requires --user-approved.", file=sys.stderr)
        return 1

    repo_root = Path(context.get("repo_path", ""))
    pr_number = context.get("pr_number")
    if not repo_root or not pr_number:
        print("Error: posting requires repo_path and pr_number in the context JSON.", file=sys.stderr)
        return 1

    repo_slug = gh_json(repo_root, ["repo", "view", "--json", "nameWithOwner"])["nameWithOwner"]
    head_sha = context.get("head_sha", "")
    failures = post_comments(
        repo_root=repo_root,
        repo_slug=repo_slug,
        pr_number=int(pr_number),
        head_sha=head_sha,
        comments=decision["postable_comments"],
    )
    if failures:
        print(json.dumps({"posted": False, "failures": failures}, indent=2, sort_keys=True))
        return 1

    print(json.dumps({"posted": True, "count": len(decision["postable_comments"])}, indent=2))
    return 0


def post_comments(
    repo_root: Path,
    repo_slug: str,
    pr_number: int,
    head_sha: str,
    comments: Iterable[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    failures: List[Dict[str, Any]] = []
    summary_groups = defaultdict(list)

    for comment in comments:
        if comment["delivery"] == "summary":
            summary_groups[comment["lane"]].append(comment)
            continue
        body = render_comment_body(comment)
        result = subprocess.run(
            [
                "gh",
                "api",
                "--method",
                "POST",
                f"repos/{repo_slug}/pulls/{pr_number}/comments",
                "-f",
                f"body={body}",
                "-f",
                f"commit_id={head_sha}",
                "-f",
                f"path={comment['path']}",
                "-F",
                f"line={comment['line']}",
                "-f",
                "side=RIGHT",
            ],
            cwd=repo_root,
            text=True,
            capture_output=True,
        )
        if result.returncode != 0:
            failures.append(
                {
                    "comment": comment,
                    "stderr": result.stderr.strip(),
                    "stdout": result.stdout.strip(),
                }
            )

    for lane, grouped_comments in summary_groups.items():
        body = render_summary_body(lane, grouped_comments)
        result = subprocess.run(
            ["gh", "pr", "comment", str(pr_number), "--body", body],
            cwd=repo_root,
            text=True,
            capture_output=True,
        )
        if result.returncode != 0:
            failures.append(
                {
                    "lane": lane,
                    "stderr": result.stderr.strip(),
                    "stdout": result.stdout.strip(),
                }
            )

    return failures


def render_comment_body(comment: Dict[str, Any]) -> str:
    evidence = "\n".join(f"- {line}" for line in comment.get("evidence", []))
    check = comment.get("suggested_check") or "n/a"
    return (
        f"**{comment['title']}**\n\n"
        f"{comment['body']}\n\n"
        f"Evidence:\n{evidence}\n\n"
        f"Suggested check: `{check}`"
    )


def render_summary_body(lane: str, comments: Iterable[Dict[str, Any]]) -> str:
    chunks = [f"### {lane}"]
    for comment in comments:
        evidence = "; ".join(comment.get("evidence", []))
        chunks.append(
            f"- **{comment['title']}** ({comment.get('severity', 'non_blocking')}): "
            f"{comment['body']} Evidence: {evidence}"
        )
    return "\n".join(chunks)


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


if __name__ == "__main__":
    raise SystemExit(main())
