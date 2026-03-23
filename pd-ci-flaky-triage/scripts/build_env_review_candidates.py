#!/usr/bin/env python3
"""Merge source failure items into env review candidates for agent review."""

from __future__ import annotations

import argparse

from stage_common import read_json, write_json


def _payload_failure_items(payload: dict) -> list[dict]:
    return payload.get("failure_items", [])


def build_env_review_candidates_payload(failure_item_payloads: list[dict]) -> dict:
    items = []
    by_source: dict[str, int] = {}
    window = failure_item_payloads[0]["window"] if failure_item_payloads else {"start": "", "end": ""}

    for payload in failure_item_payloads:
        source = payload["source"]
        by_source.setdefault(source, 0)
        for failure_item in _payload_failure_items(payload):
            items.append(
                {
                    "candidate_id": failure_item["candidate_id"],
                    "group_key": failure_item.get("group_key", failure_item["candidate_id"]),
                    "source": failure_item["source"],
                    "target": failure_item["target"],
                    "ci_name": failure_item["ci_name"],
                    "ci_url": failure_item["ci_url"],
                    "log_ref": failure_item["log_ref"],
                    "signatures": failure_item["signatures"],
                    "failure_family": failure_item.get("failure_family"),
                    "evidence_lines": failure_item["evidence_lines"],
                    "excerpt_lines": failure_item.get("excerpt_lines", []),
                    "excerpt_start_line": failure_item.get("excerpt_start_line"),
                    "excerpt_end_line": failure_item.get("excerpt_end_line"),
                    "excerpt_confidence": failure_item.get("excerpt_confidence"),
                    "excerpt_reason": failure_item.get("excerpt_reason", ""),
                    "debug_only_evidence_summary": failure_item["debug_only_evidence_summary"],
                }
            )
            by_source[source] += 1

    return {
        "window": window,
        "counts": {
            "total_candidates": len(items),
            "by_source": by_source,
        },
        "items": items,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-json", nargs="+", required=True)
    parser.add_argument("--out-json", default="/tmp/env_review_candidates.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    failure_item_payloads = [read_json(path) for path in args.input_json]
    payload = build_env_review_candidates_payload(failure_item_payloads)
    write_json(args.out_json, payload)
    print(f"wrote {payload['counts']['total_candidates']} env review candidates to {args.out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
