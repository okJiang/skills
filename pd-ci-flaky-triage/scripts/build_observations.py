#!/usr/bin/env python3
"""Parse staged Prow and GitHub Actions logs into observation artifacts."""

from __future__ import annotations

import argparse
from pathlib import Path

from stage_common import LEGACY, deserialize_failure_item, read_json, write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prow-input-json", default="/tmp/prow_logs.json")
    parser.add_argument("--actions-input-json", default="/tmp/actions_logs.json")
    parser.add_argument("--prow-out-json", default="/tmp/prow_observations.json")
    parser.add_argument("--actions-out-json", default="/tmp/actions_observations.json")
    parser.add_argument("--agent-max-log-bytes", type=int, default=8 * 1024 * 1024)
    return parser.parse_args()


def build_observations_from_logs(
    *,
    logs_payload: dict,
    agent_max_log_bytes: int,
) -> dict:
    source = logs_payload["source"]
    observations = []
    skipped = []

    for log_item in logs_payload.get("logs", []):
        record = deserialize_failure_item(log_item)
        log_path = Path(log_item["log_ref"])
        try:
            log_text = log_path.read_text(encoding="utf-8", errors="replace")
            parsed_items = LEGACY.parse_failures_from_log(
                record=record,
                log_text=log_text,
                agent_max_log_bytes=agent_max_log_bytes,
            )
        except Exception as exc:  # noqa: BLE001
            skipped.append({"source_item_id": log_item["source_item_id"], "reason": str(exc)})
            continue

        for index, parsed in enumerate(parsed_items, start=1):
            observation = {
                "candidate_id": f"{source}:{log_item['source_item_id']}:{index}",
                "group_key": f"{source}::{parsed.key}",
                "source": source,
                "source_item_id": log_item["source_item_id"],
                "target": {
                    "test_name": parsed.test_name,
                    "package_name": parsed.primary_package,
                },
                "tests": list(parsed.tests),
                "primary_test": parsed.primary_test,
                "primary_package": parsed.primary_package,
                "failed_packages": list(parsed.failed_packages),
                "signatures": list(parsed.signatures),
                "failure_type": parsed.failure_type,
                "evidence_lines": list(parsed.evidence_lines),
                "debug_only_evidence_summary": parsed.evidence_summary,
                "confidence": parsed.confidence,
                "ci_name": log_item["ci_name"],
                "ci_url": log_item["ci_url"],
                "log_ref": log_item["log_ref"],
                "occurred_at": log_item["occurred_at"],
                "commit_sha": log_item.get("commit_sha"),
                "status": log_item["status"],
            }
            if source == "prow":
                observation["pr_number"] = log_item.get("pr_number")
                observation["source_details"] = {
                    "job_name": log_item.get("job_name"),
                    "build_id": log_item.get("build_id"),
                    "log_url": log_item.get("log_url"),
                }
            else:
                observation["pr_number"] = None
                observation["source_details"] = {
                    "workflow_name": log_item.get("workflow_name"),
                    "job_name": log_item.get("job_name"),
                    "run_id": log_item.get("run_id"),
                    "job_id": log_item.get("job_id"),
                }
            observations.append(observation)

    observations.sort(key=lambda item: (item["group_key"], item["candidate_id"]))
    skipped.sort(key=lambda item: item["source_item_id"])
    return {
        "source": source,
        "window": logs_payload["window"],
        "counts": {
            "logs": len(logs_payload.get("logs", [])),
            "observations": len(observations),
            "skipped": len(skipped),
        },
        "observations": observations,
        "skipped": skipped,
    }


def _build_output(input_json: str, expected_source: str, output_json: str, agent_max_log_bytes: int) -> int:
    logs_payload = read_json(input_json)
    if logs_payload.get("source") != expected_source:
        raise SystemExit(f"expected {expected_source} log artifact, got {logs_payload.get('source')}")
    payload = build_observations_from_logs(
        logs_payload=logs_payload,
        agent_max_log_bytes=agent_max_log_bytes,
    )
    write_json(output_json, payload)
    return int(payload["counts"]["observations"])


def main() -> int:
    args = parse_args()
    prow_count = _build_output(
        input_json=args.prow_input_json,
        expected_source="prow",
        output_json=args.prow_out_json,
        agent_max_log_bytes=args.agent_max_log_bytes,
    )
    actions_count = _build_output(
        input_json=args.actions_input_json,
        expected_source="actions",
        output_json=args.actions_out_json,
        agent_max_log_bytes=args.agent_max_log_bytes,
    )
    print(
        f"wrote {prow_count} prow observations to {args.prow_out_json} "
        f"and {actions_count} actions observations to {args.actions_out_json}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
