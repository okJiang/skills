#!/usr/bin/env python3
"""Triages recent PD CI failures and manages flaky-test issues."""

from __future__ import annotations

import argparse
import concurrent.futures
import dataclasses
import datetime as dt
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
from pathlib import Path
from typing import Any

UTC = dt.timezone.utc
PROGRESS_ENV = "PD_CI_FLAKY_PROGRESS"


@dataclasses.dataclass
class FailureRecord:
    record_id: str
    source: str
    ci_name: str
    ci_url: str
    log_url: str | None
    occurred_at: str
    pr_number: int | None
    commit_sha: str | None
    run_id: str | None
    job_id: int | None
    status: str


@dataclasses.dataclass
class ParsedFailure:
    record_id: str
    key: str
    test_name: str | None
    signatures: list[str]
    evidence_lines: list[str]
    anchor_signatures: list[str] = dataclasses.field(default_factory=list)
    anchor_offsets: list[int] = dataclasses.field(default_factory=list)
    log_fetch_mode: str = "full"
    raw_log_ref: str = ""
    tests: list[str] = dataclasses.field(default_factory=list)
    primary_test: str | None = None
    failure_type: str = "unknown"
    stack_blocks: list[str] = dataclasses.field(default_factory=list)
    evidence_summary: str = ""
    confidence: float = 0.0
    needs_inbox_fallback: bool = False
    stack_tokens: list[str] = dataclasses.field(default_factory=list)
    primary_package: str | None = None
    failed_packages: list[str] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class CoarseFailureRecord:
    record_id: str
    source: str
    ci_name: str
    ci_url: str
    log_url: str | None
    occurred_at: str
    pr_number: int | None
    commit_sha: str | None
    anchor_signatures: list[str]
    anchor_offsets: list[int]
    log_fetch_mode: str
    raw_log_ref: str


@dataclasses.dataclass
class AgentAnalysisRecord:
    record_id: str
    tests: list[str]
    primary_test: str | None
    failure_type: str
    stack_blocks: list[str]
    evidence_summary: str
    confidence: float
    needs_inbox_fallback: bool
    stack_tokens: list[str]
    primary_package: str | None


@dataclasses.dataclass
class FlakyDecision:
    key: str
    test_name: str | None
    is_flaky: bool
    reason: str
    distinct_pr_count: int
    distinct_sha_count: int
    has_existing_issue: bool
    existing_issue_number: int | None
    confidence: float = 0.0
    needs_inbox_fallback: bool = False
    action: str = "skip"
    action_reason: str = ""
    dedup_key: str = ""


@dataclasses.dataclass
class IssueResolution:
    key: str
    action: str
    issue_number: int | None
    issue_url: str | None
    details: str


@dataclasses.dataclass
class RunSummary:
    scanned_window_start: str
    scanned_window_end: str
    prow_records: int = 0
    actions_records: int = 0
    parsed_failures: int = 0
    flaky_true: int = 0
    issue_actions: int = 0
    log_spool_dir: str = ""
    skipped_unknown: list[str] = dataclasses.field(default_factory=list)
    command_failed_after_retries: list[str] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class DownloadedLog:
    record: FailureRecord
    path: Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Triages recent PD CI failures and flaky issues")
    parser.add_argument("--repo", default="tikv/pd")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--scope", choices=["pr+push", "pr", "push"], default="pr+push")
    parser.add_argument("--ci-scope", choices=["test-all"], default="test-all")
    parser.add_argument("--mode", choices=["auto", "dry-run"], default="auto")
    parser.add_argument("--flaky-policy", choices=["evidence-first"], default="evidence-first")
    parser.add_argument("--reopen-closed", type=parse_bool, default=True)
    parser.add_argument("--out-json", default="")
    parser.add_argument("--max-prow-pages", type=int, default=30)
    parser.add_argument("--max-action-runs", type=int, default=500)
    parser.add_argument("--retry-count", type=int, default=3)
    parser.add_argument("--pipeline-mode", choices=["parallel", "serial"], default="parallel")
    parser.add_argument("--download-workers", type=int, default=8)
    parser.add_argument("--parse-workers", type=int, default=0)
    parser.add_argument("--log-spool-dir", default="")
    parser.add_argument("--keep-logs", type=parse_bool, default=False)
    parser.add_argument("--analysis-mode", choices=["coarse-only", "agent-full"], default="agent-full")
    parser.add_argument("--agent-max-log-bytes", type=int, default=8 * 1024 * 1024)
    parser.add_argument("--agent-confidence-threshold", type=float, default=0.65)
    parser.add_argument("--inbox-issue-title", default="[CI triage inbox] unresolved flaky candidates")
    parser.add_argument("--inbox-issue-labels", default="type/ci")
    return parser.parse_args()


def parse_bool(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value
    lowered = value.strip().lower()
    if lowered in {"1", "true", "t", "yes", "y", "on"}:
        return True
    if lowered in {"0", "false", "f", "no", "n", "off"}:
        return False
    raise argparse.ArgumentTypeError(f"invalid boolean value: {value}")


def now_utc() -> dt.datetime:
    return dt.datetime.now(tz=UTC)


def progress_enabled() -> bool:
    value = os.getenv(PROGRESS_ENV, "1").strip().lower()
    return value not in {"0", "false", "off", "no"}


def log_progress(message: str) -> None:
    if not progress_enabled():
        return
    ts = now_utc().isoformat(timespec="seconds")
    print(f"[progress] {ts} {message}", file=sys.stderr, flush=True)


def parse_iso8601(ts: str | None) -> dt.datetime:
    if not ts:
        return dt.datetime.fromtimestamp(0, tz=UTC)
    ts = ts.strip()
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    return dt.datetime.fromisoformat(ts).astimezone(UTC)


def run_cmd(
    cmd: list[str],
    summary: RunSummary,
    retries: int,
    timeout: int = 600,
) -> tuple[bool, str, str]:
    last_stdout = ""
    last_stderr = ""
    for attempt in range(1, retries + 1):
        try:
            proc = subprocess.run(
                cmd,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except Exception as exc:  # noqa: BLE001
            last_stderr = str(exc)
            proc = None
        else:
            last_stdout = proc.stdout or ""
            last_stderr = proc.stderr or ""
            if proc.returncode == 0:
                return True, last_stdout, last_stderr
            last_stderr = f"exit={proc.returncode}; {last_stderr.strip()}"

        if attempt < retries:
            time.sleep(2 ** (attempt - 1))

    snippet = " ".join(cmd[:4])
    summary.command_failed_after_retries.append(f"{snippet}: {last_stderr[:240]}")
    return False, last_stdout, last_stderr


def run_gh_json(args: list[str], summary: RunSummary, retries: int) -> Any | None:
    ok, out, _ = run_cmd(["gh", *args], summary=summary, retries=retries)
    if not ok:
        return None
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        summary.skipped_unknown.append(f"json_decode_failed: gh {' '.join(args[:4])}")
        return None


def run_curl_text(url: str, summary: RunSummary, retries: int) -> str | None:
    ok, out, _ = run_cmd(["curl", "-L", "-s", url], summary=summary, retries=retries)
    if not ok:
        return None
    return out


def extract_json_array_after(text: str, marker: str) -> str | None:
    idx = text.find(marker)
    if idx < 0:
        return None
    start = text.find("[", idx)
    if start < 0:
        return None

    in_string = False
    escaped = False
    depth = 0
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
            continue
        if ch == "[":
            depth += 1
            continue
        if ch == "]":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def extract_older_runs_url(page_html: str) -> str | None:
    match = re.search(r'href="([^"]+buildId=[^"]+)"[^>]*>&lt;- Older Runs', page_html)
    if not match:
        return None
    return urllib.parse.urljoin("https://prow.tidb.net", match.group(1))


def spyglass_to_build_log_url(spyglass_link: str) -> str | None:
    if not spyglass_link:
        return None
    if "#" in spyglass_link:
        spyglass_link = spyglass_link.split("#", 1)[0]
    prefix = "/view/gs/"
    if prefix not in spyglass_link:
        return None
    rel = spyglass_link.split(prefix, 1)[1].strip("/")
    if not rel:
        return None
    return f"https://storage.googleapis.com/{rel}/build-log.txt"


def normalize_test_key(test_name: str | None, signatures: list[str]) -> str:
    if test_name:
        cleaned = test_name.strip().strip("`")
        return re.sub(r"\s+", "", cleaned).lower()
    if signatures:
        return f"signature::{signatures[0].lower()}"
    return "signature::unknown"


def normalize_package_key(package_name: str) -> str:
    cleaned = package_name.strip().strip("`")
    if not cleaned:
        return "package::unknown"
    return f"package::{re.sub(r'[^a-z0-9]+', '', cleaned.lower())}"


def collapse_parameterized_subtest(test_name: str) -> str:
    if "/" not in test_name:
        return test_name
    root, suffix = test_name.split("/", 1)
    if re.search(r"[=,]", suffix):
        return root
    return test_name


def normalize_extracted_tests(tests: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for test_name in tests:
        normalized = collapse_parameterized_subtest(test_name)
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)

    roots_with_subtests = {name.split("/", 1)[0] for name in deduped if "/" in name}
    return [name for name in deduped if not ("/" not in name and name in roots_with_subtests)]


FAIL_PACKAGE_PATTERN = re.compile(r"^\s*FAIL\s+([^\s]+)\s+\d+(?:\.\d+)?s(?:\s|$)")


def parse_failed_packages(log_text: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for line in log_text.splitlines():
        match = FAIL_PACKAGE_PATTERN.search(line)
        if not match:
            continue
        package_name = match.group(1).strip()
        if not package_name or package_name in seen:
            continue
        seen.add(package_name)
        found.append(package_name)
    return found


def build_refs_match_repo(build: dict[str, Any], target_repo: str) -> bool:
    if "/" not in target_repo:
        return True
    target_org, target_name = target_repo.split("/", 1)
    target_org = target_org.lower().strip()
    target_name = target_name.lower().strip()

    refs = build.get("Refs", {}) or {}
    org = str(refs.get("org") or "").lower().strip()
    repo = str(refs.get("repo") or "").lower().strip()
    if org and repo:
        return org == target_org and repo == target_name

    pulls = refs.get("pulls", []) or []
    for pull in pulls:
        pull_org = str(pull.get("org") or pull.get("author") or "").lower().strip()
        pull_repo = str(pull.get("repo") or "").lower().strip()
        if pull_org and pull_repo:
            if pull_org == target_org and pull_repo == target_name:
                return True

    spyglass_link = str(build.get("SpyglassLink") or "").lower()
    return f"/pull/{target_org}_{target_name}/" in spyglass_link


def looks_test_related(name: str) -> bool:
    lowered = name.lower()
    return bool(
        re.search(r"(test|tests|unit|integration|tso|goleak|pull-unit-test|pd test|chunks)", lowered)
    )


SIGNATURE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("DATA_RACE", re.compile(r"WARNING:\s+DATA RACE", re.IGNORECASE)),
    ("POTENTIAL_DEADLOCK", re.compile(r"POTENTIAL DEADLOCK", re.IGNORECASE)),
    ("TIMEOUT_PANIC", re.compile(r"panic:\s+test timed out", re.IGNORECASE)),
    ("CONDITION_NEVER_SATISFIED", re.compile(r"Condition never satisfied", re.IGNORECASE)),
    ("PANIC", re.compile(r"panic:", re.IGNORECASE)),
]
GOLEAK_PATTERN = re.compile(r"\bgoleak\b", re.IGNORECASE)
GOLEAK_EXCLUDE_PATTERN = re.compile(r"^\s*go:\s+downloading\s+.*goleak", re.IGNORECASE)
GOLEAK_SIGNAL_PATTERNS = [
    re.compile(r"found unexpected goroutines", re.IGNORECASE),
    re.compile(r"goleak:\s+errors on successful test run", re.IGNORECASE),
]
COMMON_STOP_PATTERNS = [
    re.compile(r"^\s*run all tasks takes", re.IGNORECASE),
    re.compile(r"^\s*make:\s+\*\*\*"),
    re.compile(r"^\s*##\[error\]"),
    re.compile(r"^\s*FAIL\s*$"),
    re.compile(r"^\s*PASS\s*$"),
]


def parse_signatures(log_text: str) -> list[str]:
    found: list[str] = []
    lines = log_text.splitlines()

    for name, pattern in SIGNATURE_PATTERNS:
        if any(pattern.search(line) for line in lines):
            found.append(name)

    has_real_goleak = False
    for line in lines:
        if GOLEAK_EXCLUDE_PATTERN.search(line):
            continue
        if any(pattern.search(line) for pattern in GOLEAK_SIGNAL_PATTERNS):
            has_real_goleak = True
            break
    if has_real_goleak:
        found.append("GOLEAK")

    if not found:
        found.append("UNKNOWN_FAILURE")
    return found


def _push_test_name(found: list[str], seen: set[str], name: str | None) -> None:
    if not name:
        return
    cleaned = name.strip().strip("`").rstrip(":,.")
    if not cleaned:
        return
    if cleaned == "TestMain":
        return
    if cleaned in seen:
        return
    seen.add(cleaned)
    found.append(cleaned)


def parse_test_names(log_text: str) -> list[str]:
    patterns = [
        re.compile(r"--- FAIL:\s+([^\s(]+)"),
        re.compile(r"=== NAME\s+([^\s]+)"),
        re.compile(r"\bTest:\s+([^\s]+)"),
        re.compile(r"running tests:\s*$", re.IGNORECASE),
    ]
    running_test_pattern = re.compile(r"^\s*(Test[A-Za-z0-9_]+(?:/[A-Za-z0-9_.-]+)?)(?:\s|\(|$)")
    stack_test_pattern = re.compile(r"\b[\w_]+\.(Test[A-Za-z0-9_]+(?:/[A-Za-z0-9_.-]+)?)\b")
    explicit_found: list[str] = []
    explicit_seen: set[str] = set()
    stack_found: list[str] = []
    stack_seen: set[str] = set()
    lines = log_text.splitlines()
    for i, line in enumerate(lines):
        for pattern in patterns[:3]:
            match = pattern.search(line)
            if match:
                _push_test_name(explicit_found, explicit_seen, match.group(1))

        if patterns[3].search(line):
            for j in range(i + 1, min(i + 8, len(lines))):
                run_match = running_test_pattern.search(lines[j])
                if run_match:
                    _push_test_name(explicit_found, explicit_seen, run_match.group(1))

        stack_match = stack_test_pattern.search(line)
        if stack_match:
            _push_test_name(stack_found, stack_seen, stack_match.group(1))

    if explicit_found:
        return normalize_extracted_tests(explicit_found)
    return normalize_extracted_tests(stack_found)


def extract_anchor_offsets(log_text: str) -> list[int]:
    offsets: list[int] = []
    anchor = re.compile(
        r"--- FAIL:|=== NAME|\bTest:|panic:|DATA RACE|POTENTIAL DEADLOCK|Condition never satisfied|goleak",
        re.IGNORECASE,
    )
    for idx, line in enumerate(log_text.splitlines(), start=1):
        if GOLEAK_EXCLUDE_PATTERN.search(line):
            continue
        if anchor.search(line):
            offsets.append(idx)
    return offsets


def _slice_block(
    lines: list[str],
    start: int,
    max_lines: int,
    stop_patterns: list[re.Pattern[str]] | None = None,
) -> str:
    stop_patterns = stop_patterns or COMMON_STOP_PATTERNS
    end = min(len(lines), start + max_lines)
    for i in range(start + 1, end):
        if i - start < 6:
            continue
        if any(pattern.search(lines[i]) for pattern in stop_patterns):
            return "\n".join(lines[start:i]).strip()
    return "\n".join(lines[start:end]).strip()


def extract_stack_blocks(log_text: str, signatures: list[str]) -> list[str]:
    lines = log_text.splitlines()
    blocks: list[str] = []

    def append_block(start: int, max_lines: int, stop_patterns: list[re.Pattern[str]] | None = None) -> None:
        block = _slice_block(lines, start=start, max_lines=max_lines, stop_patterns=stop_patterns)
        if block:
            blocks.append(block)

    if "DATA_RACE" in signatures:
        for i, line in enumerate(lines):
            if re.search(r"WARNING:\s+DATA RACE", line, flags=re.IGNORECASE):
                stop = COMMON_STOP_PATTERNS + [re.compile(r"^\s*=+\s*$")]
                append_block(i, max_lines=280, stop_patterns=stop)
                break

    if "POTENTIAL_DEADLOCK" in signatures:
        for i, line in enumerate(lines):
            if re.search(r"POTENTIAL DEADLOCK", line, flags=re.IGNORECASE):
                append_block(i, max_lines=280)
                break

    if "TIMEOUT_PANIC" in signatures:
        for i, line in enumerate(lines):
            if re.search(r"panic:\s+test timed out", line, flags=re.IGNORECASE):
                append_block(i, max_lines=420)
                break

    if "GOLEAK" in signatures:
        goleak_start_patterns = [
            re.compile(r"found unexpected goroutines", re.IGNORECASE),
            re.compile(r"goleak:\s+errors on successful test run", re.IGNORECASE),
        ]
        for i, line in enumerate(lines):
            if GOLEAK_EXCLUDE_PATTERN.search(line):
                continue
            if any(pattern.search(line) for pattern in goleak_start_patterns):
                append_block(i, max_lines=260)
                break

    if "PANIC" in signatures and "TIMEOUT_PANIC" not in signatures:
        for i, line in enumerate(lines):
            if re.search(r"panic:", line, flags=re.IGNORECASE):
                append_block(i, max_lines=180)
                break

    if not blocks:
        anchors = extract_anchor_offsets(log_text)
        if anchors:
            start = max(0, anchors[0] - 1)
            append_block(start, max_lines=120)

    return blocks


def extract_stack_tokens(stack_blocks: list[str]) -> list[str]:
    tokens: set[str] = set()
    for block in stack_blocks:
        for match in re.finditer(r"([A-Za-z0-9_./-]+\.go):\d+", block):
            tokens.add(match.group(1).lower())
        for match in re.finditer(r"\b(Test[A-Za-z0-9_]+(?:/[A-Za-z0-9_.-]+)?)\b", block):
            tokens.add(match.group(1).lower())
    return sorted(tokens)[:48]


def infer_failure_type(signatures: list[str]) -> str:
    for candidate in [
        "DATA_RACE",
        "POTENTIAL_DEADLOCK",
        "TIMEOUT_PANIC",
        "GOLEAK",
        "CONDITION_NEVER_SATISFIED",
        "PANIC",
    ]:
        if candidate in signatures:
            return candidate.lower()
    return "unknown"


def estimate_confidence(
    primary_test: str | None,
    signatures: list[str],
    stack_blocks: list[str],
    stack_tokens: list[str],
) -> float:
    score = 0.2
    if primary_test:
        score += 0.45
    if any(sig != "UNKNOWN_FAILURE" for sig in signatures):
        score += 0.15
    if stack_blocks:
        score += 0.15
    if stack_tokens:
        score += 0.1
    if primary_test and "/" in primary_test:
        score += 0.05
    return min(1.0, round(score, 3))


def extract_evidence(log_text: str, stack_blocks: list[str], max_lines: int = 30) -> list[str]:
    if stack_blocks:
        evidence: list[str] = []
        for block in stack_blocks[:2]:
            for line in block.splitlines():
                stripped = line.strip()
                if not stripped:
                    continue
                evidence.append(stripped)
                if len(evidence) >= max_lines:
                    return evidence
        return evidence

    matcher = re.compile(
        r"--- FAIL:|=== NAME|\bTest:|panic:|DATA RACE|POTENTIAL DEADLOCK|goleak|Condition never satisfied",
        re.IGNORECASE,
    )
    evidence = []
    for line in log_text.splitlines():
        if GOLEAK_EXCLUDE_PATTERN.search(line):
            continue
        if matcher.search(line):
            evidence.append(line.strip())
            if len(evidence) >= max_lines:
                break
    return evidence


def build_evidence_summary(
    failure_type: str,
    primary_test: str | None,
    primary_package: str | None,
    signatures: list[str],
    evidence_lines: list[str],
) -> str:
    prefix = f"type={failure_type}; test={primary_test or 'N/A'}"
    if primary_package:
        prefix += f"; package={primary_package}"
    prefix += f"; signatures={','.join(signatures)}"
    if not evidence_lines:
        return prefix
    return f"{prefix}; first_line={evidence_lines[0][:300]}"


def parse_failures_from_log(
    record: FailureRecord,
    log_text: str,
    raw_log_ref: str,
    analysis_mode: str,
    agent_max_log_bytes: int,
    confidence_threshold: float,
) -> list[ParsedFailure]:
    if agent_max_log_bytes > 0 and len(log_text) > agent_max_log_bytes:
        log_text = log_text[:agent_max_log_bytes]

    signatures = parse_signatures(log_text)
    tests = parse_test_names(log_text)
    primary_test = tests[0] if tests else None
    failed_packages = parse_failed_packages(log_text)
    primary_package = failed_packages[0] if failed_packages else None
    anchor_offsets = extract_anchor_offsets(log_text)
    stack_blocks = extract_stack_blocks(log_text, signatures) if analysis_mode == "agent-full" else []
    stack_tokens = extract_stack_tokens(stack_blocks) if analysis_mode == "agent-full" else []
    failure_type = infer_failure_type(signatures)
    evidence = extract_evidence(log_text, stack_blocks=stack_blocks)
    confidence = (
        estimate_confidence(primary_test=primary_test, signatures=signatures, stack_blocks=stack_blocks, stack_tokens=stack_tokens)
        if analysis_mode == "agent-full"
        else 0.0
    )
    needs_inbox_fallback = analysis_mode == "agent-full" and (
        (primary_test is None and primary_package is None) or confidence < confidence_threshold
    )

    common_kwargs = {
        "record_id": record.record_id,
        "signatures": signatures,
        "evidence_lines": evidence,
        "anchor_signatures": signatures,
        "anchor_offsets": anchor_offsets,
        "log_fetch_mode": "full",
        "raw_log_ref": raw_log_ref,
        "tests": tests,
        "primary_test": primary_test,
        "primary_package": primary_package,
        "failed_packages": failed_packages,
        "failure_type": failure_type,
        "stack_blocks": stack_blocks,
        "confidence": confidence,
        "needs_inbox_fallback": needs_inbox_fallback,
        "stack_tokens": stack_tokens,
    }

    if "GOLEAK" in signatures and primary_package:
        evidence_summary = build_evidence_summary(
            failure_type=failure_type,
            primary_test=None,
            primary_package=primary_package,
            signatures=signatures,
            evidence_lines=evidence,
        )
        return [
            ParsedFailure(
                key=normalize_package_key(primary_package),
                test_name=None,
                evidence_summary=evidence_summary,
                **common_kwargs,
            )
        ]

    if not tests:
        evidence_summary = build_evidence_summary(
            failure_type=failure_type,
            primary_test=primary_test,
            primary_package=primary_package,
            signatures=signatures,
            evidence_lines=evidence,
        )
        return [
            ParsedFailure(
                key=normalize_test_key(None, signatures),
                test_name=None,
                evidence_summary=evidence_summary,
                **common_kwargs,
            )
        ]

    parsed: list[ParsedFailure] = []
    for test_name in tests:
        evidence_summary = build_evidence_summary(
            failure_type=failure_type,
            primary_test=test_name,
            primary_package=primary_package,
            signatures=signatures,
            evidence_lines=evidence,
        )
        parsed.append(
            ParsedFailure(
                key=normalize_test_key(test_name, signatures),
                test_name=test_name,
                evidence_summary=evidence_summary,
                **common_kwargs,
            )
        )
    return parsed


def is_release_branch_job(job_name: str) -> bool:
    lowered = (job_name or "").lower()
    return "/release-" in lowered or lowered.startswith("release-")


def collect_prow_jobs(repo: str, summary: RunSummary, retries: int) -> list[dict[str, Any]]:
    configured_url = f"https://prow.tidb.net/configured-jobs/{repo}"
    html = run_curl_text(configured_url, summary=summary, retries=retries)
    if not html:
        return []

    blob = extract_json_array_after(html, "let includedRepos =")
    if not blob:
        summary.skipped_unknown.append("unknown-log-source: cannot parse configured-jobs page")
        return []

    try:
        included = json.loads(blob)
    except json.JSONDecodeError:
        summary.skipped_unknown.append("json_decode_failed: configured-jobs")
        return []

    jobs = included[0].get("jobs", []) if included else []
    filtered_jobs = []
    skipped_release_jobs = 0
    for job in jobs:
        job_name = job.get("name", "")
        if not (looks_test_related(job_name) and job.get("jobHistoryLink")):
            continue
        if is_release_branch_job(job_name):
            skipped_release_jobs += 1
            continue
        filtered_jobs.append(job)

    if skipped_release_jobs:
        log_progress(f"skip release-branch prow jobs: {skipped_release_jobs}")
    return filtered_jobs


def collect_prow_failures(
    repo: str,
    since: dt.datetime,
    max_pages: int,
    summary: RunSummary,
    retries: int,
) -> tuple[list[FailureRecord], dict[str, set[str]]]:
    jobs = collect_prow_jobs(repo=repo, summary=summary, retries=retries)
    log_progress(f"prow jobs discovered: {len(jobs)}")
    failures: list[FailureRecord] = []
    outcomes_by_ci_sha: dict[str, set[str]] = {}

    for job in jobs:
        job_name = job.get("name", "")
        log_progress(f"prow job start: {job_name}")
        next_url = urllib.parse.urljoin("https://prow.tidb.net", job.get("jobHistoryLink", ""))
        pages = 0
        while next_url and pages < max_pages:
            html = run_curl_text(next_url, summary=summary, retries=retries)
            if not html:
                break
            if "failed to get job history" in html:
                summary.skipped_unknown.append(f"unknown-log-source: {job_name} history unavailable")
                break

            blob = extract_json_array_after(html, "var allBuilds =")
            if not blob:
                break
            try:
                builds = json.loads(blob)
            except json.JSONDecodeError:
                summary.skipped_unknown.append(f"json_decode_failed: allBuilds {job_name}")
                break

            if not builds:
                break

            all_older = True
            for build in builds:
                started = parse_iso8601(build.get("Started"))
                if started >= since:
                    all_older = False
                else:
                    continue

                if not build_refs_match_repo(build, repo):
                    continue

                result = str(build.get("Result", "")).upper()
                refs = build.get("Refs", {}) or {}
                pulls = refs.get("pulls", []) or []
                pr_number = pulls[0].get("number") if pulls else None
                commit_sha = pulls[0].get("sha") if pulls else refs.get("base_sha")
                ci_sha_key = f"{job_name}::{commit_sha or 'none'}"
                outcomes_by_ci_sha.setdefault(ci_sha_key, set()).add(result)

                if result not in {"FAILURE", "ERROR"}:
                    continue

                spyglass_link = build.get("SpyglassLink", "")
                ci_url = urllib.parse.urljoin("https://prow.tidb.net", spyglass_link)
                log_url = spyglass_to_build_log_url(spyglass_link)
                record_id = f"prow-{job_name}-{build.get('ID', '')}"
                failures.append(
                    FailureRecord(
                        record_id=record_id,
                        source="prow",
                        ci_name=job_name,
                        ci_url=ci_url,
                        log_url=log_url,
                        occurred_at=started.isoformat(),
                        pr_number=pr_number,
                        commit_sha=commit_sha,
                        run_id=str(build.get("ID", "")),
                        job_id=None,
                        status=result,
                    )
                )

            pages += 1
            if pages % 5 == 0:
                log_progress(f"prow job progress: {job_name} pages={pages} failures={len(failures)}")
            if all_older:
                break
            next_url = extract_older_runs_url(html)
        log_progress(f"prow job done: {job_name} pages={pages}")

    return failures, outcomes_by_ci_sha


def scope_allows_event(scope: str, event: str) -> bool:
    event = (event or "").lower()
    if scope == "pr+push":
        return event in {"pull_request", "push"}
    if scope == "pr":
        return event == "pull_request"
    if scope == "push":
        return event == "push"
    return False


def collect_actions_failures(
    repo: str,
    since: dt.datetime,
    scope: str,
    max_runs: int,
    summary: RunSummary,
    retries: int,
) -> list[FailureRecord]:
    log_progress("querying github actions run list")
    run_list = run_gh_json(
        [
            "run",
            "list",
            "--repo",
            repo,
            "--status",
            "failure",
            "--limit",
            str(max_runs),
            "--json",
            "databaseId,name,url,event,createdAt,headSha,displayTitle",
        ],
        summary=summary,
        retries=retries,
    )
    if run_list is None:
        return []
    log_progress(f"github actions runs fetched: {len(run_list)}")

    failures: list[FailureRecord] = []
    for run in run_list:
        created_at = parse_iso8601(run.get("createdAt"))
        if created_at < since:
            continue
        event = run.get("event", "")
        if not scope_allows_event(scope, event):
            continue
        run_name = run.get("name", "")
        run_id = str(run.get("databaseId", ""))
        log_progress(f"inspecting run {run_id}: {run_name}")

        run_view = run_gh_json(
            ["run", "view", run_id, "--repo", repo, "--json", "jobs"],
            summary=summary,
            retries=retries,
        )
        if not run_view:
            continue

        for job in run_view.get("jobs", []) or []:
            conclusion = str(job.get("conclusion") or "").lower()
            if conclusion not in {"failure", "timed_out"}:
                continue

            job_name = job.get("name", "")
            if not (looks_test_related(job_name) or "chunks" in job_name.lower()):
                continue

            job_id = job.get("databaseId")
            ci_name = f"{run_name} / {job_name}"
            failures.append(
                FailureRecord(
                    record_id=f"actions-{run_id}-{job_id}",
                    source="actions",
                    ci_name=ci_name,
                    ci_url=job.get("url") or run.get("url") or "",
                    log_url=None,
                    occurred_at=created_at.isoformat(),
                    pr_number=None,
                    commit_sha=run.get("headSha"),
                    run_id=run_id,
                    job_id=job_id,
                    status=conclusion.upper(),
                )
            )
        if failures and len(failures) % 10 == 0:
            log_progress(f"github actions failure records collected: {len(failures)}")

    return failures


def fetch_log_text(
    record: FailureRecord,
    repo: str,
    summary: RunSummary,
    retries: int,
) -> str | None:
    if record.source == "prow":
        if not record.log_url:
            summary.skipped_unknown.append(f"unknown-log-source: {record.ci_url}")
            return None
        return run_curl_text(record.log_url, summary=summary, retries=retries)

    if record.source == "actions":
        if record.job_id is None:
            summary.skipped_unknown.append(f"unknown-log-source: {record.ci_url}")
            return None
        ok, out, _ = run_cmd(
            ["gh", "api", f"repos/{repo}/actions/jobs/{record.job_id}/logs"],
            summary=summary,
            retries=retries,
            timeout=900,
        )
        if not ok:
            return None
        return out

    summary.skipped_unknown.append(f"unknown-log-source: {record.ci_url}")
    return None


def resolve_parse_workers(configured: int) -> int:
    if configured > 0:
        return configured
    cpu = os.cpu_count() or 1
    return max(1, cpu)


def resolve_download_workers(configured: int) -> int:
    return max(1, configured)


def resolve_log_spool_dir(base_dir: str) -> Path:
    run_id = f"{now_utc().strftime('%Y%m%dT%H%M%SZ')}-{os.getpid()}"
    if base_dir:
        root = Path(base_dir)
    else:
        root = Path("/tmp/pd-ci-flaky")
    spool_dir = root / run_id
    spool_dir.mkdir(parents=True, exist_ok=True)
    return spool_dir


def sanitize_record_id(record_id: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", record_id).strip("._")
    if not cleaned:
        return "record"
    return cleaned[:180]


def write_log_file_atomic(path: Path, content: str) -> None:
    tmp_path = path.with_suffix(path.suffix + ".part")
    with open(tmp_path, "w", encoding="utf-8", errors="replace") as f:
        f.write(content)
    os.replace(tmp_path, path)


def fetch_and_spool_log(
    record: FailureRecord,
    repo: str,
    summary: RunSummary,
    retries: int,
    spool_dir: Path,
) -> tuple[DownloadedLog | None, str | None]:
    log_text = fetch_log_text(record=record, repo=repo, summary=summary, retries=retries)
    if not log_text:
        return None, "empty_or_unavailable"

    file_name = f"{sanitize_record_id(record.record_id)}.log"
    path = spool_dir / file_name
    try:
        write_log_file_atomic(path, log_text)
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)

    return DownloadedLog(record=record, path=path), None


def parse_log_file(item: DownloadedLog, args: argparse.Namespace) -> list[ParsedFailure]:
    log_text = item.path.read_text(encoding="utf-8", errors="replace")
    return parse_failures_from_log(
        record=item.record,
        log_text=log_text,
        raw_log_ref=str(item.path),
        analysis_mode=args.analysis_mode,
        agent_max_log_bytes=args.agent_max_log_bytes,
        confidence_threshold=args.agent_confidence_threshold,
    )


def process_logs_serial(
    args: argparse.Namespace,
    records: list[FailureRecord],
    summary: RunSummary,
    spool_dir: Path,
) -> list[ParsedFailure]:
    parsed: list[ParsedFailure] = []
    total = len(records)
    for idx, record in enumerate(records, start=1):
        item, err = fetch_and_spool_log(
            record=record,
            repo=args.repo,
            summary=summary,
            retries=args.retry_count,
            spool_dir=spool_dir,
        )
        if err:
            summary.skipped_unknown.append(f"log_download_failed:{record.record_id}:{err}")
            continue

        try:
            parsed.extend(parse_log_file(item, args=args))
        except Exception as exc:  # noqa: BLE001
            summary.skipped_unknown.append(f"log_parse_failed:{record.record_id}:{exc}")

        if idx % 10 == 0 or idx == total:
            log_progress(f"log parsing progress: {idx}/{total} records, parsed_failures={len(parsed)}")
    return parsed


def process_logs_parallel(
    args: argparse.Namespace,
    records: list[FailureRecord],
    summary: RunSummary,
    spool_dir: Path,
) -> list[ParsedFailure]:
    parsed: list[ParsedFailure] = []
    parsed_lock = threading.Lock()
    status_lock = threading.Lock()
    parse_queue: queue.Queue[DownloadedLog | None] = queue.Queue(maxsize=128)
    download_workers = resolve_download_workers(args.download_workers)
    parse_workers = resolve_parse_workers(args.parse_workers)
    total = len(records)
    download_done = 0
    parse_done = 0
    queued_for_parse = 0
    download_finished = False

    def parse_worker() -> None:
        nonlocal parse_done
        while True:
            item = parse_queue.get()
            if item is None:
                parse_queue.task_done()
                return
            try:
                parsed_items = parse_log_file(item, args=args)
                with parsed_lock:
                    parsed.extend(parsed_items)
            except Exception as exc:  # noqa: BLE001
                with status_lock:
                    summary.skipped_unknown.append(f"log_parse_failed:{item.record.record_id}:{exc}")
            finally:
                with status_lock:
                    parse_done += 1
                    should_log = parse_done % 10 == 0 or (download_finished and parse_done == queued_for_parse)
                    local_parse_done = parse_done
                    local_queued = queued_for_parse
                if should_log:
                    with parsed_lock:
                        parsed_count = len(parsed)
                    log_progress(
                        f"parse progress: {local_parse_done}/{local_queued} records, parsed_failures={parsed_count}"
                    )
                parse_queue.task_done()

    parser_threads = [threading.Thread(target=parse_worker, daemon=True) for _ in range(parse_workers)]
    for t in parser_threads:
        t.start()

    with concurrent.futures.ThreadPoolExecutor(max_workers=download_workers) as executor:
        future_map = {
            executor.submit(
                fetch_and_spool_log,
                record=record,
                repo=args.repo,
                summary=summary,
                retries=args.retry_count,
                spool_dir=spool_dir,
            ): record
            for record in records
        }
        for future in concurrent.futures.as_completed(future_map):
            record = future_map[future]
            try:
                item, err = future.result()
            except Exception as exc:  # noqa: BLE001
                item = None
                err = str(exc)

            with status_lock:
                download_done += 1
                local_download_done = download_done

            if err:
                summary.skipped_unknown.append(f"log_download_failed:{record.record_id}:{err}")
            else:
                with status_lock:
                    queued_for_parse += 1
                parse_queue.put(item)

            if local_download_done % 10 == 0 or local_download_done == total:
                with status_lock:
                    local_queued = queued_for_parse
                log_progress(
                    f"download progress: {local_download_done}/{total} records, queued_for_parse={local_queued}"
                )

    with status_lock:
        download_finished = True

    for _ in parser_threads:
        parse_queue.put(None)
    parse_queue.join()
    for t in parser_threads:
        t.join()

    return parsed


def process_logs(
    args: argparse.Namespace,
    records: list[FailureRecord],
    summary: RunSummary,
) -> list[ParsedFailure]:
    if not records:
        return []

    spool_dir = resolve_log_spool_dir(args.log_spool_dir)
    summary.log_spool_dir = str(spool_dir)
    log_progress(f"log spool dir prepared: {spool_dir}")
    try:
        if args.pipeline_mode == "serial":
            parsed = process_logs_serial(args=args, records=records, summary=summary, spool_dir=spool_dir)
        else:
            parsed = process_logs_parallel(args=args, records=records, summary=summary, spool_dir=spool_dir)
    finally:
        if args.keep_logs:
            log_progress(f"log spool dir retained: {spool_dir}")
        else:
            shutil.rmtree(spool_dir, ignore_errors=True)
            summary.log_spool_dir = ""
            log_progress(f"log spool dir cleaned: {spool_dir}")

    parsed.sort(key=lambda p: (p.record_id, p.key, p.test_name or ""))
    return parsed


def fetch_ci_records(
    args: argparse.Namespace,
    since: dt.datetime,
    summary: RunSummary,
) -> tuple[list[FailureRecord], dict[str, set[str]]]:
    prow_failures: list[FailureRecord] = []
    outcomes: dict[str, set[str]] = {}
    if args.scope in {"pr+push", "push"}:
        log_progress(f"collecting prow failures (max_pages={args.max_prow_pages})")
        prow_failures, outcomes = collect_prow_failures(
            repo=args.repo,
            since=since,
            max_pages=args.max_prow_pages,
            summary=summary,
            retries=args.retry_count,
        )
        log_progress(f"prow collection done: failures={len(prow_failures)}")
    else:
        log_progress("skip prow collection due to scope=pr")

    log_progress(f"collecting github actions failures (max_runs={args.max_action_runs})")
    actions_failures = collect_actions_failures(
        repo=args.repo,
        since=since,
        scope=args.scope,
        max_runs=args.max_action_runs,
        summary=summary,
        retries=args.retry_count,
    )
    log_progress(f"github actions collection done: failures={len(actions_failures)}")

    summary.prow_records = len(prow_failures)
    summary.actions_records = len(actions_failures)
    return prow_failures + actions_failures, outcomes


def build_coarse_records(
    parsed: list[ParsedFailure],
    records_by_id: dict[str, FailureRecord],
) -> list[CoarseFailureRecord]:
    coarse_by_record: dict[str, CoarseFailureRecord] = {}
    for item in parsed:
        if item.record_id in coarse_by_record:
            continue
        record = records_by_id[item.record_id]
        coarse_by_record[item.record_id] = CoarseFailureRecord(
            record_id=item.record_id,
            source=record.source,
            ci_name=record.ci_name,
            ci_url=record.ci_url,
            log_url=record.log_url,
            occurred_at=record.occurred_at,
            pr_number=record.pr_number,
            commit_sha=record.commit_sha,
            anchor_signatures=item.anchor_signatures,
            anchor_offsets=item.anchor_offsets,
            log_fetch_mode=item.log_fetch_mode,
            raw_log_ref=item.raw_log_ref,
        )
    return sorted(coarse_by_record.values(), key=lambda x: x.record_id)


def build_agent_analyses(parsed: list[ParsedFailure]) -> list[AgentAnalysisRecord]:
    analysis_by_record: dict[str, AgentAnalysisRecord] = {}
    for item in parsed:
        if item.record_id in analysis_by_record:
            continue
        analysis_by_record[item.record_id] = AgentAnalysisRecord(
            record_id=item.record_id,
            tests=item.tests,
            primary_test=item.primary_test,
            failure_type=item.failure_type,
            stack_blocks=item.stack_blocks,
            evidence_summary=item.evidence_summary,
            confidence=item.confidence,
            needs_inbox_fallback=item.needs_inbox_fallback,
            stack_tokens=item.stack_tokens,
            primary_package=item.primary_package,
        )
    return sorted(analysis_by_record.values(), key=lambda x: x.record_id)


def load_flaky_issues(repo: str, state: str, summary: RunSummary, retries: int) -> list[dict[str, Any]]:
    data = run_gh_json(
        [
            "search",
            "issues",
            "--repo",
            repo,
            "--state",
            state,
            "--label",
            "type/ci",
            "--limit",
            "200",
            "--json",
            "number,title,body,url,state,updatedAt",
        ],
        summary=summary,
        retries=retries,
    )
    if data is None:
        return []
    return data


def normalize_issue_text(value: str) -> str:
    lowered = value.lower()
    lowered = re.sub(r"`+", "", lowered)
    lowered = re.sub(r"\s+", " ", lowered)
    return lowered.strip()


def normalize_test_name_for_match(test_name: str) -> str:
    return re.sub(r"\s+", "", test_name.strip().lower().strip("`"))


def extract_issue_stack_tokens(issue: dict[str, Any]) -> set[str]:
    text = f"{issue.get('title') or ''}\n{issue.get('body') or ''}"
    tokens: set[str] = set()
    for match in re.finditer(r"([A-Za-z0-9_./-]+\.go):\d+", text):
        tokens.add(match.group(1).lower())
    for match in re.finditer(r"\b(Test[A-Za-z0-9_]+(?:/[A-Za-z0-9_.-]+)?)\b", text):
        tokens.add(match.group(1).lower())
    return tokens


def score_issue_match(
    issue: dict[str, Any],
    test_name: str | None,
    signatures: list[str],
    stack_tokens: list[str],
    package_name: str | None = None,
) -> int:
    title = normalize_issue_text(issue.get("title") or "")
    body = normalize_issue_text(issue.get("body") or "")
    issue_text = f"{title}\n{body}"
    score = 0
    has_test_token_match = False
    has_package_match = False

    if test_name:
        normalized = normalize_test_name_for_match(test_name)
        leaf = normalized.split("/")[-1]
        if normalized and normalized in title:
            score = max(score, 130)
            has_test_token_match = True
        if normalized and normalized in body:
            score = max(score, 120)
            has_test_token_match = True
        if leaf and leaf in title:
            score = max(score, 100)
            has_test_token_match = True
        if leaf and leaf in body:
            score = max(score, 90)
            has_test_token_match = True

    if package_name:
        normalized_pkg = normalize_test_name_for_match(package_name)
        pkg_leaf = normalized_pkg.split("/")[-1]
        if normalized_pkg and normalized_pkg in issue_text:
            score = max(score, 125)
            has_package_match = True
        elif pkg_leaf and pkg_leaf in issue_text:
            score = max(score, 95)
            has_package_match = True

    sig_to_phrase = {
        "DATA_RACE": "data race",
        "POTENTIAL_DEADLOCK": "potential deadlock",
        "TIMEOUT_PANIC": "timed out",
        "GOLEAK": "goleak",
        "CONDITION_NEVER_SATISFIED": "condition never satisfied",
        "PANIC": "panic",
    }

    for sig in signatures:
        phrase = sig_to_phrase.get(sig, "")
        if not phrase:
            continue
        if phrase in title:
            score = max(score, 60)
        if phrase in body:
            score = max(score, 40)

    stack_overlap = 0
    if stack_tokens:
        issue_tokens = extract_issue_stack_tokens(issue)
        stack_overlap = len(set(stack_tokens) & issue_tokens)
        if stack_overlap > 0:
            score = max(score, 70 + min(30, stack_overlap * 4))

    if not test_name:
        has_non_unknown_signature = any(sig != "UNKNOWN_FAILURE" for sig in signatures)
        if not has_non_unknown_signature and stack_overlap == 0:
            return 0
    elif not has_test_token_match:
        # A known test must match title/body token to avoid false issue linking.
        return 0

    if "flaky" in issue_text and score < 60 and not test_name:
        # Avoid matching broad "flaky" issue text when test identity is unclear.
        return 0

    if package_name and not has_package_match and not test_name and score < 100:
        # Package-level matching should not rely on generic flaky wording or weak stack overlap.
        return 0

    return score


def choose_issue_match(
    issues: list[dict[str, Any]],
    test_name: str | None,
    signatures: list[str],
    stack_tokens: list[str],
    package_name: str | None = None,
) -> dict[str, Any] | None:
    best: dict[str, Any] | None = None
    best_score = -1
    best_updated = dt.datetime.fromtimestamp(0, tz=UTC)

    for issue in issues:
        score = score_issue_match(
            issue,
            test_name=test_name,
            package_name=package_name,
            signatures=signatures,
            stack_tokens=stack_tokens,
        )
        if score <= 0:
            continue
        updated = parse_iso8601(issue.get("updatedAt"))
        if score > best_score or (score == best_score and updated > best_updated):
            best_score = score
            best_updated = updated
            best = issue

    threshold = 100 if test_name else 90 if package_name else 75
    if best is None or best_score < threshold:
        return None
    return best


def decide_flaky(
    key: str,
    test_name: str | None,
    entries: list[ParsedFailure],
    records_by_id: dict[str, FailureRecord],
    open_issue: dict[str, Any] | None,
    closed_issue: dict[str, Any] | None,
    outcomes_by_ci_sha: dict[str, set[str]],
) -> FlakyDecision:
    records = [records_by_id[e.record_id] for e in entries]
    pr_set = {r.pr_number for r in records if r.pr_number is not None}
    sha_set = {r.commit_sha for r in records if r.commit_sha}
    confidence_values = [e.confidence for e in entries if e.confidence > 0]
    confidence = round(sum(confidence_values) / len(confidence_values), 3) if confidence_values else 0.0
    needs_inbox_fallback = any(e.needs_inbox_fallback for e in entries)

    has_existing_issue = open_issue is not None or closed_issue is not None
    existing_issue = open_issue or closed_issue

    has_same_sha_flap = False
    for r in records:
        if r.source != "prow" or not r.commit_sha:
            continue
        outcome_key = f"{r.ci_name}::{r.commit_sha}"
        outcomes = outcomes_by_ci_sha.get(outcome_key, set())
        if "FAILURE" in outcomes and "SUCCESS" in outcomes:
            has_same_sha_flap = True
            break

    if has_existing_issue:
        return FlakyDecision(
            key=key,
            test_name=test_name,
            is_flaky=True,
            reason="existing_flaky_issue",
            distinct_pr_count=len(pr_set),
            distinct_sha_count=len(sha_set),
            has_existing_issue=True,
            existing_issue_number=int(existing_issue["number"]),
            confidence=confidence,
            needs_inbox_fallback=needs_inbox_fallback,
            action_reason="matched_existing_issue",
            dedup_key=key,
        )

    if len(pr_set) >= 2:
        return FlakyDecision(
            key=key,
            test_name=test_name,
            is_flaky=True,
            reason="reproduced_across_prs",
            distinct_pr_count=len(pr_set),
            distinct_sha_count=len(sha_set),
            has_existing_issue=False,
            existing_issue_number=None,
            confidence=confidence,
            needs_inbox_fallback=needs_inbox_fallback,
            action_reason="cross_pr_repro",
            dedup_key=key,
        )

    if has_same_sha_flap:
        return FlakyDecision(
            key=key,
            test_name=test_name,
            is_flaky=True,
            reason="same_sha_flapping",
            distinct_pr_count=len(pr_set),
            distinct_sha_count=len(sha_set),
            has_existing_issue=False,
            existing_issue_number=None,
            confidence=confidence,
            needs_inbox_fallback=needs_inbox_fallback,
            action_reason="same_sha_flap",
            dedup_key=key,
        )

    return FlakyDecision(
        key=key,
        test_name=test_name,
        is_flaky=False,
        reason="likely_pr_regression_or_insufficient_evidence",
        distinct_pr_count=len(pr_set),
        distinct_sha_count=len(sha_set),
        has_existing_issue=False,
        existing_issue_number=None,
        confidence=confidence,
        needs_inbox_fallback=True,
        action_reason="insufficient_evidence",
        dedup_key=key,
    )


def format_reason(decision: FlakyDecision) -> str:
    if decision.reason == "existing_flaky_issue":
        return "Matched existing flaky issue"
    if decision.reason == "reproduced_across_prs":
        return "Reproduced across multiple PRs in the scan window"
    if decision.reason == "same_sha_flapping":
        return "Same commit shows fail/pass flapping behavior"
    return "Only observed in isolated context; likely PR regression"


def issue_comment_body(
    decision: FlakyDecision,
    links: list[str],
    signatures: list[str],
    repo: str,
    evidence_summary: str,
    package_name: str | None = None,
) -> str:
    test_display = decision.test_name or (f"{package_name} package" if package_name else decision.key)
    sig_display = ", ".join(signatures)
    intro = (
        f"Observed flaky failure again for `{test_display}`."
        if decision.is_flaky
        else f"Observed unresolved CI failure candidate for `{test_display}`."
    )
    lines = [
        intro,
        "",
        "CI links:",
    ]
    lines.extend([f"- {link}" for link in links])
    lines.extend(
        [
            "",
            f"Auto-triage basis: {format_reason(decision)}.",
            f"Failure signatures: {sig_display}",
            f"Confidence: {decision.confidence:.2f}",
            f"Evidence summary: {evidence_summary}",
            f"Source repo: {repo}",
        ]
    )
    return "\n".join(lines)


def build_issue_title(test_name: str | None, signatures: list[str], package_name: str | None = None) -> str:
    if package_name and "GOLEAK" in signatures:
        return f"GOLEAK detected in {package_name} package tests"
    if test_name:
        return f"{test_name} is flaky"
    if package_name:
        return f"{package_name} package tests are flaky"
    if signatures:
        return f"{signatures[0].replace('_', ' ').title()} in CI is flaky"
    return "Unknown test is flaky"


def build_issue_body(
    test_name: str | None,
    ci_names: list[str],
    links: list[str],
    decision: FlakyDecision,
    signatures: list[str],
    records: list[FailureRecord],
    evidence_summary: str,
    stack_blocks: list[str],
    package_name: str | None = None,
) -> str:
    jobs_block = "\n".join([f"- {name}" for name in ci_names])
    links_block = "\n".join(links)
    prs = sorted({r.pr_number for r in records if r.pr_number is not None})
    shas = sorted({r.commit_sha for r in records if r.commit_sha})

    triage_meta_lines = [
        f"Auto-triage basis: {format_reason(decision)}.",
        f"Signatures: {', '.join(signatures)}",
        f"Distinct PR count in window: {decision.distinct_pr_count}",
        f"Distinct commit count in window: {decision.distinct_sha_count}",
        f"Confidence: {decision.confidence:.2f}",
        f"Evidence summary: {evidence_summary}",
    ]

    target_key = test_name or (f"package:{package_name}" if package_name else decision.key)
    anything_else = [
        f"Test key: {target_key}",
        f"PRs: {prs if prs else 'N/A'}",
        f"SHAs: {shas if shas else 'N/A'}",
        "Source: auto triage from Prow + GitHub Actions",
        *triage_meta_lines,
    ]
    if package_name:
        anything_else.insert(1, f"Fail package: {package_name}")

    stack_excerpt = "\n\n".join(stack_blocks[:2]) if stack_blocks else "N/A"

    return "\n".join(
        [
            "## Flaky Test",
            "",
            "### Which jobs are failing",
            jobs_block,
            "",
            "### CI link",
            links_block,
            "",
            "### Reason for failure (if possible)",
            "",
            "",
            "### Stack excerpt",
            stack_excerpt,
            "",
            "### Anything else",
            "\n".join(anything_else),
        ]
    )


def parse_issue_number_from_url(url: str | None) -> int | None:
    if not url:
        return None
    match = re.search(r"/issues/(\d+)", url)
    if not match:
        return None
    return int(match.group(1))


def parse_label_list(raw: str) -> list[str]:
    labels = [label.strip() for label in raw.split(",")]
    labels = [label for label in labels if label]
    if not labels:
        return ["type/ci"]
    return labels


def ensure_inbox_issue(
    args: argparse.Namespace,
    open_issues: list[dict[str, Any]],
    summary: RunSummary,
) -> dict[str, Any] | None:
    target = normalize_issue_text(args.inbox_issue_title)
    for issue in open_issues:
        if normalize_issue_text(issue.get("title") or "") == target:
            return issue

    if args.mode != "auto":
        return {
            "number": None,
            "url": "",
            "state": "open",
            "title": args.inbox_issue_title,
            "body": "",
            "updatedAt": now_utc().isoformat(),
        }

    labels = parse_label_list(args.inbox_issue_labels)
    create_cmd = [
        "gh",
        "issue",
        "create",
        "--repo",
        args.repo,
        "--title",
        args.inbox_issue_title,
    ]
    for label in labels:
        create_cmd.extend(["--label", label])
    create_cmd.extend(
        [
            "--body",
            "This issue collects CI failures that cannot be confidently mapped to a specific flaky test.",
        ]
    )
    ok, out, _ = run_cmd(create_cmd, summary=summary, retries=args.retry_count)
    if not ok:
        return None

    url = out.strip().splitlines()[-1] if out.strip() else ""
    number = parse_issue_number_from_url(url)
    return {
        "number": number,
        "url": url,
        "state": "open",
        "title": args.inbox_issue_title,
        "body": "",
        "updatedAt": now_utc().isoformat(),
    }


def process_issues(
    args: argparse.Namespace,
    grouped: dict[str, list[ParsedFailure]],
    records_by_id: dict[str, FailureRecord],
    decisions: list[FlakyDecision],
    issue_matches: dict[str, dict[str, Any] | None],
    signatures_by_key: dict[str, list[str]],
    open_issues: list[dict[str, Any]],
    summary: RunSummary,
) -> list[IssueResolution]:
    resolutions: list[IssueResolution] = []
    issue_cache_text: dict[int, str] = {}
    posted_links_by_issue: dict[int, set[str]] = {}
    inbox_issue: dict[str, Any] | None = None

    for decision in decisions:
        key = decision.key
        if not decision.is_flaky and not decision.needs_inbox_fallback:
            continue

        entries = grouped[key]
        records = [records_by_id[e.record_id] for e in entries]
        links = sorted({r.ci_url for r in records if r.ci_url})
        ci_names = sorted({r.ci_name for r in records if r.ci_name})
        signatures = signatures_by_key.get(key, ["UNKNOWN_FAILURE"])
        evidence_summary = entries[0].evidence_summary if entries else ""
        stack_blocks = entries[0].stack_blocks if entries else []
        package_name = entries[0].primary_package if entries else None
        labels = parse_label_list(args.inbox_issue_labels)

        issue = issue_matches.get(key)
        is_inbox_fallback = False
        if issue is None and decision.needs_inbox_fallback:
            if inbox_issue is None:
                inbox_issue = ensure_inbox_issue(args=args, open_issues=open_issues, summary=summary)
            issue = inbox_issue
            is_inbox_fallback = issue is not None

        if issue:
            issue_number_raw = issue.get("number")
            issue_number = int(issue_number_raw) if issue_number_raw is not None else None
            issue_url = issue.get("url")
            state = (issue.get("state") or "").lower()

            reopened = False
            if issue_number is not None and state == "closed" and args.reopen_closed:
                if args.mode == "auto":
                    ok, _, _ = run_cmd(
                        ["gh", "issue", "reopen", str(issue_number), "--repo", args.repo],
                        summary=summary,
                        retries=args.retry_count,
                    )
                    reopened = ok
                else:
                    reopened = True

            if issue_number is not None and issue_number not in issue_cache_text:
                detail = run_gh_json(
                    [
                        "issue",
                        "view",
                        str(issue_number),
                        "--repo",
                        args.repo,
                        "--json",
                        "body,comments",
                    ],
                    summary=summary,
                    retries=args.retry_count,
                )
                if detail is None:
                    issue_cache_text[issue_number] = ""
                else:
                    comment_bodies = "\n".join(c.get("body", "") for c in (detail.get("comments") or []))
                    issue_cache_text[issue_number] = (detail.get("body", "") or "") + "\n" + comment_bodies

            existing_text = issue_cache_text.get(issue_number, "") if issue_number is not None else ""
            posted_links = posted_links_by_issue.setdefault(issue_number, set()) if issue_number is not None else set()
            new_links = [
                link
                for link in links
                if link and link not in existing_text and link not in posted_links
            ]
            if not new_links:
                resolutions.append(
                    IssueResolution(
                        key=key,
                        action="skipped_dedup",
                        issue_number=issue_number,
                        issue_url=issue_url,
                        details="all ci links already present",
                    )
                )
                continue

            comment_body = issue_comment_body(
                decision=decision,
                links=new_links,
                signatures=signatures,
                repo=args.repo,
                evidence_summary=evidence_summary,
                package_name=package_name,
            )

            if issue_number is None:
                action = "dryrun_inbox_comment" if is_inbox_fallback else "dryrun_comment"
            elif args.mode == "auto":
                ok, _, _ = run_cmd(
                    [
                        "gh",
                        "issue",
                        "comment",
                        str(issue_number),
                        "--repo",
                        args.repo,
                        "--body",
                        comment_body,
                    ],
                    summary=summary,
                    retries=args.retry_count,
                )
                if ok:
                    if is_inbox_fallback:
                        action = "inbox_reopened_and_commented" if reopened else "inbox_commented"
                    else:
                        action = "reopened_and_commented" if reopened else "commented"
                    posted_links.update(new_links)
                else:
                    action = "comment_failed"
            else:
                if is_inbox_fallback:
                    action = "dryrun_inbox_reopen_and_comment" if reopened else "dryrun_inbox_comment"
                else:
                    action = "dryrun_reopen_and_comment" if reopened else "dryrun_comment"
                posted_links.update(new_links)

            resolutions.append(
                IssueResolution(
                    key=key,
                    action=action,
                    issue_number=issue_number,
                    issue_url=issue_url,
                    details=f"links={len(new_links)}",
                )
            )
            continue

        if not decision.is_flaky:
            resolutions.append(
                IssueResolution(
                    key=key,
                    action="inbox_unavailable_skip",
                    issue_number=None,
                    issue_url=None,
                    details="needs_inbox_fallback but inbox issue unavailable",
                )
            )
            continue

        title = build_issue_title(test_name=decision.test_name, signatures=signatures, package_name=package_name)
        body = build_issue_body(
            test_name=decision.test_name,
            ci_names=ci_names,
            links=links,
            decision=decision,
            signatures=signatures,
            records=records,
            evidence_summary=evidence_summary,
            stack_blocks=stack_blocks,
            package_name=package_name,
        )

        issue_url = None
        issue_number = None
        action = "dryrun_create"
        if args.mode == "auto":
            create_cmd = [
                "gh",
                "issue",
                "create",
                "--repo",
                args.repo,
                "--title",
                title,
            ]
            for label in labels:
                create_cmd.extend(["--label", label])
            create_cmd.extend(["--body", body])

            ok, out, _ = run_cmd(create_cmd, summary=summary, retries=args.retry_count)
            if ok:
                issue_url = out.strip().splitlines()[-1] if out.strip() else None
                issue_number = parse_issue_number_from_url(issue_url)
                action = "created"
            else:
                action = "create_failed"

        resolutions.append(
            IssueResolution(
                key=key,
                action=action,
                issue_number=issue_number,
                issue_url=issue_url,
                details=title,
            )
        )

    summary.issue_actions = len(resolutions)
    return resolutions


def ensure_gh_auth(summary: RunSummary, retries: int) -> bool:
    log_progress("checking gh auth status")
    ok, _, _ = run_cmd(["gh", "auth", "status"], summary=summary, retries=retries)
    if not ok:
        summary.skipped_unknown.append("gh_auth_invalid")
        log_progress("gh auth check failed")
    else:
        log_progress("gh auth check passed")
    return ok


def build_output(
    args: argparse.Namespace,
    summary: RunSummary,
    grouped: dict[str, list[ParsedFailure]],
    decisions: list[FlakyDecision],
    resolutions: list[IssueResolution],
    records_by_id: dict[str, FailureRecord],
) -> None:
    print("Scanned window")
    print(f"- repo: {args.repo}")
    print(f"- since: {summary.scanned_window_start}")
    print(f"- until: {summary.scanned_window_end}")
    print(f"- scope: {args.scope}")
    print(f"- ci-scope: {args.ci_scope}")
    print(f"- mode: {args.mode}")
    print(f"- analysis-mode: {args.analysis_mode}")
    print(f"- pipeline-mode: {args.pipeline_mode}")
    print(f"- failures from prow: {summary.prow_records}")
    print(f"- failures from actions: {summary.actions_records}")
    if args.keep_logs and summary.log_spool_dir:
        print(f"- log spool dir: {summary.log_spool_dir}")

    print("\nFailures found")
    if not grouped:
        print("- none")
    else:
        for key, entries in sorted(grouped.items(), key=lambda item: len(item[1]), reverse=True):
            test_name = entries[0].test_name or key
            prs = sorted({records_by_id[e.record_id].pr_number for e in entries if records_by_id[e.record_id].pr_number is not None})
            print(f"- {test_name}: occurrences={len(entries)} prs={prs if prs else 'N/A'}")

    print("\nFlaky decisions")
    if not decisions:
        print("- none")
    else:
        for d in decisions:
            status = "flaky" if d.is_flaky else "not-flaky"
            print(
                f"- {d.test_name or d.key}: {status}; reason={d.reason}; "
                f"prs={d.distinct_pr_count}; issue={d.existing_issue_number or 'none'}; "
                f"confidence={d.confidence:.2f}; inbox_fallback={d.needs_inbox_fallback}"
            )

    print("\nIssue actions")
    if not resolutions:
        print("- none")
    else:
        for r in resolutions:
            print(f"- {r.key}: {r.action}; issue={r.issue_number or 'N/A'}; {r.details}")

    print("\nSkipped/Unknown")
    skipped = list(summary.skipped_unknown)
    if summary.command_failed_after_retries:
        skipped.extend([f"command_failed_after_retries: {x}" for x in summary.command_failed_after_retries])
    if not skipped:
        print("- none")
    else:
        for item in skipped:
            print(f"- {item}")


def main() -> int:
    args = parse_args()
    end = now_utc()
    start = end - dt.timedelta(days=args.days)
    summary = RunSummary(scanned_window_start=start.isoformat(), scanned_window_end=end.isoformat())
    log_progress(
        f"triage started repo={args.repo} days={args.days} scope={args.scope} mode={args.mode} "
        f"(disable with {PROGRESS_ENV}=0)"
    )

    if not ensure_gh_auth(summary=summary, retries=args.retry_count):
        build_output(
            args=args,
            summary=summary,
            grouped={},
            decisions=[],
            resolutions=[],
            records_by_id={},
        )
        return 1

    log_progress("fetching CI failure records")
    all_records, outcomes_by_ci_sha = fetch_ci_records(args=args, since=start, summary=summary)
    log_progress(f"CI records fetched total={len(all_records)}")

    records_by_id = {r.record_id: r for r in all_records}
    parsed = process_logs(args=args, records=all_records, summary=summary)
    summary.parsed_failures = len(parsed)
    log_progress(f"log parsing done: parsed_failures={summary.parsed_failures}")

    grouped: dict[str, list[ParsedFailure]] = {}
    signatures_by_key: dict[str, list[str]] = {}
    stack_tokens_by_key: dict[str, list[str]] = {}
    for item in parsed:
        grouped.setdefault(item.key, []).append(item)
        signatures_by_key.setdefault(item.key, [])
        stack_tokens_by_key.setdefault(item.key, [])
        for sig in item.signatures:
            if sig not in signatures_by_key[item.key]:
                signatures_by_key[item.key].append(sig)
        for token in item.stack_tokens:
            if token not in stack_tokens_by_key[item.key]:
                stack_tokens_by_key[item.key].append(token)

    open_issues = load_flaky_issues(repo=args.repo, state="open", summary=summary, retries=args.retry_count)
    closed_issues = load_flaky_issues(repo=args.repo, state="closed", summary=summary, retries=args.retry_count)
    coarse_records = build_coarse_records(parsed=parsed, records_by_id=records_by_id)
    agent_analyses = build_agent_analyses(parsed=parsed)

    decisions: list[FlakyDecision] = []
    issue_matches: dict[str, dict[str, Any] | None] = {}

    for key, entries in grouped.items():
        test_name = entries[0].test_name
        package_name = entries[0].primary_package
        signatures = signatures_by_key.get(key, [])
        stack_tokens = stack_tokens_by_key.get(key, [])
        open_match = choose_issue_match(
            open_issues,
            test_name=test_name,
            package_name=package_name,
            signatures=signatures,
            stack_tokens=stack_tokens,
        )
        closed_match = None if open_match else choose_issue_match(
            closed_issues,
            test_name=test_name,
            package_name=package_name,
            signatures=signatures,
            stack_tokens=stack_tokens,
        )
        issue_matches[key] = open_match or closed_match

        decision = decide_flaky(
            key=key,
            test_name=test_name,
            entries=entries,
            records_by_id=records_by_id,
            open_issue=open_match,
            closed_issue=closed_match,
            outcomes_by_ci_sha=outcomes_by_ci_sha,
        )
        decisions.append(decision)
    log_progress(f"flaky decisions computed: total={len(decisions)} flaky={sum(1 for d in decisions if d.is_flaky)}")

    summary.flaky_true = sum(1 for d in decisions if d.is_flaky)

    resolutions = process_issues(
        args=args,
        grouped=grouped,
        records_by_id=records_by_id,
        decisions=decisions,
        issue_matches=issue_matches,
        signatures_by_key=signatures_by_key,
        open_issues=open_issues,
        summary=summary,
    )
    log_progress(f"issue resolution stage done: actions={len(resolutions)} mode={args.mode}")

    build_output(
        args=args,
        summary=summary,
        grouped=grouped,
        decisions=decisions,
        resolutions=resolutions,
        records_by_id=records_by_id,
    )

    if args.out_json:
        payload = {
            "summary": dataclasses.asdict(summary),
            "records": [dataclasses.asdict(r) for r in all_records],
            "coarse_records": [dataclasses.asdict(r) for r in coarse_records],
            "agent_analyses": [dataclasses.asdict(r) for r in agent_analyses],
            "parsed_failures": [dataclasses.asdict(p) for p in parsed],
            "decisions": [dataclasses.asdict(d) for d in decisions],
            "issue_actions": [dataclasses.asdict(r) for r in resolutions],
        }
        with open(args.out_json, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, sort_keys=True)
        log_progress(f"wrote json output: {args.out_json}")

    log_progress("triage finished")

    return 0


if __name__ == "__main__":
    sys.exit(main())
