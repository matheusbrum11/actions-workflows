"""Rule: enforce a minimum test-coverage percentage from JaCoCo.

Reads one or more JaCoCo XML reports, aggregates the chosen counter (``LINE`` by
default) across them, and flags a blocking finding when coverage is below the
configured threshold (90% by default).

Config options (under ``rules.coverage``):
    * ``min_percentage``: threshold, default from the top-level ``coverage`` block
      or 90.
    * ``metric``: ``LINE`` | ``INSTRUCTION`` | ``BRANCH`` (default ``LINE``).
    * ``report_paths``: list of globs, relative to the project root, pointing at
      JaCoCo ``*.xml`` reports.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Iterable

from ..context import GateContext
from ..finding import Finding
from ..registry import Rule, register

_DEFAULT_REPORTS = [
    "**/build/reports/jacoco/**/*.xml",
    "**/build/reports/jacoco/**/jacocoTestReport.xml",
]


@register
class CoverageRule(Rule):
    """Fail when aggregated JaCoCo coverage is under the threshold."""

    id = "coverage"
    description = "Test coverage must meet the configured minimum (default 90%)."

    #: Populated after :meth:`check` so the CLI can show it in the summary header.
    last_percent: float | None = None
    last_threshold: float | None = None

    def check(self, context: GateContext) -> Iterable[Finding]:
        threshold = float(
            self.options.get(
                "min_percentage",
                context.config.raw.get("coverage", {}).get("min_percentage", 90),
            ),
        )
        metric = str(self.options.get("metric", "LINE")).upper()
        patterns = list(self.options.get("report_paths", _DEFAULT_REPORTS))

        reports = _find_reports(context.project_root, patterns)
        self.last_threshold = threshold
        if not reports:
            yield self.finding(
                "No JaCoCo report found at "
                f"{patterns}. Ensure coverage runs before the gate.",
            )
            return

        missed, covered = 0, 0
        for report in reports:
            m, c = _read_counter(report, metric)
            missed += m
            covered += c

        total = missed + covered
        if total == 0:
            yield self.finding(
                f"JaCoCo reports contained no {metric} counters; cannot verify coverage.",
            )
            return

        percent = 100.0 * covered / total
        self.last_percent = percent
        if percent < threshold:
            yield self.finding(
                f"{metric} coverage {percent:.2f}% is below the {threshold:.0f}% threshold.",
            )


def _find_reports(project_root: Path, patterns: list[str]) -> list[Path]:
    found: list[Path] = []
    seen: set[Path] = set()
    for pattern in patterns:
        for path in sorted(project_root.glob(pattern)):
            if path.is_file() and path not in seen:
                seen.add(path)
                found.append(path)
    return found


def _read_counter(report: Path, metric: str) -> tuple[int, int]:
    """Return ``(missed, covered)`` for ``metric`` at the report root."""
    try:
        tree = ET.parse(report)
    except ET.ParseError:
        return 0, 0
    root = tree.getroot()
    for counter in root.findall("counter"):
        if counter.get("type") == metric:
            return int(counter.get("missed", 0)), int(counter.get("covered", 0))
    return 0, 0
