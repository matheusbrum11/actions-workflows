"""The context object handed to every rule.

A :class:`GateContext` bundles everything a rule might need to inspect the
project: where it lives on disk, which files changed in the PR, the raw diff,
the full set of Kotlin sources, and the parsed configuration. Rules receive a
single ``context`` argument and read whatever they care about — adding a new
rule never requires changing this class.

The context is built once by :mod:`quality_gate.cli` and reused across rules.
File reads and directory scans are cached so many rules can scan the same
sources cheaply.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .config import GateConfig


@dataclass
class GateContext:
    """A view of the project under analysis, shared by every rule.

    Attributes:
        project_root: Absolute path to the consumer project checkout.
        config: Parsed :class:`~quality_gate.config.GateConfig`.
        changed_files: Repo-relative paths changed in this PR. Empty when the
            diff base is unknown (e.g. local full-repo run).
        base_ref: Git ref the PR is compared against, if any.
        diff: Raw unified diff against ``base_ref`` (may be empty).
    """

    project_root: Path
    config: GateConfig
    changed_files: list[str] = field(default_factory=list)
    base_ref: str | None = None
    diff: str = ""
    _text_cache: dict[str, str] = field(default_factory=dict, repr=False)
    _kotlin_cache: tuple[str, ...] | None = field(default=None, repr=False)

    def absolute(self, repo_relative: str) -> Path:
        """Resolve a repo-relative path to an absolute path."""
        return self.project_root / repo_relative

    def read_text(self, repo_relative: str) -> str:
        """Read and cache a UTF-8 text file. Returns '' if it cannot be read."""
        if repo_relative not in self._text_cache:
            try:
                self._text_cache[repo_relative] = self.absolute(repo_relative).read_text(
                    encoding="utf-8",
                )
            except (OSError, UnicodeDecodeError):
                self._text_cache[repo_relative] = ""
        return self._text_cache[repo_relative]

    def all_kotlin_files(self) -> list[str]:
        """Every ``.kt`` file under the configured scan paths (repo-relative).

        Honors ``exempt_paths`` glob patterns from config so generated code and
        vendored files are skipped project-wide.
        """
        if self._kotlin_cache is None:
            self._kotlin_cache = self._scan_kotlin()
        return list(self._kotlin_cache)

    def kotlin_files_to_check(self) -> list[str]:
        """Kotlin files a file-scanning rule should look at.

        When the config scope is ``changed`` and we have a diff base, returns
        only changed Kotlin files; otherwise returns the full set. This keeps PR
        runs fast while still supporting full-repo audits.
        """
        if self.config.scope == "changed" and self.changed_files:
            changed = {
                f for f in self.changed_files
                if f.endswith(".kt") and not self.config.is_exempt(f)
            }
            return [f for f in self.all_kotlin_files() if f in changed]
        return self.all_kotlin_files()

    def _scan_kotlin(self) -> tuple[str, ...]:
        results: list[str] = []
        for scan_path in self.config.scan_paths:
            root = self.absolute(scan_path)
            if not root.exists():
                continue
            for path in sorted(root.rglob("*.kt")):
                rel = path.relative_to(self.project_root).as_posix()
                if not self.config.is_exempt(rel):
                    results.append(rel)
        return tuple(results)


def compute_changed_files(project_root: Path, base_ref: str | None) -> tuple[list[str], str]:
    """Return ``(changed_files, diff)`` for ``base_ref`` using git.

    Falls back to empty results (which triggers a full scan downstream) when git
    is unavailable or ``base_ref`` is not provided.
    """
    if not base_ref:
        return [], ""
    try:
        names = subprocess.run(
            ["git", "-C", str(project_root), "diff", "--name-only", f"{base_ref}...HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout
        diff = subprocess.run(
            ["git", "-C", str(project_root), "diff", f"{base_ref}...HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return [], ""
    changed = [line.strip() for line in names.splitlines() if line.strip()]
    return changed, diff
