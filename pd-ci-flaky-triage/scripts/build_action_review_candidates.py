#!/usr/bin/env python3
"""Build action review candidates for agent final review."""

from __future__ import annotations

import argparse

from stage_common import LEGACY, read_json, write_json


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


def _filter_observations_for_downstream(
    observation_payloads: list[dict],
    *,
    env_review_payload: dict | None,
    env_review_decisions: dict | None,
) -> list[dict]:
    if env_review_payload is None or env_review_decisions is None:
        return observation_payloads
    decisions = _validated_env_decisions(env_review_payload, env_review_decisions)
    filtered = []
    for payload in observation_payloads:
        kept = []
        for item in payload.get("observations", []):
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
                    "observations": len(kept),
                },
                "observations": kept,
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


def _group_observations(observation_payloads: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for payload in observation_payloads:
        for item in payload.get("observations", []):
            grouped.setdefault(item["group_key"], []).append(item)
    for values in grouped.values():
        values.sort(key=lambda item: item["candidate_id"])
    return grouped


def build_action_review_candidates_payload(
    *,
    observation_payloads: list[dict],
    issue_match_payload: dict,
    env_review_payload: dict | None = None,
    env_review_decisions: dict | None = None,
    issue_labels: str = "type/ci",
) -> dict:
    filtered_payloads = _filter_observations_for_downstream(
        observation_payloads,
        env_review_payload=env_review_payload,
        env_review_decisions=env_review_decisions,
    )
    grouped = _group_observations(filtered_payloads)
    issue_match_map = {item["group_key"]: item for item in issue_match_payload.get("candidates", [])}
    labels = LEGACY.parse_label_list(issue_labels)
    candidates = []
    counts = {"create": 0, "comment": 0, "reopen_and_comment": 0, "unknown": 0}
    window = filtered_payloads[0]["window"] if filtered_payloads else {"start": "", "end": ""}

    for group_key, items in sorted(grouped.items()):
        lead = items[0]
        links = _union_preserve_order([item.get("ci_url") for item in items])
        ci_names = _union_preserve_order([item.get("ci_name") for item in items])
        signatures = _union_preserve_order([sig for item in items for sig in item.get("signatures", [])])
        issue_matches = issue_match_map.get(group_key, {"selected_match": None, "matches": []})
        selected_match = issue_matches.get("selected_match")
        pr_numbers = {item.get("pr_number") for item in items if item.get("pr_number") is not None}
        commit_shas = {item.get("commit_sha") for item in items if item.get("commit_sha")}

        if selected_match:
            suggested_action = "reopen_and_comment" if (selected_match.get("state") or "").lower() == "closed" else "comment"
            suggested_action_reason = "matched_existing_issue"
        elif lead["source"] == "prow" and len(pr_numbers) >= 2:
            suggested_action = "create"
            suggested_action_reason = "reproduced_across_prs"
        else:
            suggested_action = "unknown"
            suggested_action_reason = "insufficient_evidence"

        counts[suggested_action] += 1
        candidates.append(
            {
                "candidate_id": group_key,
                "group_key": group_key,
                "source": lead["source"],
                "canonical_target": lead["target"],
                "issue_labels": labels,
                "issue_matches": issue_matches,
                "links": links,
                "ci_names": ci_names,
                "signatures": signatures,
                "debug_only_evidence_summary": lead["debug_only_evidence_summary"],
                "signal_summary": {
                    "occurrences": len(items),
                    "distinct_pr_count": len(pr_numbers),
                    "distinct_sha_count": len(commit_shas),
                },
                "observation_ids": [item["candidate_id"] for item in items],
                "suggested_action": suggested_action,
                "suggested_action_reason": suggested_action_reason,
            }
        )

    return {
        "window": window,
        "counts": {
            "total_candidates": len(candidates),
            "suggested_actions": counts,
        },
        "candidates": candidates,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-json", nargs="+", required=True)
    parser.add_argument("--issue-match-candidates", required=True)
    parser.add_argument("--env-review-payload", default="")
    parser.add_argument("--env-review-decisions", default="")
    parser.add_argument("--issue-labels", default="type/ci")
    parser.add_argument("--out-json", default="/tmp/action_review_candidates.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    observation_payloads = [read_json(path) for path in args.input_json]
    issue_match_payload = read_json(args.issue_match_candidates)
    env_review_payload = read_json(args.env_review_payload) if args.env_review_payload else None
    env_review_decisions = read_json(args.env_review_decisions) if args.env_review_decisions else None
    payload = build_action_review_candidates_payload(
        observation_payloads=observation_payloads,
        issue_match_payload=issue_match_payload,
        env_review_payload=env_review_payload,
        env_review_decisions=env_review_decisions,
        issue_labels=args.issue_labels,
    )
    write_json(args.out_json, payload)
    print(f"wrote {payload['counts']['total_candidates']} action review candidates to {args.out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
