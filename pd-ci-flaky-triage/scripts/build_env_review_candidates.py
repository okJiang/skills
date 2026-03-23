#!/usr/bin/env python3
"""Merge source observations into env review candidates for agent review."""

from __future__ import annotations

import argparse

from stage_common import read_json, write_json


def build_env_review_candidates_payload(observation_payloads: list[dict]) -> dict:
    items = []
    by_source: dict[str, int] = {}
    window = observation_payloads[0]["window"] if observation_payloads else {"start": "", "end": ""}

    for payload in observation_payloads:
        source = payload["source"]
        by_source.setdefault(source, 0)
        for observation in payload.get("observations", []):
            items.append(
                {
                    "candidate_id": observation["candidate_id"],
                    "group_key": observation.get("group_key", observation["candidate_id"]),
                    "source": observation["source"],
                    "target": observation["target"],
                    "ci_name": observation["ci_name"],
                    "ci_url": observation["ci_url"],
                    "log_ref": observation["log_ref"],
                    "signatures": observation["signatures"],
                    "evidence_lines": observation["evidence_lines"],
                    "debug_only_evidence_summary": observation["debug_only_evidence_summary"],
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
    observation_payloads = [read_json(path) for path in args.input_json]
    payload = build_env_review_candidates_payload(observation_payloads)
    write_json(args.out_json, payload)
    print(f"wrote {payload['counts']['total_candidates']} env review candidates to {args.out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
