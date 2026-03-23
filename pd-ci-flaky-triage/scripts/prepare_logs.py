#!/usr/bin/env python3
"""Collect recent failures and fetch raw logs into source-specific artifacts."""

from __future__ import annotations

import argparse
import datetime as dt

from stage_common import (
    LEGACY,
    build_window_payload,
    fetch_logs_for_failures,
    serialize_actions_failure,
    serialize_prow_failure,
    write_json,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default="tikv/pd")
    parser.add_argument("--days", type=int, default=1)
    parser.add_argument("--max-prow-pages", type=int, default=30)
    parser.add_argument("--max-action-runs", type=int, default=500)
    parser.add_argument("--retry-count", type=int, default=3)
    parser.add_argument("--download-workers", type=int, default=8)
    parser.add_argument("--log-spool-dir", default="")
    parser.add_argument("--prow-failures-json", default="/tmp/prow_failures.json")
    parser.add_argument("--actions-failures-json", default="/tmp/actions_failures.json")
    parser.add_argument("--prow-logs-json", default="/tmp/prow_logs.json")
    parser.add_argument("--actions-logs-json", default="/tmp/actions_logs.json")
    return parser.parse_args()


def _build_prow_failures_payload(
    *,
    repo: str,
    start: dt.datetime,
    end: dt.datetime,
    max_pages: int,
    retries: int,
) -> dict:
    summary = LEGACY.RunSummary(
        scanned_window_start=start.isoformat(),
        scanned_window_end=end.isoformat(),
    )
    failures, outcomes = LEGACY.collect_prow_failures(
        repo=repo,
        since=start,
        max_pages=max_pages,
        summary=summary,
        retries=retries,
    )
    return {
        "source": "prow",
        "repo": repo,
        "window": build_window_payload(start, end),
        "counts": {
            "failures": len(failures),
            "skipped_unknown": len(summary.skipped_unknown),
            "command_failed_after_retries": len(summary.command_failed_after_retries),
        },
        "failures": [serialize_prow_failure(record) for record in failures],
        "skipped_unknown": list(summary.skipped_unknown),
        "command_failed_after_retries": list(summary.command_failed_after_retries),
        "outcomes_by_ci_sha": {key: sorted(values) for key, values in outcomes.items()},
    }


def _build_actions_failures_payload(
    *,
    repo: str,
    start: dt.datetime,
    end: dt.datetime,
    max_runs: int,
    retries: int,
) -> dict:
    summary = LEGACY.RunSummary(
        scanned_window_start=start.isoformat(),
        scanned_window_end=end.isoformat(),
    )
    failures = LEGACY.collect_actions_failures(
        repo=repo,
        since=start,
        max_runs=max_runs,
        summary=summary,
        retries=retries,
    )
    return {
        "source": "actions",
        "repo": repo,
        "window": build_window_payload(start, end),
        "counts": {
            "failures": len(failures),
            "skipped_unknown": len(summary.skipped_unknown),
            "command_failed_after_retries": len(summary.command_failed_after_retries),
        },
        "failures": [serialize_actions_failure(record) for record in failures],
        "skipped_unknown": list(summary.skipped_unknown),
        "command_failed_after_retries": list(summary.command_failed_after_retries),
    }


def main() -> int:
    args = parse_args()
    end = LEGACY.now_utc()
    start = end - dt.timedelta(days=args.days)
    auth_summary = LEGACY.RunSummary(
        scanned_window_start=start.isoformat(),
        scanned_window_end=end.isoformat(),
    )
    if not LEGACY.ensure_gh_auth(summary=auth_summary, retries=args.retry_count):
        return 1

    prow_failures_payload = _build_prow_failures_payload(
        repo=args.repo,
        start=start,
        end=end,
        max_pages=args.max_prow_pages,
        retries=args.retry_count,
    )
    actions_failures_payload = _build_actions_failures_payload(
        repo=args.repo,
        start=start,
        end=end,
        max_runs=args.max_action_runs,
        retries=args.retry_count,
    )
    write_json(args.prow_failures_json, prow_failures_payload)
    write_json(args.actions_failures_json, actions_failures_payload)

    common_fetch_kwargs = {
        "repo": args.repo,
        "retries": args.retry_count,
        "download_workers": args.download_workers,
        "log_spool_dir": args.log_spool_dir or None,
    }
    prow_logs_payload = fetch_logs_for_failures(
        failures_payload=prow_failures_payload,
        **common_fetch_kwargs,
    )
    actions_logs_payload = fetch_logs_for_failures(
        failures_payload=actions_failures_payload,
        **common_fetch_kwargs,
    )
    write_json(args.prow_logs_json, prow_logs_payload)
    write_json(args.actions_logs_json, actions_logs_payload)
    print(
        "wrote "
        f"{prow_failures_payload['counts']['failures']} prow failures to {args.prow_failures_json}, "
        f"{actions_failures_payload['counts']['failures']} actions failures to {args.actions_failures_json}, "
        f"{prow_logs_payload['counts']['logs']} prow logs to {args.prow_logs_json}, and "
        f"{actions_logs_payload['counts']['logs']} actions logs to {args.actions_logs_json}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
