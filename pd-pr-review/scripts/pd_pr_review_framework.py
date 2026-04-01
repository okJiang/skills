#!/usr/bin/env python3
"""Shared helpers for the local PD PR review skill."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


BLOCKING_THRESHOLD = 0.90
NON_BLOCKING_THRESHOLD = 0.80
DEFAULT_COMMAND_BUDGET = 2
ROOT_CAUSE_MARKER = re.compile(
    r"\b(bug|fix|fixes|fixed|fixing|flaky|regression|panic|race|crash|failure|error|incorrect|stale|timeout|deadlock)\b"
)

BASE_LANES = [
    "metadata",
    "tests",
]

PASSING_STATES = {"success", "completed", "neutral"}
FAILING_STATES = {"failure", "error", "cancelled", "timed_out", "action_required"}
PENDING_STATES = {"pending", "queued", "in_progress", "requested"}


def parse_pr_body_sections(body: str) -> Dict[str, Any]:
    sections: Dict[str, List[str]] = {}
    current_heading: Optional[str] = None

    for raw_line in (body or "").splitlines():
        line = raw_line.rstrip()
        heading_match = re.match(r"^###\s+(.*)$", line)
        if heading_match:
            current_heading = heading_match.group(1).strip().lower()
            sections.setdefault(current_heading, [])
            continue
        if current_heading is not None:
            sections[current_heading].append(line)

    cleaned_sections = {
        name: _strip_html_comments(lines)
        for name, lines in sections.items()
    }

    checklist = _parse_checklist_sections(cleaned_sections.get("check list", []))
    release_note = _extract_fenced_block(cleaned_sections.get("release note", []))

    problem_lines = [
        line for line in cleaned_sections.get("what problem does this pr solve?", []) if line.strip()
    ]
    issue_number = ""
    for line in problem_lines:
        if line.lower().startswith("issue number:"):
            issue_number = line.split(":", 1)[1].strip()
            break
    problem_statement = "\n".join(
        line for line in problem_lines if not line.lower().startswith("issue number:")
    ).strip()

    changed_lines = [
        line
        for line in cleaned_sections.get("what is changed and how does it work?", [])
        if line.strip() and not line.startswith("```")
    ]

    return {
        "issue_number": issue_number,
        "problem_statement": problem_statement,
        "change_summary": "\n".join(changed_lines).strip(),
        "tests": checklist.get("tests", []),
        "code_changes": checklist.get("code changes", []),
        "side_effects": checklist.get("side effects", []),
        "related_changes": checklist.get("related changes", []),
        "release_note": release_note,
    }


def _parse_checklist_sections(lines: Iterable[str]) -> Dict[str, List[str]]:
    sections: Dict[str, List[str]] = {}
    current_section: Optional[str] = None

    for raw_line in lines:
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("<!--"):
            continue
        if stripped.startswith("- "):
            if current_section is None:
                continue
            sections.setdefault(current_section, []).append(stripped[2:].strip())
            continue
        current_section = stripped.lower()
        sections.setdefault(current_section, [])

    return sections


def _strip_html_comments(lines: Iterable[str]) -> List[str]:
    cleaned: List[str] = []
    in_comment = False
    for raw_line in lines:
        line = raw_line
        stripped = line.strip()
        if stripped.startswith("<!--") and stripped.endswith("-->"):
            continue
        if stripped.startswith("<!--"):
            in_comment = True
            continue
        if in_comment and stripped.endswith("-->"):
            in_comment = False
            continue
        if in_comment:
            continue
        cleaned.append(line)
    return cleaned


def _extract_fenced_block(lines: Iterable[str]) -> str:
    in_block = False
    payload: List[str] = []
    for raw_line in lines:
        line = raw_line.rstrip("\n")
        stripped = line.strip()
        if stripped.startswith("```") and not in_block:
            in_block = True
            continue
        if stripped.startswith("```") and in_block:
            break
        if in_block:
            payload.append(line)
    return "\n".join(payload).strip()


def normalize_pr_context(
    pr_number: int,
    pr_payload: Dict[str, Any],
    issue_payload: Optional[Dict[str, Any]],
    diff_text: str,
    codeowners_text: str,
    checks_payload: List[Dict[str, Any]],
) -> Dict[str, Any]:
    changed_files = _extract_changed_files(pr_payload.get("files", []))
    parsed_body = parse_pr_body_sections(pr_payload.get("body", ""))
    diff_hunks = parse_diff_hunks(diff_text)

    return {
        "pr_number": pr_number,
        "title": pr_payload.get("title", ""),
        "base_sha": pr_payload.get("baseRefOid") or pr_payload.get("baseRefName") or "",
        "head_sha": pr_payload.get("headRefOid") or pr_payload.get("headRefName") or "",
        "pr_body_sections": parsed_body,
        "issue_summary": {
            "title": (issue_payload or {}).get("title", ""),
            "body": (issue_payload or {}).get("body", ""),
        },
        "changed_files": changed_files,
        "diff_hunks": diff_hunks,
        "codeowners_hits": match_codeowners(changed_files, codeowners_text),
        "ci_status": summarize_ci_status(checks_payload),
        "risk_tags": [],
    }


def _extract_changed_files(files_payload: Iterable[Any]) -> List[str]:
    changed: List[str] = []
    for item in files_payload:
        if isinstance(item, str):
            changed.append(item)
            continue
        if isinstance(item, dict):
            path = item.get("path") or item.get("name")
            if path:
                changed.append(path)
    return changed


def parse_diff_hunks(diff_text: str) -> Dict[str, List[int]]:
    diff_hunks: Dict[str, List[int]] = {}
    current_file: Optional[str] = None
    current_line: Optional[int] = None

    for raw_line in (diff_text or "").splitlines():
        if raw_line.startswith("+++ b/"):
            current_file = raw_line[6:]
            diff_hunks.setdefault(current_file, [])
            current_line = None
            continue
        if raw_line.startswith("@@"):
            match = re.search(r"\+(\d+)", raw_line)
            current_line = int(match.group(1)) if match else None
            continue
        if current_file is None or current_line is None:
            continue
        if raw_line.startswith("+") and not raw_line.startswith("+++"):
            diff_hunks[current_file].append(current_line)
            current_line += 1
            continue
        if raw_line.startswith("-") and not raw_line.startswith("---"):
            continue
        current_line += 1

    return diff_hunks


def match_codeowners(changed_files: Iterable[str], codeowners_text: str) -> List[Dict[str, Any]]:
    rules: List[Dict[str, Any]] = []
    for raw_line in (codeowners_text or "").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        rules.append({"pattern": parts[0], "owners": parts[1:]})

    hits: List[Dict[str, Any]] = []
    for path in sorted(changed_files):
        for rule in rules:
            if _matches_codeowners_pattern(path, rule["pattern"]):
                hits.append(
                    {
                        "pattern": rule["pattern"],
                        "owners": rule["owners"],
                        "path": path,
                    }
                )
    return hits


def _matches_codeowners_pattern(path: str, pattern: str) -> bool:
    clean_pattern = pattern.lstrip("/")
    if pattern.endswith("/"):
        return path.startswith(clean_pattern)
    return path == clean_pattern


def summarize_ci_status(checks_payload: Iterable[Dict[str, Any]]) -> Dict[str, List[str]]:
    status = {"passing": [], "failing": [], "pending": []}
    for check in checks_payload:
        name = check.get("name") or check.get("workflow") or "unknown"
        conclusion = str(check.get("conclusion") or "").lower()
        state = str(check.get("state") or check.get("status") or "").lower()
        if conclusion in FAILING_STATES or state in FAILING_STATES:
            status["failing"].append(name)
            continue
        if conclusion in PENDING_STATES or state in PENDING_STATES:
            status["pending"].append(name)
            continue
        if conclusion in PASSING_STATES or state in PASSING_STATES:
            status["passing"].append(name)
    return status


def build_risk_map(context: Dict[str, Any]) -> Dict[str, Any]:
    changed_files = context.get("changed_files", [])
    body_sections = context.get("pr_body_sections", {})
    risk_tags: List[str] = []
    selected_lanes = list(BASE_LANES)
    lane_check_candidates: List[tuple[str, str]] = []
    command_budget = DEFAULT_COMMAND_BUDGET

    if _has_root_cause_signal(context):
        selected_lanes.append("root-cause")

    if _has_agent_artifact_signal(changed_files):
        risk_tags.append("agent-artifact")
        selected_lanes.append("agent-artifacts")

    if changed_files and all(_is_docs_only(path) for path in changed_files) and not risk_tags:
        risk_tags.append("docs-only")
        return {
            "risk_tags": risk_tags,
            "selected_lanes": ["metadata"],
            "suggested_checks": [],
            "lane_suggested_checks": {},
            "command_budget": command_budget,
        }

    if any(path.startswith("pkg/schedule/") for path in changed_files):
        risk_tags.append("schedule-hotpath")
        selected_lanes.append("schedule-hotpath")
        lane_check_candidates.append(("schedule-hotpath", "go test ./pkg/schedule/..."))

    if _has_invariant_or_boundary_signal(changed_files):
        risk_tags.append("invariants-and-boundaries")
        selected_lanes.append("invariants-and-boundaries")

    if _has_config_or_compat_signal(changed_files, body_sections):
        risk_tags.append("config-change")
        selected_lanes.append("config-and-compat")
        if not lane_check_candidates:
            lane_check_candidates.append(("config-and-compat", "go test ./server/..."))

    if _has_tso_or_mcs_signal(changed_files):
        risk_tags.append("tso-or-mcs")
        selected_lanes.append("tso-and-mcs")
        lane_check_candidates.append(("tso-and-mcs", "make test-tso-function"))

    if _has_observability_signal(changed_files):
        risk_tags.append("observability-and-docs")
        selected_lanes.append("observability-and-docs")

    if _has_abstraction_or_naming_signal(changed_files, context.get("title", ""), body_sections):
        risk_tags.append("abstractions-and-naming")
        selected_lanes.append("abstractions-and-naming")

    if context.get("ci_status", {}).get("failing"):
        risk_tags.append("ci-red")

    # Preserve ordering while enforcing the command budget.
    deduped_lanes: List[str] = []
    for lane in selected_lanes:
        if lane not in deduped_lanes:
            deduped_lanes.append(lane)

    deduped_checks: List[str] = []
    lane_suggested_checks: Dict[str, List[str]] = {}
    for lane, command in lane_check_candidates:
        if command in deduped_checks or len(deduped_checks) >= command_budget:
            continue
        deduped_checks.append(command)
        lane_suggested_checks.setdefault(lane, []).append(command)

    return {
        "risk_tags": risk_tags,
        "selected_lanes": deduped_lanes,
        "suggested_checks": deduped_checks[:command_budget],
        "lane_suggested_checks": lane_suggested_checks,
        "command_budget": command_budget,
    }


def _is_docs_only(path: str) -> bool:
    return path.endswith(".md") or path.startswith("docs/")


def _has_config_or_compat_signal(changed_files: Iterable[str], body_sections: Dict[str, Any]) -> bool:
    code_changes = body_sections.get("code_changes", [])
    side_effects = body_sections.get("side_effects", [])
    signal_strings = "\n".join(code_changes + side_effects).lower()
    if "configuration change" in signal_strings:
        return True
    if "http api interfaces changed" in signal_strings:
        return True
    if "persistent data change" in signal_strings:
        return True
    if "breaking backward compatibility" in signal_strings:
        return True
    for path in changed_files:
        if path.endswith("config.go") or "/config/" in path or path.startswith("conf/"):
            return True
    return False


def _has_tso_or_mcs_signal(changed_files: Iterable[str]) -> bool:
    client_keywords = ("tso", "timestamp", "allocator", "keyspace", "mcs")
    for path in changed_files:
        lowered = path.lower()
        if path.startswith("pkg/mcs/") or path.startswith("tests/server/tso/"):
            return True
        if "/tso/" in path or "/mcs/" in path:
            return True
        if path.startswith("client/") and any(keyword in lowered for keyword in client_keywords):
            return True
    return False


def _has_agent_artifact_signal(changed_files: Iterable[str]) -> bool:
    for path in changed_files:
        if path == "AGENTS.md" or path.startswith(".agents/") or "/.agents/" in path:
            return True
    return False


def _has_invariant_or_boundary_signal(changed_files: Iterable[str]) -> bool:
    keywords = (
        "retry",
        "discovery",
        "watcher",
        "guard",
        "operator_controller",
        "inner_client",
        "callback",
        "hook",
    )
    for path in changed_files:
        lowered = path.lower()
        if any(keyword in lowered for keyword in keywords):
            return True
        if path.startswith("client/") and any(
            keyword in lowered for keyword in ("retry", "discovery", "guard", "callback", "hook")
        ):
            return True
    return False


def _has_root_cause_signal(context: Dict[str, Any]) -> bool:
    issue = context.get("issue_summary", {})
    body_sections = context.get("pr_body_sections", {})
    signal_text = "\n".join(
        [
            str(context.get("title", "")),
            str(body_sections.get("problem_statement", "")),
            str(body_sections.get("change_summary", "")),
            str(issue.get("title", "")),
            str(issue.get("body", "")),
        ]
    ).lower()
    return bool(ROOT_CAUSE_MARKER.search(signal_text))


def _has_observability_signal(changed_files: Iterable[str]) -> bool:
    keywords = ("metric", "metrics", "log", "logger", "trace", "swagger", "openapi", "annotation")
    for path in changed_files:
        lowered = path.lower()
        if any(keyword in lowered for keyword in keywords):
            return True
    return False


def _has_abstraction_or_naming_signal(
    changed_files: Iterable[str],
    title: str,
    body_sections: Dict[str, Any],
) -> bool:
    title_lower = title.lower()
    if any(keyword in title_lower for keyword in ("refactor", "rename", "reorganize", "cleanup")):
        return True
    keywords = ("middleware", "watcher", "redirector", "interface.go", "option.go")
    change_signal = "\n".join(body_sections.get("code_changes", []) + body_sections.get("side_effects", [])).lower()
    has_explicit_abstraction_file = False
    has_api_surface = False
    has_controller_or_owner_boundary = False
    has_client_controller = False
    for path in changed_files:
        lowered = path.lower()
        if any(keyword in lowered for keyword in keywords):
            has_explicit_abstraction_file = True
        if "/api/" in lowered or "/apis/" in lowered or lowered.endswith("api.go"):
            has_api_surface = True
        if "controller" in lowered or lowered.endswith("manager.go") or "policy" in lowered:
            has_controller_or_owner_boundary = True
        if lowered.startswith("client/") and "controller" in lowered:
            has_client_controller = True
    if has_explicit_abstraction_file:
        return True

    if _has_config_or_compat_signal(changed_files, body_sections):
        if has_controller_or_owner_boundary and (has_api_surface or has_client_controller):
            return True
        if has_controller_or_owner_boundary and any(
            keyword in f"{title_lower}\n{change_signal}"
            for keyword in ("controllerconfig", "controller config", "override", "inherit")
        ):
            return True
    return False


def arbitrate_skill_results(
    context: Dict[str, Any],
    lane_results: Iterable[Dict[str, Any]],
) -> Dict[str, Any]:
    deduped_postable_comments: Dict[tuple[Any, ...], Dict[str, Any]] = {}
    local_only_findings: List[Dict[str, Any]] = []

    for result in lane_results:
        result_confidence = float(result.get("confidence", 0.0))
        lane_name = result.get("lane") or result.get("skill")
        for finding in result.get("findings", []):
            severity = finding.get("severity", "")
            reason = _local_only_reason(finding, result_confidence)
            if reason is not None:
                local_only_findings.append(
                    {
                        "reason": reason,
                        "lane": lane_name,
                        "title": finding.get("title"),
                        "severity": severity,
                    }
                )
                continue

            delivery = "summary"
            path = finding.get("path")
            line = finding.get("line")
            if isinstance(line, int) and path in context.get("diff_hunks", {}):
                if line in context["diff_hunks"][path]:
                    delivery = "inline"

            dedupe_key = (
                path,
                line,
                finding.get("title"),
            )
            candidate_comment = {
                "lane": lane_name,
                "severity": severity,
                "delivery": delivery,
                "path": path,
                "line": line,
                "title": finding.get("title"),
                "body": finding.get("body"),
                "evidence": finding.get("evidence", []),
                "suggested_check": finding.get("suggested_check", ""),
            }
            existing = deduped_postable_comments.get(dedupe_key)
            if existing is None:
                deduped_postable_comments[dedupe_key] = candidate_comment
                continue
            deduped_postable_comments[dedupe_key] = _merge_duplicate_comment(
                existing,
                candidate_comment,
            )

    return {
        "postable_comments": list(deduped_postable_comments.values()),
        "local_only_findings": local_only_findings,
    }


def _merge_duplicate_comment(existing: Dict[str, Any], candidate: Dict[str, Any]) -> Dict[str, Any]:
    existing_rank = _severity_rank(existing.get("severity", "question"))
    candidate_rank = _severity_rank(candidate.get("severity", "question"))
    preferred = existing if existing_rank >= candidate_rank else candidate
    other = candidate if preferred is existing else existing

    merged = dict(preferred)
    merged["evidence"] = _merge_unique_strings(existing.get("evidence", []), candidate.get("evidence", []))
    if not merged.get("suggested_check"):
        merged["suggested_check"] = other.get("suggested_check", "")
    if merged.get("delivery") != "inline" and other.get("delivery") == "inline":
        merged["delivery"] = "inline"
    return merged


def _severity_rank(severity: str) -> int:
    if severity == "blocking":
        return 3
    if severity == "non_blocking":
        return 2
    return 1


def _merge_unique_strings(left: Iterable[str], right: Iterable[str]) -> List[str]:
    merged: List[str] = []
    for item in list(left) + list(right):
        if item not in merged:
            merged.append(item)
    return merged


def _local_only_reason(finding: Dict[str, Any], result_confidence: float) -> Optional[str]:
    severity = finding.get("severity")
    evidence = finding.get("evidence", [])
    if severity == "question":
        if not evidence:
            return "insufficient-evidence"
        return None
    if severity == "blocking":
        if result_confidence < BLOCKING_THRESHOLD:
            return "below-threshold"
        if len(evidence) < 2:
            return "insufficient-evidence"
    if severity == "non_blocking":
        if result_confidence < NON_BLOCKING_THRESHOLD:
            return "below-threshold"
        if not evidence:
            return "insufficient-evidence"
    return None


def categorize_shadow_pr(pr_payload: Dict[str, Any]) -> str:
    files = _extract_changed_files(pr_payload.get("files", []))
    title = str(pr_payload.get("title", "")).lower()

    if any(path.startswith("pkg/mcs/") for path in files):
        return "tso-mcs"
    if any(path.startswith("pkg/schedule/") or _is_general_config_path(path) for path in files):
        return "schedule-config"
    if any(path.startswith("tests/") for path in files) or "flaky" in title or "test" in title:
        return "tests-ci"
    return "refactor-no-code"


def _is_general_config_path(path: str) -> bool:
    if path.startswith("pkg/mcs/"):
        return False
    return "config" in path


def run_command(command: List[str], cwd: Path) -> Dict[str, Any]:
    process = subprocess.run(command, cwd=cwd, text=True, capture_output=True)
    return {
        "cmd": " ".join(command),
        "exit_code": process.returncode,
        "stdout": process.stdout,
        "stderr": process.stderr,
    }


def load_json_file(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
