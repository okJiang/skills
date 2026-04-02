#!/usr/bin/env python3
"""Static validation for the pd-pr-review skill."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


SHARED_RUNTIME_REFERENCES = [
    "references/reviewer-rules.md",
    "references/review-principles.md",
    "references/lane-selection.md",
]

OFFLINE_CALIBRATION_REFERENCES = [
    "references/offline-calibration.md",
    "references/benchmark-v1.json",
    "references/shadow-pr-corpus.jsonl",
]

CORE_LANES = {"metadata", "tests"}
ROUTED_LANES = {
    "root-cause",
    "config-and-compat",
    "schedule-hotpath",
    "tso-and-mcs",
    "invariants-and-boundaries",
    "observability-and-docs",
    "abstractions-and-naming",
    "agent-artifacts",
}
ALL_LANES = CORE_LANES | ROUTED_LANES

OUTPUT_SECTIONS = [
    "PR Context",
    "Active Lanes",
    "Lane Notes",
    "Consolidated Findings",
    "Open Questions / Needs More Evidence",
    "Draft Review Comments",
]


def parse_simple_frontmatter(frontmatter_text: str) -> tuple[dict[str, str] | None, list[str]]:
    issues: list[str] = []
    frontmatter: dict[str, str] = {}

    for index, line in enumerate(frontmatter_text.splitlines(), start=1):
        if not line.strip():
            continue
        if ":" not in line:
            issues.append(f"SKILL.md frontmatter line {index} is not `key: value`")
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            issues.append(f"SKILL.md frontmatter line {index} has an empty key")
            continue
        if value.startswith(("\"", "'")) and value.endswith(("\"", "'")) and len(value) >= 2:
            value = value[1:-1]
        frontmatter[key] = value

    if issues:
        return None, issues
    return frontmatter, []


def parse_skill_md(skill_dir: Path) -> tuple[dict[str, Any] | None, str, list[str]]:
    issues: list[str] = []
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return None, "", ["SKILL.md is missing"]

    content = skill_md.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n?(.*)$", content, re.DOTALL)
    if not match:
        return None, content, ["SKILL.md frontmatter is missing or malformed"]

    frontmatter, parse_issues = parse_simple_frontmatter(match.group(1))
    if parse_issues:
        return None, content, parse_issues

    return frontmatter, match.group(2), issues


def load_json(path: Path) -> tuple[Any | None, list[str]]:
    if not path.exists():
        return None, [f"{path.name} is missing"]

    try:
        return json.loads(path.read_text(encoding="utf-8")), []
    except json.JSONDecodeError as exc:
        return None, [f"{path.name} is not valid JSON: {exc}"]


def validate_frontmatter(frontmatter: dict[str, Any], body: str) -> list[str]:
    issues: list[str] = []

    if frontmatter.get("name") != "pd-pr-review":
        issues.append("SKILL.md name must be `pd-pr-review`")

    description = frontmatter.get("description")
    if not isinstance(description, str) or not description.strip():
        issues.append("SKILL.md description must be a non-empty string")
    else:
        lowered = description.lower()
        if "tikv/pd" not in lowered:
            issues.append("description should explicitly mention `tikv/pd`")
        if "review" not in lowered:
            issues.append("description should clearly say the skill reviews PRs")
        if "pr" not in lowered and "pull request" not in lowered:
            issues.append("description should mention PR or pull request trigger language")

    required_sections = [
        "## Shared Runtime Resources",
        "## Workflow",
        "## Local Output Contract",
        "## Hard Rules",
        "## Active Lanes",
    ]
    for section in required_sections:
        if section not in body:
            issues.append(f"SKILL.md body is missing section `{section}`")

    if "Never post GitHub comments" not in body:
        issues.append("SKILL.md must contain the local publish gate")

    if "exactly one primary lane file" not in body:
        issues.append("SKILL.md should state that each active lane loads exactly one primary lane file")

    for section in OUTPUT_SECTIONS:
        if f"`{section}`" not in body:
            issues.append(f"SKILL.md output contract is missing `{section}`")

    return issues


def collect_lane_names_from_lane_selection(lane_selection: str) -> set[str]:
    return set(re.findall(r"^### `([a-z0-9-]+)`$", lane_selection, re.MULTILINE))


def validate_references(skill_dir: Path) -> list[str]:
    issues: list[str] = []

    for relative_path in SHARED_RUNTIME_REFERENCES + OFFLINE_CALIBRATION_REFERENCES:
        path = skill_dir / relative_path
        if not path.exists():
            issues.append(f"required reference is missing: {relative_path}")

    lane_selection_path = skill_dir / "references/lane-selection.md"
    if not lane_selection_path.exists():
        return issues

    lane_selection = lane_selection_path.read_text(encoding="utf-8")
    lane_names = collect_lane_names_from_lane_selection(lane_selection)
    if lane_names != ALL_LANES:
        missing = sorted(ALL_LANES - lane_names)
        extra = sorted(lane_names - ALL_LANES)
        if missing:
            issues.append(f"lane-selection is missing lanes: {', '.join(missing)}")
        if extra:
            issues.append(f"lane-selection has unexpected lanes: {', '.join(extra)}")

    lane_dir = skill_dir / "references/lanes"
    if not lane_dir.exists():
        issues.append("references/lanes directory is missing")
        return issues

    for lane in sorted(ALL_LANES):
        if not (lane_dir / f"{lane}.md").exists():
            issues.append(f"primary lane file is missing: references/lanes/{lane}.md")

    for helper_path in lane_dir.glob("*.md"):
        stem = helper_path.stem
        if stem in ALL_LANES:
            continue
        if stem.endswith("-question-patterns"):
            base = stem[: -len("-question-patterns")]
        elif stem.endswith("-checklist"):
            base = stem[: -len("-checklist")]
        else:
            issues.append(f"unexpected helper file naming: references/lanes/{helper_path.name}")
            continue
        if base not in ALL_LANES:
            issues.append(
                f"helper file {helper_path.name} does not map to a known lane",
            )

    return issues


def validate_description_queries(skill_dir: Path) -> list[str]:
    issues: list[str] = []
    data, load_issues = load_json(skill_dir / "evals/description-queries.json")
    issues.extend(load_issues)
    if load_issues:
        return issues

    if not isinstance(data, dict):
        return ["description-queries.json must be a JSON object"]

    if data.get("skill") != "pd-pr-review":
        issues.append("description-queries.json `skill` must be `pd-pr-review`")

    queries = data.get("queries")
    if not isinstance(queries, list) or not queries:
        return ["description-queries.json must contain a non-empty `queries` list"]

    split_counts = {"train": {True: 0, False: 0}, "validation": {True: 0, False: 0}}
    seen_ids: set[str] = set()
    seen_prompts: dict[str, str] = {}
    for index, item in enumerate(queries):
        label = f"description query #{index + 1}"
        if not isinstance(item, dict):
            issues.append(f"{label} must be an object")
            continue

        query_id = item.get("id")
        split = item.get("split")
        should_trigger = item.get("should_trigger")
        prompt = item.get("prompt")

        if not isinstance(query_id, str) or not query_id:
            issues.append(f"{label} must have a non-empty string `id`")
        elif query_id in seen_ids:
            issues.append(f"duplicate description query id: {query_id}")
        else:
            seen_ids.add(query_id)

        if split not in split_counts:
            issues.append(f"{label} has invalid split: {split}")
            continue
        if not isinstance(should_trigger, bool):
            issues.append(f"{label} must have boolean `should_trigger`")
            continue
        if not isinstance(prompt, str) or not prompt.strip():
            issues.append(f"{label} must have a non-empty string `prompt`")
            continue
        normalized_prompt = " ".join(prompt.split()).casefold()
        previous = seen_prompts.get(normalized_prompt)
        if previous:
            issues.append(f"duplicate description query prompt: {query_id} matches {previous}")
        else:
            seen_prompts[normalized_prompt] = query_id
        split_counts[split][should_trigger] += 1

    total_positive = 0
    total_negative = 0
    for split, counts in split_counts.items():
        total = counts[True] + counts[False]
        total_positive += counts[True]
        total_negative += counts[False]
        if total < 4:
            issues.append(f"description queries need at least 4 cases in `{split}`")
        if counts[True] == 0 or counts[False] == 0:
            issues.append(
                f"description queries in `{split}` must include both trigger and non-trigger cases",
            )

    if total_positive < 8:
        issues.append("description queries need at least 8 trigger cases across train + validation")
    if total_negative < 8:
        issues.append("description queries need at least 8 non-trigger cases across train + validation")

    return issues


def validate_review_cases(skill_dir: Path) -> list[str]:
    issues: list[str] = []
    data, load_issues = load_json(skill_dir / "evals/review-cases.json")
    issues.extend(load_issues)
    if load_issues:
        return issues

    if not isinstance(data, dict):
        return ["review-cases.json must be a JSON object"]

    if data.get("skill") != "pd-pr-review":
        issues.append("review-cases.json `skill` must be `pd-pr-review`")

    required_sections = data.get("required_sections")
    if required_sections != OUTPUT_SECTIONS:
        issues.append("review-cases.json `required_sections` must match the skill output contract")

    cases = data.get("cases")
    if not isinstance(cases, list) or len(cases) < 3:
        return ["review-cases.json must contain at least 3 cases"]

    seen_ids: set[str] = set()
    for index, item in enumerate(cases):
        label = f"review case #{index + 1}"
        if not isinstance(item, dict):
            issues.append(f"{label} must be an object")
            continue

        case_id = item.get("id")
        prompt = item.get("prompt")
        expected_lanes = item.get("expected_lanes")
        forbidden_lanes = item.get("forbidden_lanes", [])
        must_stop_before_publish = item.get("must_stop_before_publish")

        if not isinstance(case_id, str) or not case_id:
            issues.append(f"{label} must have a non-empty string `id`")
        elif case_id in seen_ids:
            issues.append(f"duplicate review case id: {case_id}")
        else:
            seen_ids.add(case_id)

        if not isinstance(prompt, str) or not prompt.strip():
            issues.append(f"{label} must have a non-empty string `prompt`")

        if not isinstance(expected_lanes, list) or not expected_lanes:
            issues.append(f"{label} must have a non-empty `expected_lanes` list")
            continue

        lane_set = set(expected_lanes)
        if not CORE_LANES.issubset(lane_set):
            issues.append(f"{label} must always include `metadata` and `tests`")
        unknown_lanes = sorted(lane_set - ALL_LANES)
        if unknown_lanes:
            issues.append(f"{label} has unknown expected lanes: {', '.join(unknown_lanes)}")

        if not isinstance(forbidden_lanes, list):
            issues.append(f"{label} must have list `forbidden_lanes`")
        else:
            forbidden_set = set(forbidden_lanes)
            unknown_forbidden = sorted(forbidden_set - ALL_LANES)
            if unknown_forbidden:
                issues.append(
                    f"{label} has unknown forbidden lanes: {', '.join(unknown_forbidden)}",
                )
            if lane_set & forbidden_set:
                overlap = sorted(lane_set & forbidden_set)
                issues.append(
                    f"{label} has lanes in both expected and forbidden sets: {', '.join(overlap)}",
                )

        if must_stop_before_publish is not True:
            issues.append(f"{label} must set `must_stop_before_publish` to true")

    return issues


def validate_skill(skill_dir: Path) -> list[str]:
    skill_dir = skill_dir.resolve()
    frontmatter, body, issues = parse_skill_md(skill_dir)
    if frontmatter is None:
        return issues

    issues.extend(validate_frontmatter(frontmatter, body))
    issues.extend(validate_references(skill_dir))
    issues.extend(validate_description_queries(skill_dir))
    issues.extend(validate_review_cases(skill_dir))
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the pd-pr-review skill assets")
    parser.add_argument(
        "skill_dir",
        nargs="?",
        default=Path(__file__).resolve().parents[1],
        type=Path,
        help="Path to the pd-pr-review skill root",
    )
    args = parser.parse_args()

    issues = validate_skill(args.skill_dir)
    if issues:
        for issue in issues:
            print(f"- {issue}")
        return 1

    print("pd-pr-review validation passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
