"""Command-line orchestrator for the quality gate.

Flow:
    1. Parse args and load the YAML config.
    2. Build the shared :class:`GateContext` (changed files + diff via git).
    3. Instantiate every config-enabled rule from the registry.
    4. Run each rule, turning any crash into a blocking finding.
    5. Render the Markdown summary, write it to ``$GITHUB_STEP_SUMMARY`` and stdout.
    6. Exit non-zero if any blocking finding exists (fails the PR job).

Usage:
    python -m quality_gate --project-root . --config android/quality-gate.yml \
        --base-ref origin/main
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import load_config
from .context import GateContext, compute_changed_files
from .finding import Finding, Severity
from .registry import build_enabled_rules
from .report import render_summary, write_step_summary
from .rules import coverage as coverage_rule

# Importing `rules` triggers registration of the built-in rules.
from . import rules  # noqa: F401


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Android PR quality gate.")
    parser.add_argument(
        "--project-root", default=".", type=Path,
        help="Path to the consumer project checkout (default: current directory).",
    )
    parser.add_argument(
        "--config", default=None, type=Path,
        help="Path to the gate config YAML (default: <project-root>/android/"
             "quality-gate.yml, then ./quality-gate.yml).",
    )
    parser.add_argument(
        "--base-ref", default=None,
        help="Git ref the PR is compared against, e.g. origin/main. Enables "
             "changed-files scope; omit for a full-project scan.",
    )
    parser.add_argument(
        "--fail-on-warning", action="store_true",
        help="Also fail the gate when warnings are present (default: warnings "
             "never fail).",
    )
    return parser.parse_args(argv)


def _resolve_config_path(project_root: Path, explicit: Path | None) -> Path:
    if explicit:
        return explicit
    candidates = [
        project_root / "android" / "quality-gate.yml",
        project_root / "quality-gate.yml",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def run(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    project_root = args.project_root.resolve()
    config_path = _resolve_config_path(project_root, args.config)
    config = load_config(config_path)

    changed_files, diff = compute_changed_files(project_root, args.base_ref)
    context = GateContext(
        project_root=project_root,
        config=config,
        changed_files=changed_files,
        base_ref=args.base_ref,
        diff=diff,
    )

    findings: list[Finding] = []
    coverage_percent: float | None = None
    coverage_threshold: float | None = None

    for rule in build_enabled_rules(config):
        try:
            findings.extend(rule.check(context))
        except Exception as exc:  # noqa: BLE001 - a crashing rule must not pass silently
            findings.append(
                Finding(
                    rule_id=rule.id,
                    severity=Severity.BLOCKING,
                    message=f"Rule crashed: {exc!r}",
                ),
            )
        if isinstance(rule, coverage_rule.CoverageRule):
            coverage_percent = rule.last_percent
            coverage_threshold = rule.last_threshold

    standard = config.coding_standard.get("name")
    summary = render_summary(
        findings,
        standard_name=standard,
        coverage_percent=coverage_percent,
        coverage_threshold=coverage_threshold,
    )
    write_step_summary(summary)
    print(summary)

    has_blocking = any(f.severity is Severity.BLOCKING for f in findings)
    has_warning = any(f.severity is Severity.WARNING for f in findings)
    if has_blocking or (args.fail_on_warning and has_warning):
        return 1
    return 0


def main(argv: list[str] | None = None) -> None:
    sys.exit(run(argv))
