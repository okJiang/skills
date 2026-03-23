#!/usr/bin/env python3
"""Assemble final triage payload from agent review decisions."""

from __future__ import annotations

import argparse

from stage_common import LEGACY, read_json, write_json


def _review_decision_index(payload: dict, field: str = "candidate_id") -> dict[str, dict]:
    return {item[field]: item for item in payload.get("decisions", [])}


def _validated_env_decisions(
    env_review_payload: dict,
    env_review_decisions: dict,
) -> dict[str, dict]:
    indexed = _review_decision_index(env_review_decisions)
    expected = {item["candidate_id"] for item in env_review_payload.get("items", [])}
    missing = sorted(expected - indexed.keys())
    if missing:
        raise ValueError(f"missing env review decisions for candidates: {', '.join(missing)}")
    return indexed


def _validate_action_decisions(action_review_candidates: dict, action_review_decisions: dict) -> dict[str, dict]:
    indexed = _review_decision_index(action_review_decisions)
    expected = {item["candidate_id"] for item in action_review_candidates.get("candidates", [])}
    missing = sorted(expected - indexed.keys())
    if missing:
        raise ValueError(f"missing action review decisions for candidates: {', '.join(missing)}")
    return indexed


def _candidate_target(decision: dict, candidate: dict) -> dict:
    return decision.get("canonical_target") or candidate.get("canonical_target") or {
        "test_name": None,
        "package_name": None,
    }


def _selected_issue(decision: dict, candidate: dict) -> dict | None:
    issue_number = decision.get("target_issue_number")
    issue_url = decision.get("target_issue_url")
    selected = candidate.get("issue_matches", {}).get("selected_match")
    if issue_number is not None:
        return {
            "number": issue_number,
            "url": issue_url or (selected or {}).get("url"),
        }
    return selected


def _excerpt_candidates(candidate: dict) -> list[dict]:
    return list(candidate.get("excerpt_candidates", []))


def assemble_final_triage_payload(
    *,
    action_review_candidates: dict,
    action_review_decisions: dict,
    env_review_payload: dict,
    env_review_decisions: dict,
) -> dict:
    env_index = _validated_env_decisions(env_review_payload, env_review_decisions)
    action_index = _validate_action_decisions(action_review_candidates, action_review_decisions)
    candidate_map = {item["candidate_id"]: item for item in action_review_candidates.get("candidates", [])}
    payload = {
        "window": action_review_candidates.get("window") or env_review_payload.get("window") or {"start": "", "end": ""},
        "counts": {
            "create": 0,
            "comment": 0,
            "reopen_and_comment": 0,
            "unknown": 0,
            "env_filtered": 0,
        },
        "create": [],
        "comment": [],
        "reopen_and_comment": [],
        "unknown": [],
        "env_filtered": [],
    }

    for item in env_review_payload.get("items", []):
        decision = env_index[item["candidate_id"]]
        if decision["decision"] == "env_filtered":
            payload["env_filtered"].append(
                {
                    "source": item["source"],
                    "test_name": item["target"].get("test_name"),
                    "package": item["target"].get("package_name"),
                    "ci_name": item["ci_name"],
                    "ci_url": item["ci_url"],
                    "log_ref": item["log_ref"],
                    "failure_family": item.get("failure_family"),
                    "excerpt_lines": item.get("excerpt_lines", []),
                    "excerpt_start_line": item.get("excerpt_start_line"),
                    "excerpt_end_line": item.get("excerpt_end_line"),
                    "excerpt_confidence": item.get("excerpt_confidence"),
                    "excerpt_reason": item.get("excerpt_reason", ""),
                    "environment_reason": decision.get("reason", ""),
                }
            )
            continue
        if decision["decision"] != "keep":
            raise ValueError(f"unsupported env review decision: {decision['decision']}")

    for candidate_id, candidate in candidate_map.items():
        decision = action_index[candidate_id]
        final_action = decision["final_action"]
        target = _candidate_target(decision, candidate)
        if final_action == "drop":
            continue
        if final_action == "create":
            payload["create"].append(
                {
                    "key": candidate.get("group_key", candidate["candidate_id"]),
                    "source": candidate["source"],
                    "test_name": target.get("test_name"),
                    "package": target.get("package_name"),
                    "title": LEGACY.build_issue_title(
                        test_name=target.get("test_name"),
                        package_name=target.get("package_name"),
                        signatures=candidate["signatures"],
                    ),
                    "labels": candidate.get("issue_labels", ["type/ci"]),
                    "links": candidate["links"],
                    "ci_names": candidate["ci_names"],
                    "signatures": candidate["signatures"],
                    "excerpt_candidates": _excerpt_candidates(candidate),
                    "debug_only_evidence_summary": candidate["debug_only_evidence_summary"],
                    "review_reason": decision.get("reason", ""),
                }
            )
            continue
        if final_action in {"comment", "reopen_and_comment"}:
            issue = _selected_issue(decision, candidate)
            if not issue or issue.get("number") is None:
                raise ValueError(f"missing target issue for action {candidate_id}")
            payload[final_action].append(
                {
                    "key": candidate.get("group_key", candidate["candidate_id"]),
                    "source": candidate["source"],
                    "test_name": target.get("test_name"),
                    "package": target.get("package_name"),
                    "issue_number": issue["number"],
                    "issue_url": issue.get("url"),
                    "new_links": candidate["links"],
                    "ci_names": candidate["ci_names"],
                    "signatures": candidate["signatures"],
                    "excerpt_candidates": _excerpt_candidates(candidate),
                    "debug_only_evidence_summary": candidate["debug_only_evidence_summary"],
                    "review_reason": decision.get("reason", ""),
                }
            )
            continue
        if final_action == "unknown":
            payload["unknown"].append(
                {
                    "key": candidate.get("group_key", candidate["candidate_id"]),
                    "source": candidate["source"],
                    "test_name": target.get("test_name"),
                    "package": target.get("package_name"),
                    "links": candidate["links"],
                    "ci_names": candidate["ci_names"],
                    "signatures": candidate["signatures"],
                    "excerpt_candidates": _excerpt_candidates(candidate),
                    "debug_only_evidence_summary": candidate["debug_only_evidence_summary"],
                    "decision_reason": decision.get("reason", ""),
                    "existing_issue_number": ((candidate.get("issue_matches", {}).get("selected_match") or {}).get("number")),
                    "existing_issue_url": ((candidate.get("issue_matches", {}).get("selected_match") or {}).get("url")),
                }
            )
            continue
        raise ValueError(f"unsupported final action: {final_action}")

    for key in payload["counts"]:
        payload["counts"][key] = len(payload[key])
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--action-review-candidates", required=True)
    parser.add_argument("--action-review-decisions", required=True)
    parser.add_argument("--env-review-payload", required=True)
    parser.add_argument("--env-review-decisions", required=True)
    parser.add_argument("--out-json", default="/tmp/final_triage.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = assemble_final_triage_payload(
        action_review_candidates=read_json(args.action_review_candidates),
        action_review_decisions=read_json(args.action_review_decisions),
        env_review_payload=read_json(args.env_review_payload),
        env_review_decisions=read_json(args.env_review_decisions),
    )
    write_json(args.out_json, payload)
    print(
        "wrote final triage to "
        f"{args.out_json} (create={payload['counts']['create']} "
        f"comment={payload['counts']['comment']} reopen={payload['counts']['reopen_and_comment']} "
        f"unknown={payload['counts']['unknown']} env_filtered={payload['counts']['env_filtered']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
