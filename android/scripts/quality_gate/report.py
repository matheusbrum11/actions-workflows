"""Rendering findings as a Markdown summary.

The summary groups findings by severity (blocking first) and, inside each
group, by rule. It is written to ``$GITHUB_STEP_SUMMARY`` when that variable is
present (so it shows on the PR's checks page) and also returned so the CLI can
print it to stdout for local runs.
"""

from __future__ import annotations

import os
from collections import defaultdict
from pathlib import Path

from .finding import Finding, Severity


def render_summary(
    findings: list[Finding],
    *,
    standard_name: str | None = None,
    coverage_percent: float | None = None,
    coverage_threshold: float | None = None,
) -> str:
    """Build the Markdown report for a gate run."""
    blocking = [f for f in findings if f.severity is Severity.BLOCKING]
    warnings = [f for f in findings if f.severity is Severity.WARNING]

    lines: list[str] = ["# Android Quality Gate"]
    if standard_name:
        lines.append(f"**Coding standard:** {standard_name}")
    if coverage_percent is not None:
        target = f" (threshold {coverage_threshold:.0f}%)" if coverage_threshold else ""
        lines.append(f"**Coverage:** {coverage_percent:.2f}%{target}")
    lines.append("")

    status = "❌ **FAILED**" if blocking else "✅ **PASSED**"
    lines.append(
        f"{status} — {len(blocking)} blocking, {len(warnings)} warning(s).",
    )
    lines.append("")

    if blocking:
        lines.append("## ⛔ Blocking findings")
        lines.extend(_render_group(blocking))
        lines.append("")
    if warnings:
        lines.append("## ⚠️ Warnings")
        lines.extend(_render_group(warnings))
        lines.append("")
    if not findings:
        lines.append("No findings. 🎉")
        lines.append("")

    return "\n".join(lines)


def _render_group(findings: list[Finding]) -> list[str]:
    by_rule: dict[str, list[Finding]] = defaultdict(list)
    for finding in findings:
        by_rule[finding.rule_id].append(finding)

    out: list[str] = []
    for rule_id in sorted(by_rule):
        out.append(f"### `{rule_id}` ({len(by_rule[rule_id])})")
        for finding in by_rule[rule_id]:
            location = finding.location()
            prefix = f"`{location}` — " if location else ""
            out.append(f"- {prefix}{finding.message}")
        out.append("")
    return out


def write_step_summary(markdown: str) -> None:
    """Append the summary to ``$GITHUB_STEP_SUMMARY`` if the variable is set."""
    target = os.environ.get("GITHUB_STEP_SUMMARY")
    if not target:
        return
    with Path(target).open("a", encoding="utf-8") as handle:
        handle.write(markdown)
        handle.write("\n")
