"""Extensible Android PR quality gate.

A small, plugin-based gate that scans a Kotlin/Gradle project and reports
findings as either blocking (fails the PR) or warning (summary only). Rules live
under :mod:`quality_gate.rules` and self-register via :func:`quality_gate.registry.register`.

See ``android/README.md`` for how to add rules and point the gate at your own
coding-standard document.
"""

__all__ = ["cli", "config", "context", "finding", "registry", "report"]
