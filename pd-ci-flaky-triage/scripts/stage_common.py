#!/usr/bin/env python3
"""Low-level helpers shared by staged PD CI flaky scripts."""

from __future__ import annotations

import concurrent.futures
import datetime as dt
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
LEGACY_PATH = SCRIPT_DIR / "triage_pd_ci_flaky.py"
LEGACY_SPEC = importlib.util.spec_from_file_location("pd_ci_flaky_legacy", LEGACY_PATH)
LEGACY = importlib.util.module_from_spec(LEGACY_SPEC)
assert LEGACY_SPEC and LEGACY_SPEC.loader
sys.modules[LEGACY_SPEC.name] = LEGACY
LEGACY_SPEC.loader.exec_module(LEGACY)

UTC = dt.timezone.utc


def read_json(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: str | Path, payload: object) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)


def build_window_payload(start: dt.datetime, end: dt.datetime) -> dict[str, str]:
    return {
        "start": start.astimezone(UTC).isoformat(),
        "end": end.astimezone(UTC).isoformat(),
    }


def split_actions_ci_name(ci_name: str) -> tuple[str, str]:
    if " / " in ci_name:
        workflow_name, job_name = ci_name.split(" / ", 1)
        return workflow_name, job_name
    return ci_name, ci_name


def serialize_prow_failure(record: Any) -> dict[str, Any]:
    return {
        "source": "prow",
        "source_item_id": record.record_id,
        "job_name": record.ci_name,
        "ci_name": record.ci_name,
        "ci_url": record.ci_url,
        "log_url": record.log_url,
        "occurred_at": record.occurred_at,
        "pr_number": record.pr_number,
        "commit_sha": record.commit_sha,
        "build_id": record.run_id,
        "status": record.status,
    }


def serialize_actions_failure(record: Any) -> dict[str, Any]:
    workflow_name, job_name = split_actions_ci_name(record.ci_name)
    return {
        "source": "actions",
        "source_item_id": record.record_id,
        "workflow_name": workflow_name,
        "job_name": job_name,
        "ci_name": record.ci_name,
        "ci_url": record.ci_url,
        "occurred_at": record.occurred_at,
        "commit_sha": record.commit_sha,
        "run_id": record.run_id,
        "job_id": record.job_id,
        "status": record.status,
    }


def deserialize_failure_item(item: dict[str, Any]) -> Any:
    source = item["source"]
    if source == "prow":
        return LEGACY.FailureRecord(
            record_id=item["source_item_id"],
            source="prow",
            ci_name=item["ci_name"],
            ci_url=item["ci_url"],
            log_url=item.get("log_url"),
            occurred_at=item["occurred_at"],
            pr_number=item.get("pr_number"),
            commit_sha=item.get("commit_sha"),
            run_id=str(item.get("build_id") or ""),
            job_id=None,
            status=item["status"],
        )
    if source == "actions":
        return LEGACY.FailureRecord(
            record_id=item["source_item_id"],
            source="actions",
            ci_name=item["ci_name"],
            ci_url=item["ci_url"],
            log_url=None,
            occurred_at=item["occurred_at"],
            pr_number=None,
            commit_sha=item.get("commit_sha"),
            run_id=str(item.get("run_id") or ""),
            job_id=item.get("job_id"),
            status=item["status"],
        )
    raise ValueError(f"unsupported failure source: {source}")


def _prepare_log_root(source: str, base_dir: str | None) -> Path:
    root = Path(base_dir) if base_dir else Path("/tmp/pd-ci-flaky-stages")
    now = dt.datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    target = root / f"{source}-logs-{now}-{os.getpid()}"
    target.mkdir(parents=True, exist_ok=True)
    return target


def _serialize_log_item(source_item: dict[str, Any], downloaded: Any) -> dict[str, Any]:
    item = {
        "source": source_item["source"],
        "source_item_id": source_item["source_item_id"],
        "ci_name": source_item["ci_name"],
        "ci_url": source_item["ci_url"],
        "log_ref": str(downloaded.path),
        "occurred_at": source_item["occurred_at"],
        "commit_sha": source_item.get("commit_sha"),
        "status": source_item["status"],
    }
    if source_item["source"] == "prow":
        item["job_name"] = source_item["job_name"]
        item["pr_number"] = source_item.get("pr_number")
        item["build_id"] = source_item.get("build_id")
        item["log_url"] = source_item.get("log_url")
    else:
        item["workflow_name"] = source_item.get("workflow_name")
        item["job_name"] = source_item.get("job_name")
        item["run_id"] = source_item.get("run_id")
        item["job_id"] = source_item.get("job_id")
    return item


def fetch_logs_for_failures(
    *,
    failures_payload: dict[str, Any],
    repo: str,
    retries: int,
    download_workers: int = 8,
    log_spool_dir: str | None = None,
) -> dict[str, Any]:
    summary = LEGACY.RunSummary(
        scanned_window_start=failures_payload["window"]["start"],
        scanned_window_end=failures_payload["window"]["end"],
    )
    source = failures_payload["source"]
    records = [deserialize_failure_item(item) for item in failures_payload.get("failures", [])]
    source_items = {item["source_item_id"]: item for item in failures_payload.get("failures", [])}
    spool_dir = _prepare_log_root(source, log_spool_dir)
    logs: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []

    def fetch(record: Any) -> tuple[str, Any | None, str | None]:
        downloaded, err = LEGACY.fetch_and_spool_log(
            record=record,
            repo=repo,
            summary=summary,
            retries=retries,
            spool_dir=spool_dir,
        )
        return record.record_id, downloaded, err

    workers = max(1, download_workers)
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        future_map = {executor.submit(fetch, record): record for record in records}
        for future in concurrent.futures.as_completed(future_map):
            record_id, downloaded, err = future.result()
            if err or downloaded is None:
                skipped.append({"source_item_id": record_id, "reason": err or "empty_or_unavailable"})
                continue
            logs.append(_serialize_log_item(source_items[record_id], downloaded))

    logs.sort(key=lambda item: item["source_item_id"])
    skipped.sort(key=lambda item: item["source_item_id"])
    return {
        "source": source,
        "repo": repo,
        "window": failures_payload["window"],
        "log_root": str(spool_dir),
        "counts": {
            "inputs": len(records),
            "logs": len(logs),
            "skipped": len(skipped),
        },
        "logs": logs,
        "skipped": skipped,
        "summary": {
            "skipped_unknown": list(summary.skipped_unknown),
            "command_failed_after_retries": list(summary.command_failed_after_retries),
        },
    }


def load_open_closed_issues(repo: str, retries: int = 3) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    summary = LEGACY.RunSummary(scanned_window_start="", scanned_window_end="")
    open_issues = LEGACY.load_flaky_issues(repo=repo, state="open", summary=summary, retries=retries)
    closed_issues = LEGACY.load_flaky_issues(repo=repo, state="closed", summary=summary, retries=retries)
    return open_issues, closed_issues
