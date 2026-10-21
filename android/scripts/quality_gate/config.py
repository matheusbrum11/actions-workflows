"""Loading and querying the gate configuration.

Everything tunable lives in a YAML file (``android/quality-gate.yml`` by
default) so the gate logic stays free of hardcoded thresholds, paths, or rule
toggles. :class:`GateConfig` wraps the parsed dict and exposes small typed
helpers the framework and rules use.

The config also carries the *coding-standard context* — a pointer to the
document that describes which code conventions this gate enforces. The default
points at the bundled Now in Android (single-module) standard, but a consumer
can repoint it at their own document (see the README section "Apontar o gate
para um padrão próprio").
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as exc:  # pragma: no cover - guidance for a missing dep
    raise SystemExit(
        "PyYAML is required. Install it with `pip install -r "
        "android/scripts/requirements.txt`.",
    ) from exc


DEFAULT_SCAN_PATHS = ["app/src/main"]
DEFAULT_EXEMPT_PATHS = [
    "**/build/**",
    "**/generated/**",
    "**/*_Generated.kt",
]


@dataclass
class GateConfig:
    """Typed accessor over the parsed config dict.

    Attributes:
        raw: The full parsed YAML document.
        scan_paths: Directories (repo-relative) scanned for Kotlin sources.
        exempt_paths: Glob patterns excluded from every file-based rule.
        scope: ``"changed"`` (PR diff) or ``"all"`` (whole project).
    """

    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def scan_paths(self) -> list[str]:
        return list(self.raw.get("scan_paths", DEFAULT_SCAN_PATHS))

    @property
    def exempt_paths(self) -> list[str]:
        return list(self.raw.get("exempt_paths", DEFAULT_EXEMPT_PATHS))

    @property
    def scope(self) -> str:
        value = str(self.raw.get("scope", "changed")).lower()
        return value if value in {"changed", "all"} else "changed"

    @property
    def coding_standard(self) -> dict[str, Any]:
        """The coding-standard context block (name + document pointer)."""
        return dict(self.raw.get("coding_standard", {}))

    def is_exempt(self, repo_relative: str) -> bool:
        """True if a path matches any ``exempt_paths`` glob."""
        return any(fnmatch.fnmatch(repo_relative, pattern) for pattern in self.exempt_paths)

    # -- per-rule helpers used by the registry -----------------------------

    def rule_block(self, rule_id: str) -> dict[str, Any]:
        rules = self.raw.get("rules", {})
        block = rules.get(rule_id, {})
        return dict(block) if isinstance(block, dict) else {}

    def is_rule_enabled(self, rule_id: str) -> bool:
        return bool(self.rule_block(rule_id).get("enabled", False))

    def rule_severity(self, rule_id: str, default: "SeverityType") -> "SeverityType":
        from .finding import Severity

        raw = self.rule_block(rule_id).get("severity")
        return Severity.parse(raw) if raw else default


def load_config(path: Path) -> GateConfig:
    """Parse the YAML config at ``path``. An empty/missing file yields defaults."""
    if not path.exists():
        return GateConfig(raw={})
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise SystemExit(f"Config at {path} must be a YAML mapping, got {type(data).__name__}")
    return GateConfig(raw=data)


# Alias to avoid a hard import cycle in the type hint above.
SeverityType = Any
