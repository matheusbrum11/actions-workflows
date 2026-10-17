"""TEMPLATE — copy this file to create a new rule.

This module is intentionally NOT imported by ``rules/__init__.py``, so the rule
below is never registered and never runs. It exists purely as a copy-paste
starting point. To ship a real rule:

1.  Copy this file to ``rules/<your_rule>.py`` and rename the class.
2.  Give it a unique ``id`` (also its config key) and a one-line ``description``.
3.  Implement ``check`` to return an iterable of ``Finding`` objects.
4.  Classify each finding's severity:
       - blocking  -> use ``self.finding(...)`` (inherits the configured/default
         severity, which you set via ``default_severity`` below or the config).
       - warning   -> pass ``severity=Severity.WARNING`` explicitly, OR let the
         consumer set ``severity: warning`` under ``rules.<id>`` in the config.
5.  Register it by adding one import line to ``rules/__init__.py``:
       ``from . import your_rule  # noqa: F401``
6.  Enable it in ``android/quality-gate.yml``:
       ```yaml
       rules:
         your-rule-id:
           enabled: true
           severity: blocking   # or warning
           # ...any custom options your rule reads via self.options
       ```

That is the whole contract. You never touch the registry, the CLI, or the
report — the framework discovers, configures, runs, and renders your rule.
"""

from __future__ import annotations

from typing import Iterable

from ..context import GateContext
from ..finding import Finding, Severity
from ..registry import Rule, register


# NOTE: the ``@register`` decorator is commented out on purpose so this template
# does not self-register. Uncomment it in your real copy.
# @register
class ExampleRule(Rule):
    """One-line description of what this rule checks and why."""

    id = "example-rule"
    description = "Explain the convention this rule enforces."
    # Default severity if the config does not override it. Consumers can still
    # flip this per-project via ``rules.example-rule.severity``.
    default_severity = Severity.WARNING

    def check(self, context: GateContext) -> Iterable[Finding]:
        """Inspect the project and yield findings.

        ``context`` gives you everything you need:
            * ``context.project_root``         -> absolute Path to the checkout
            * ``context.changed_files``        -> repo-relative changed paths
            * ``context.diff``                 -> raw unified diff (str)
            * ``context.kotlin_files_to_check()`` -> Kotlin files in scope
            * ``context.read_text(path)``      -> cached file contents
            * ``self.options``                 -> this rule's config block
        """
        # Read a tunable with a sensible default.
        forbidden_token = str(self.options.get("forbidden_token", "TODO"))

        for rel_path in context.kotlin_files_to_check():
            source = context.read_text(rel_path)
            for line_no, line in enumerate(source.splitlines(), start=1):
                if forbidden_token in line:
                    # Blocking finding (inherits self.severity):
                    yield self.finding(
                        f"Found forbidden token '{forbidden_token}'.",
                        file=rel_path, line=line_no,
                    )
                    # Warning finding (explicit override) would instead be:
                    # yield self.finding(
                    #     "...", file=rel_path, line=line_no,
                    #     severity=Severity.WARNING,
                    # )
