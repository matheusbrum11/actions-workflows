"""The plugin registry: how rules are defined and discovered.

This is the extensibility backbone. A rule is any subclass of :class:`Rule`
decorated with :func:`register`. At import time the decorator adds the rule to a
module-level registry; the orchestrator then asks the registry for every rule
the config enables and runs them in order.

To add a rule you only need to:

1. Create a module under ``rules/`` with a :class:`Rule` subclass.
2. Decorate it with ``@register``.
3. Import the module from ``rules/__init__.py`` so it self-registers.

Nothing in this file (or the CLI) has to change. See ``rules/_template.py`` for
a copy-paste starting point.
"""

from __future__ import annotations

import abc
from typing import Any, Callable, Iterable

from .context import GateContext
from .finding import Finding, Severity


class Rule(abc.ABC):
    """Base class for all quality-gate rules.

    Subclasses must set a unique :attr:`id` and a short :attr:`description`, and
    implement :meth:`check`. The ``options`` dict passed in is the per-rule
    config block (everything under ``rules.<id>`` in the config file minus the
    framework keys ``enabled`` and ``severity``), so each rule reads its own
    tunables without touching the framework.
    """

    #: Stable identifier, also the config key under ``rules:``. Override.
    id: str = ""
    #: One-line human description shown in docs and summaries. Override.
    description: str = ""
    #: Default severity if the config does not override it.
    default_severity: Severity = Severity.BLOCKING

    def __init__(self, options: dict[str, Any], severity: Severity) -> None:
        self.options = options
        #: Effective severity after applying config overrides.
        self.severity = severity

    @abc.abstractmethod
    def check(self, context: GateContext) -> Iterable[Finding]:
        """Inspect the project and yield :class:`Finding` objects.

        Implementations should return findings tagged with ``self.severity`` so
        the per-rule config override is honored. Raising is allowed — the
        orchestrator turns an unexpected exception into a blocking finding so a
        broken rule can never silently pass the gate.
        """
        raise NotImplementedError

    def finding(
        self, message: str, *, file: str | None = None, line: int | None = None,
        severity: Severity | None = None,
    ) -> Finding:
        """Convenience factory that stamps the rule id and effective severity."""
        return Finding(
            rule_id=self.id,
            severity=severity or self.severity,
            message=message,
            file=file,
            line=line,
        )


_REGISTRY: dict[str, type[Rule]] = {}


def register(rule_cls: type[Rule]) -> type[Rule]:
    """Class decorator that adds a :class:`Rule` subclass to the registry.

    Raises ``ValueError`` on a missing or duplicate id so collisions fail loudly
    at import time rather than silently shadowing a rule.
    """
    if not rule_cls.id:
        raise ValueError(f"{rule_cls.__name__} must define a non-empty `id`")
    if rule_cls.id in _REGISTRY:
        raise ValueError(f"Duplicate rule id: {rule_cls.id!r}")
    _REGISTRY[rule_cls.id] = rule_cls
    return rule_cls


def available_rules() -> dict[str, type[Rule]]:
    """Return a copy of the registry: ``{id: Rule subclass}``."""
    return dict(_REGISTRY)


def build_enabled_rules(config: "GateConfigLike") -> list[Rule]:
    """Instantiate every registered rule the config enables.

    Rules run in registry (import) order. A rule is skipped when its config
    block sets ``enabled: false`` or when it is absent and the config default is
    to only run explicitly-enabled rules.
    """
    built: list[Rule] = []
    for rule_id, rule_cls in _REGISTRY.items():
        block = config.rule_block(rule_id)
        if not config.is_rule_enabled(rule_id):
            continue
        severity = config.rule_severity(rule_id, rule_cls.default_severity)
        options = {k: v for k, v in block.items() if k not in {"enabled", "severity"}}
        built.append(rule_cls(options=options, severity=severity))
    return built


# Typing helper: the config object only needs to expose these three methods.
class GateConfigLike:  # pragma: no cover - structural type documentation only
    def rule_block(self, rule_id: str) -> dict[str, Any]: ...
    def is_rule_enabled(self, rule_id: str) -> bool: ...
    def rule_severity(self, rule_id: str, default: Severity) -> Severity: ...


RuleFactory = Callable[[dict[str, Any], Severity], Rule]
