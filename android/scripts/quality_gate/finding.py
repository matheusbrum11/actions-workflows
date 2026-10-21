"""Core value types shared by every rule: severities and findings.

A *finding* is a single thing a rule wants to report. Rules never decide on
their own whether the gate passes or fails: they only emit findings with a
:class:`Severity`. The orchestrator (:mod:`quality_gate.cli`) aggregates every
finding and fails the build when at least one ``BLOCKING`` finding exists.

Keeping this module tiny and dependency-free means a new rule can
``from quality_gate.finding import Finding, Severity`` without pulling in
anything else.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass


class Severity(enum.Enum):
    """How much a finding matters.

    * ``BLOCKING`` — reproves the gate. Any single blocking finding makes the
      process exit with a non-zero status, which fails the PR job.
    * ``WARNING`` — informational only. It shows up in the Markdown summary but
      never fails the build.
    """

    BLOCKING = "blocking"
    WARNING = "warning"

    @classmethod
    def parse(cls, value: str) -> "Severity":
        """Parse a severity from a config string (case-insensitive).

        Accepts ``blocking``/``block``/``error`` and ``warning``/``warn``/``info``
        so config files can read naturally. Raises ``ValueError`` otherwise.
        """
        normalized = value.strip().lower()
        if normalized in {"blocking", "block", "error", "fail"}:
            return cls.BLOCKING
        if normalized in {"warning", "warn", "info"}:
            return cls.WARNING
        raise ValueError(f"Unknown severity: {value!r}")


@dataclass(frozen=True)
class Finding:
    """One issue reported by a rule.

    Attributes:
        rule_id: Id of the rule that produced the finding (e.g. ``"no-comments"``).
        severity: :class:`Severity` controlling whether it fails the gate.
        message: Human-readable description of the problem.
        file: Optional repo-relative path the finding refers to.
        line: Optional 1-based line number inside ``file``.
    """

    rule_id: str
    severity: Severity
    message: str
    file: str | None = None
    line: int | None = None

    @property
    def is_blocking(self) -> bool:
        return self.severity is Severity.BLOCKING

    def location(self) -> str:
        """Return a compact ``path:line`` location, or an empty string."""
        if self.file and self.line:
            return f"{self.file}:{self.line}"
        if self.file:
            return self.file
        return ""
