#!/usr/bin/env python3
"""Build issue match candidates for kept failure items."""

from __future__ import annotations

import argparse

from stage_common import LEGACY, load_open_closed_issues, read_json, write_json


def _review_decision_index(payload: dict, field: str = "candidate_id") -> dict[str, dict]:
    return {item[field]: item for item in payload.get("decisions", [])}


def _validated_env_decisions(
    env_review_payload: dict,
    env_review_decisions: dict | None,
) -> dict[str, dict]:
    if env_review_decisions is None:
        return {}
    indexed = _review_decision_index(env_review_decisions)
    expected = {item["candidate_id"] for item in env_review_payload.get("items", [])}
    missing = sorted(expected - indexed.keys())
    if missing:
        raise ValueError(f"missing env review decisions for candidates: {', '.join(missing)}")
    return indexed


def _payload_failure_items(payload: dict) -> list[dict]:
    return payload.get("failure_items", [])


def _filter_failure_items_for_downstream(
    failure_item_payloads: list[dict],
    *,
    env_review_payload: dict | None,
    env_review_decisions: dict | None,
) -> list[dict]:
    if env_review_payload is None or env_review_decisions is None:
        return failure_item_payloads
    decisions = _validated_env_decisions(env_review_payload, env_review_decisions)
    filtered = []
    for payload in failure_item_payloads:
        kept = []
        for item in _payload_failure_items(payload):
            decision = decisions[item["candidate_id"]]["decision"]
            if decision == "keep":
                kept.append(item)
                continue
            if decision != "env_filtered":
                raise ValueError(f"unsupported env review decision: {decision}")
        filtered.append(
            {
                **payload,
                "counts": {
                    **payload.get("counts", {}),
                    "failure_items": len(kept),
                },
                "failure_items": kept,
            }
        )
    return filtered


def _union_preserve_order(values: list[str | None]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _group_failure_items(failure_item_payloads: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for payload in failure_item_payloads:
        for item in _payload_failure_items(payload):
            grouped.setdefault(item["group_key"], []).append(item)
    for values in grouped.values():
        values.sort(key=lambda item: item["candidate_id"])
    return grouped


def _score_and_rank_matches(
    issues: list[dict],
    *,
    test_name: str | None,
    package_name: str | None,
    signatures: list[str],
    limit: int,
) -> list[dict]:
    ranked: list[tuple[int, dict]] = []
    for issue in issues:
        score = LEGACY.score_issue_match(
            issue,
            test_name=test_name,
            package_name=package_name,
            signatures=signatures,
        )
        if score <= 0:
            continue
        ranked.append((score, issue))
    ranked.sort(
        key=lambda item: (item[0], LEGACY.parse_iso8601(item[1].get("updatedAt"))),
        reverse=True,
    )
    return [
        {
            "number": match["number"],
            "title": match.get("title"),
            "url": match.get("url"),
            "state": match.get("state"),
            "updatedAt": match.get("updatedAt"),
            "score": score,
        }
        for score, match in ranked[:limit]
    ]


def build_issue_match_candidates_payload(
    *,
    failure_item_payloads: list[dict],
    env_review_payload: dict | None,
    env_review_decisions: dict | None,
    open_issues: list[dict],
    closed_issues: list[dict],
    max_matches: int = 5,
) -> dict:
    filtered_payloads = _filter_failure_items_for_downstream(
        failure_item_payloads,
        env_review_payload=env_review_payload,
        env_review_decisions=env_review_decisions,
    )
    grouped = _group_failure_items(filtered_payloads)
    window = filtered_payloads[0]["window"] if filtered_payloads else {"start": "", "end": ""}
    candidates = []

    for group_key, items in sorted(grouped.items()):
        lead = items[0]
        signatures = _union_preserve_order([sig for item in items for sig in item.get("signatures", [])])
        test_name = lead["target"].get("test_name")
        package_name = lead["target"].get("package_name")
        open_ranked = _score_and_rank_matches(
            open_issues,
            test_name=test_name,
            package_name=package_name,
            signatures=signatures,
            limit=max_matches,
        )
        closed_ranked = _score_and_rank_matches(
            closed_issues,
            test_name=test_name,
            package_name=package_name,
            signatures=signatures,
            limit=max_matches,
        )
        selected = LEGACY.choose_issue_match(
            open_issues,
            test_name=test_name,
            package_name=package_name,
            signatures=signatures,
        )
        if selected is None:
            selected = LEGACY.choose_issue_match(
                closed_issues,
                test_name=test_name,
                package_name=package_name,
                signatures=signatures,
            )
        open_numbers = {match["number"] for match in open_ranked}
        candidates.append(
            {
                "group_key": group_key,
                "source": lead["source"],
                "canonical_target": lead["target"],
                "failure_item_ids": [item["candidate_id"] for item in items],
                "selected_match": (
                    {
                        "number": selected["number"],
                        "title": selected.get("title"),
                        "url": selected.get("url"),
                        "state": selected.get("state"),
                        "updatedAt": selected.get("updatedAt"),
                    }
                    if selected
                    else None
                ),
                "matches": open_ranked + [match for match in closed_ranked if match["number"] not in open_numbers],
            }
        )

    return {
        "window": window,
        "counts": {"candidates": len(candidates)},
        "candidates": candidates,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default="tikv/pd")
    parser.add_argument("--input-json", nargs="+", required=True)
    parser.add_argument("--env-review-payload", required=True)
    parser.add_argument("--env-review-decisions", required=True)
    parser.add_argument("--retry-count", type=int, default=3)
    parser.add_argument("--max-matches", type=int, default=5)
    parser.add_argument("--out-json", default="/tmp/issue_match_candidates.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summary = LEGACY.RunSummary(scanned_window_start="", scanned_window_end="")
    if not LEGACY.ensure_gh_auth(summary=summary, retries=args.retry_count):
        return 1
    failure_item_payloads = [read_json(path) for path in args.input_json]
    env_review_payload = read_json(args.env_review_payload)
    env_review_decisions = read_json(args.env_review_decisions)
    open_issues, closed_issues = load_open_closed_issues(args.repo, retries=args.retry_count)
    payload = build_issue_match_candidates_payload(
        failure_item_payloads=failure_item_payloads,
        env_review_payload=env_review_payload,
        env_review_decisions=env_review_decisions,
        open_issues=open_issues,
        closed_issues=closed_issues,
        max_matches=args.max_matches,
    )
    write_json(args.out_json, payload)
    print(f"wrote {payload['counts']['candidates']} issue match candidates to {args.out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
