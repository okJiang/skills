#!/usr/bin/env python3
"""Prepare batch shadow-review bundles for the PD PR review skill."""

from __future__ import annotations

import argparse
import json
import shlex
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SKILL_DIR / "scripts"
REFERENCES_DIR = SKILL_DIR / "references"
DEFAULT_CORPUS = REFERENCES_DIR / "shadow-pr-corpus.jsonl"
ORCHESTRATOR_SCRIPT = SCRIPTS_DIR / "orchestrate_pd_pr_review.py"
ARBITER_SCRIPT = SCRIPTS_DIR / "arbitrate_pd_pr_review.py"
SHARED_SCORECARD_CONTRACT = Path(
    "/Users/jiangxianjie/.slock/agents/f873b63d-f306-4f48-aeb1-420921233381/"
    "handoff/pd-review-shadow-pilot/pd-shadow-review-scorecard-v1-2026-03-20.md"
)
MANUAL_SCORE_HEADER = (
    "case_id,pattern_id,skill_family,model_finding_ref,claimed_severity,"
    "skill_status,score_label,evidence_check,reason,followup_note"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare a batch shadow-review bundle from a shadow corpus or explicit PR list."
    )
    parser.add_argument("--repo", required=True, help="Path to the local tikv/pd checkout.")
    parser.add_argument(
        "--corpus-jsonl",
        help=(
            "Optional shadow corpus JSONL. Defaults to the bundled references/shadow-pr-corpus.jsonl "
            "when no explicit --pr is supplied."
        ),
    )
    parser.add_argument(
        "--category",
        action="append",
        default=[],
        help="Filter corpus records by category. Pass multiple times to keep multiple buckets.",
    )
    parser.add_argument(
        "--pr",
        action="append",
        default=[],
        help="Explicit PR number or URL to include. Pass multiple times.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Maximum number of corpus-selected PRs. Explicit --pr entries are always included.",
    )
    parser.add_argument("--out-dir", required=True, help="Output directory for the bundle.")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace an existing output directory if it already exists.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo).resolve()
    if not (repo_root / ".git").exists():
        print("Error: --repo must point at a git checkout.", file=sys.stderr)
        return 1

    corpus_path = resolve_corpus_path(args.corpus_jsonl, args.pr)
    if args.category and corpus_path is None:
        print("Error: --category requires a corpus JSONL source.", file=sys.stderr)
        return 1

    requested_prs = [extract_pr_number(value) for value in args.pr]
    corpus_records = load_shadow_corpus(corpus_path) if corpus_path else []
    selected_records = select_pr_records(
        corpus_records=corpus_records,
        requested_prs=requested_prs,
        categories=args.category,
        corpus_limit=args.limit,
    )
    if not selected_records:
        print("Error: no PRs selected for the shadow-review batch.", file=sys.stderr)
        return 1

    out_dir = Path(args.out_dir).resolve()
    prepare_output_directory(out_dir, overwrite=args.overwrite)

    manifest_entries: List[Dict[str, Any]] = []
    for record in selected_records:
        record = enrich_record_with_pr_metadata(repo_root=repo_root, record=record)
        plan_path = out_dir / f"pr-{record['pr_number']}" / "plan.json"
        plan = run_orchestrator(repo_root=repo_root, pr_number=int(record["pr_number"]), out_path=plan_path)
        manifest_entries.append(prepare_run_bundle(run_dir=plan_path.parent, record=record, plan=plan))

    manifest = {
        "generated_at": utc_now(),
        "repo_path": str(repo_root),
        "corpus_jsonl": str(corpus_path) if corpus_path else None,
        "scorecard_contract": str(SHARED_SCORECARD_CONTRACT),
        "selected_categories": args.category,
        "explicit_prs": requested_prs,
        "runs": manifest_entries,
    }
    write_json(out_dir / "batch-manifest.json", manifest)
    write_text(out_dir / "README.md", render_batch_readme(manifest))
    print(json.dumps({"runs": len(manifest_entries), "out_dir": str(out_dir)}, indent=2, sort_keys=True))
    return 0


def resolve_corpus_path(corpus_jsonl: str | None, explicit_prs: Iterable[str]) -> Path | None:
    if corpus_jsonl:
        return Path(corpus_jsonl).resolve()
    if explicit_prs:
        return None
    return DEFAULT_CORPUS


def load_shadow_corpus(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        raise SystemExit(f"Error: shadow corpus not found: {path}")

    merged: Dict[int, Dict[str, Any]] = {}
    order: List[int] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        payload = json.loads(line)
        pr_number = int(payload["number"])
        if pr_number not in merged:
            merged[pr_number] = {
                "pr_number": pr_number,
                "title": payload.get("title", ""),
                "url": payload.get("url", ""),
                "merged_at": payload.get("merged_at"),
                "files": [],
                "categories": [],
                "source": "shadow-corpus",
            }
            order.append(pr_number)
        record = merged[pr_number]
        category = payload.get("category")
        if category and category not in record["categories"]:
            record["categories"].append(category)
        for path_value in payload.get("files", []):
            if path_value not in record["files"]:
                record["files"].append(path_value)
    return [merged[pr_number] for pr_number in order]


def select_pr_records(
    corpus_records: Iterable[Dict[str, Any]],
    requested_prs: Iterable[int],
    categories: Iterable[str],
    corpus_limit: int | None,
) -> List[Dict[str, Any]]:
    corpus_map = {int(record["pr_number"]): dict(record) for record in corpus_records}
    selected: List[Dict[str, Any]] = []
    seen: set[int] = set()

    for pr_number in requested_prs:
        if pr_number in seen:
            continue
        record = corpus_map.get(
            pr_number,
            {
                "pr_number": pr_number,
                "title": "",
                "url": "",
                "merged_at": None,
                "files": [],
                "categories": [],
                "source": "explicit-pr",
            },
        )
        selected.append(record)
        seen.add(pr_number)

    allowed_categories = set(categories)
    corpus_added = 0
    for record in corpus_records:
        pr_number = int(record["pr_number"])
        if pr_number in seen:
            continue
        if allowed_categories and not (allowed_categories & set(record.get("categories", []))):
            continue
        selected.append(dict(record))
        seen.add(pr_number)
        corpus_added += 1
        if corpus_limit is not None and corpus_added >= corpus_limit:
            break

    return selected


def enrich_record_with_pr_metadata(repo_root: Path, record: Dict[str, Any]) -> Dict[str, Any]:
    if record.get("title") and record.get("url"):
        return record
    payload = gh_json(repo_root, ["pr", "view", str(record["pr_number"]), "--json", "number,title,url,mergedAt"])
    enriched = dict(record)
    enriched["title"] = payload.get("title", enriched.get("title", ""))
    enriched["url"] = payload.get("url", enriched.get("url", ""))
    enriched["merged_at"] = payload.get("mergedAt", enriched.get("merged_at"))
    return enriched


def prepare_output_directory(path: Path, overwrite: bool) -> None:
    if path.exists():
        if not overwrite:
            raise SystemExit(f"Error: output directory already exists: {path}")
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def run_orchestrator(repo_root: Path, pr_number: int, out_path: Path) -> Dict[str, Any]:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            "python3",
            str(ORCHESTRATOR_SCRIPT),
            "--repo",
            str(repo_root),
            "--pr",
            str(pr_number),
            "--out",
            str(out_path),
        ],
        cwd=repo_root,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "").strip()
        raise SystemExit(message or f"orchestrator failed for PR #{pr_number}")
    return json.loads(out_path.read_text(encoding="utf-8"))


def prepare_run_bundle(run_dir: Path, record: Dict[str, Any], plan: Dict[str, Any]) -> Dict[str, Any]:
    run_dir.mkdir(parents=True, exist_ok=True)
    write_json(run_dir / "source-record.json", record)
    write_json(run_dir / "plan.json", plan)

    selected_lanes = list(plan.get("selected_lanes", []))

    lane_dir = run_dir / "lane-results"
    lane_dir.mkdir(exist_ok=True)
    for lane in selected_lanes:
        write_json(lane_dir / f"{lane}.template.json", build_result_template(lane))
    write_text(
        lane_dir / "README.md",
        render_lane_readme(
            pr_number=int(record["pr_number"]),
            selected_lanes=selected_lanes,
        ),
    )

    arbiter_dir = run_dir / "arbiter"
    arbiter_dir.mkdir(exist_ok=True)
    arbiter_command = build_arbiter_command(
        plan_path=run_dir / "plan.json",
        result_paths=[lane_dir / f"{lane}.json" for lane in selected_lanes],
    )
    write_text(arbiter_dir / "dry-run-command.txt", render_command(arbiter_command))
    write_text(
        arbiter_dir / "capture-decision-command.txt",
        render_capture_command(arbiter_command, arbiter_dir / "decision.json"),
    )
    write_json(arbiter_dir / "decision.template.json", build_arbiter_decision_template())
    write_text(arbiter_dir / "README.md", render_arbiter_readme())
    write_text(arbiter_dir / "final-proposed-comments.md", render_final_comments_template())

    evaluation_dir = run_dir / "evaluation"
    evaluation_dir.mkdir(exist_ok=True)
    write_text(evaluation_dir / "manual-score.csv", MANUAL_SCORE_HEADER + "\n")
    write_text(
        evaluation_dir / "case-summary.md",
        render_case_summary_template(record=record, plan=plan),
    )
    write_text(evaluation_dir / "README.md", render_evaluation_readme())

    notes_dir = run_dir / "notes"
    notes_dir.mkdir(exist_ok=True)
    write_text(
        notes_dir / "shadow-summary.md",
        render_shadow_summary_template(record=record, plan=plan),
    )
    write_text(notes_dir / "manual-comparison.md", render_manual_comparison_template())

    return {
        "pr_number": int(record["pr_number"]),
        "title": record.get("title", ""),
        "url": record.get("url", ""),
        "categories": record.get("categories", []),
        "artifact_dir": str(run_dir),
        "plan_path": str(run_dir / "plan.json"),
        "review_lanes": selected_lanes,
        "command_budget": plan.get("risk_map", {}).get("command_budget"),
        "suggested_checks": plan.get("suggested_checks", []),
        "arbiter_dry_run_command": arbiter_command,
        "arbiter_decision_path": str(arbiter_dir / "decision.json"),
        "final_comments_path": str(arbiter_dir / "final-proposed-comments.md"),
        "manual_score_path": str(evaluation_dir / "manual-score.csv"),
        "case_summary_path": str(evaluation_dir / "case-summary.md"),
    }


def build_result_template(skill: str) -> Dict[str, Any]:
    return {
        "skill": skill,
        "status": "skip",
        "confidence": 0.0,
        "summary": "Template placeholder. Replace with the actual skill output before arbiter dry-run.",
        "findings": [],
        "checks_run": [],
    }


def build_arbiter_command(plan_path: Path, result_paths: Iterable[Path]) -> List[str]:
    command = [
        "python3",
        str(ARBITER_SCRIPT),
        "--context-json",
        str(plan_path),
    ]
    for result_path in result_paths:
        command.extend(["--result-json", str(result_path)])
    return command


def build_arbiter_decision_template() -> Dict[str, Any]:
    return {
        "postable_comments": [],
        "local_only_findings": [],
    }


def render_batch_readme(manifest: Dict[str, Any]) -> str:
    lines = [
        "# PD Shadow Review Batch",
        "",
        f"- Generated at: `{manifest['generated_at']}`",
        f"- Repo path: `{manifest['repo_path']}`",
    ]
    if manifest.get("corpus_jsonl"):
        lines.append(f"- Corpus JSONL: `{manifest['corpus_jsonl']}`")
    if manifest.get("selected_categories"):
        lines.append(
            "- Category filter: " + ", ".join(f"`{value}`" for value in manifest["selected_categories"])
        )
    if manifest.get("explicit_prs"):
        lines.append("- Explicit PRs: " + ", ".join(f"`{value}`" for value in manifest["explicit_prs"]))
    lines.extend(
        [
            "",
            "## Bundle layout",
            "",
            "- `batch-manifest.json`: machine-readable list of selected PRs and generated artifact paths.",
            "- `pr-<number>/source-record.json`: aggregated corpus or direct-selection metadata for the PR.",
            "- `pr-<number>/plan.json`: orchestrator output for the PR.",
            "- `pr-<number>/lane-results/*.template.json`: starter `SkillResult` payloads for each review lane.",
            "- `pr-<number>/arbiter/`: dry-run command, capture command, and arbiter output placeholders.",
            "- `pr-<number>/evaluation/`: manual score sheet and case-level verdict summary aligned to the shared scorecard contract.",
            "- `pr-<number>/notes/`: narrative shadow summary placeholder.",
            "",
            "## Next steps",
            "",
            "1. Fill the per-lane result JSON files next to the provided `.template.json` stubs.",
            "2. Run the arbiter capture command to populate `arbiter/decision.json` and then distill the final proposed comments.",
            "3. Score the run in `evaluation/manual-score.csv` using the shared scorecard contract.",
        ]
    )
    return "\n".join(lines) + "\n"


def render_lane_readme(
    pr_number: int, selected_lanes: Iterable[str]
) -> str:
    lines = [
        f"# Lane Results for PR #{pr_number}",
        "",
        "Fill one `SkillResult` JSON file per selected review lane.",
        "",
        "## Selected lanes",
    ]
    selected_lanes = list(selected_lanes)
    if selected_lanes:
        lines.extend(
            f"- `{lane}` -> write `{lane}.json` using `{lane}.template.json` as the starter"
            for lane in selected_lanes
        )
    else:
        lines.append("- No lanes were selected for this PR.")
    return "\n".join(lines) + "\n"


def render_shadow_summary_template(record: Dict[str, Any], plan: Dict[str, Any]) -> str:
    lines = [
        f"# Shadow Summary for PR #{record['pr_number']}",
        "",
        f"- Title: {record.get('title', '') or '(fill in if needed)'}",
        f"- URL: {record.get('url', '') or '(fill in if needed)'}",
        f"- Categories: {', '.join(record.get('categories', [])) or '(not categorized)'}",
        f"- Selected lanes: {', '.join(plan.get('selected_lanes', [])) or '(none)'}",
        f"- Suggested checks: {', '.join(plan.get('suggested_checks', [])) or '(none)'}",
        "",
        "## Shadow findings summary",
        "",
        "- Fill after the lane outputs and arbiter dry-run are complete.",
        "- Link or summarize `arbiter/final-proposed-comments.md` once populated.",
        "",
        "## Historical reviewer comparison",
        "",
        "- Note major overlaps, misses, or unexpected extra findings.",
    ]
    return "\n".join(lines) + "\n"


def render_manual_comparison_template() -> str:
    return (
        "# Manual Comparison Placeholder\n\n"
        f"- Shared scorecard contract: `{SHARED_SCORECARD_CONTRACT}`\n"
        "- Keep this file for narrative notes only; the formal row schema lives in `evaluation/manual-score.csv`.\n"
    )


def render_command(command: Iterable[str]) -> str:
    quoted = [shlex.quote(part) for part in command]
    if not quoted:
        return ""
    head, *tail = quoted
    if not tail:
        return head + "\n"
    return head + " \\\n  " + " \\\n  ".join(tail) + "\n"


def render_capture_command(command: Iterable[str], output_path: Path) -> str:
    base = render_command(command).rstrip("\n")
    return base + f" > {shlex.quote(str(output_path))}\n"


def render_arbiter_readme() -> str:
    return (
        "# Arbiter Outputs\n\n"
        "- `dry-run-command.txt`: prints the arbiter decision to stdout.\n"
        "- `capture-decision-command.txt`: captures the dry-run output into `decision.json`.\n"
        "- `decision.template.json`: stable placeholder with the expected top-level keys.\n"
        "- `final-proposed-comments.md`: summarize the postable comments after the dry-run decision is available.\n"
    )


def render_final_comments_template() -> str:
    return (
        "# Final Proposed Comments\n\n"
        "- Fill from `arbiter/decision.json` after the dry-run command is captured.\n"
        "- Group comments by root cause or skill when that improves readability.\n"
    )


def render_evaluation_readme() -> str:
    return (
        "# Evaluation Artifacts\n\n"
        f"- Shared scorecard contract: `{SHARED_SCORECARD_CONTRACT}`\n"
        "- `manual-score.csv`: one row per expected concern using the shared header.\n"
        "- For unmatched `miss` rows, leave `model_finding_ref`, `claimed_severity`, and `skill_status` blank instead of reusing a pass-like status.\n"
        "- `case-summary.md`: case-level verdict and hit/partial/miss summary for the PR.\n"
    )


def render_case_summary_template(record: Dict[str, Any], plan: Dict[str, Any]) -> str:
    lines = [
        f"# Case Summary for PR #{record['pr_number']}",
        "",
        f"- PR title: {record.get('title', '') or '(fill in if needed)'}",
        f"- Skill family / selected lanes: {', '.join(plan.get('selected_lanes', [])) or '(none)'}",
        "- Benchmark or pilot case id: ",
        "- expected_min_hits: ",
        "- hit_count: ",
        "- partial_count: ",
        "- miss_count: ",
        "- false_positive_count: ",
        "- needs_more_evidence_count: ",
        "- provisional verdict (`pass` / `soft fail` / `precision fail` / `artifact retry`): ",
        "",
        "## Notes",
        "",
        "- Explain whether misses come from lane selection, evidence quality, rubric drift, or a true lane gap.",
    ]
    return "\n".join(lines) + "\n"


def gh_json(repo_root: Path, args: List[str]) -> Any:
    result = subprocess.run(
        ["gh", *args],
        cwd=repo_root,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "").strip()
        raise SystemExit(message or "gh command failed")
    return json.loads(result.stdout or "{}")


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_text(path: Path, payload: str) -> None:
    path.write_text(payload, encoding="utf-8")


def extract_pr_number(value: str) -> int:
    stripped = value.rstrip("/").split("/")[-1]
    try:
        return int(stripped)
    except ValueError as exc:
        raise SystemExit(f"Error: unable to parse PR number from {value!r}") from exc


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


if __name__ == "__main__":
    raise SystemExit(main())
