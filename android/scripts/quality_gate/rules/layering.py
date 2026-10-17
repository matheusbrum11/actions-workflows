"""Rule: enforce the layer dependency direction.

Now in Android keeps its layers in separate Gradle modules; in this
single-module adaptation the same separation lives in packages:

    ui  ->  domain  ->  data

Allowed: ``ui`` may depend on ``domain`` and ``data``; ``domain`` may depend on
``data``. Forbidden: ``data`` importing ``domain`` or ``ui``; ``domain``
importing ``ui``. (Matching Now in Android, a ViewModel importing a repository
directly is allowed.)

A file's layer is inferred from the package segment it lives in; an import's
layer is inferred the same way. The segment-per-layer map and the forbidden
pairs are fully configurable, so you can add layers or tighten the direction
without editing this rule.
"""

from __future__ import annotations

import re
from typing import Iterable

from ..context import GateContext
from ..finding import Finding
from ..registry import Rule, register

_IMPORT = re.compile(r"^\s*import\s+([\w.]+)")

_DEFAULT_LAYERS = {"data": ".data.", "domain": ".domain.", "ui": ".ui."}
_DEFAULT_FORBIDDEN = {"data": ["domain", "ui"], "domain": ["ui"]}


@register
class LayeringRule(Rule):
    """Flag imports that violate the ui -> domain -> data dependency direction."""

    id = "layering"
    description = "Layer dependencies must flow ui -> domain -> data only."

    def check(self, context: GateContext) -> Iterable[Finding]:
        layers: dict[str, str] = dict(self.options.get("layers", _DEFAULT_LAYERS))
        forbidden: dict[str, list[str]] = {
            k: list(v) for k, v in self.options.get("forbidden", _DEFAULT_FORBIDDEN).items()
        }

        for rel_path in context.kotlin_files_to_check():
            source = context.read_text(rel_path)
            file_layer = _layer_of(source, layers)
            if file_layer is None or file_layer not in forbidden:
                continue
            banned = forbidden[file_layer]
            for line_no, imported in _imports(source):
                target_layer = _layer_of_import(imported, layers)
                if target_layer in banned:
                    yield self.finding(
                        f"'{file_layer}' layer must not import '{target_layer}' "
                        f"layer ({imported}).",
                        file=rel_path, line=line_no,
                    )


def _layer_of(source: str, layers: dict[str, str]) -> str | None:
    """Infer a file's layer from its ``package`` declaration."""
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith("package "):
            package = stripped[len("package "):].strip()
            probe = f".{package}."
            for layer, segment in layers.items():
                if segment in probe:
                    return layer
            return None
    return None


def _layer_of_import(imported: str, layers: dict[str, str]) -> str | None:
    probe = f".{imported}."
    for layer, segment in layers.items():
        if segment in probe:
            return layer
    return None


def _imports(source: str) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    for line_no, line in enumerate(source.splitlines(), start=1):
        match = _IMPORT.match(line)
        if match:
            out.append((line_no, match.group(1)))
    return out
