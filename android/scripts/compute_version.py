"""Compute the next semantic version from git history (Conventional Commits).

Used by the release CD workflow. It reads the latest release tag, inspects the
commits made since that tag, and decides how to bump ``MAJOR.MINOR.PATCH``:

    * a breaking change  -> bump MAJOR   (``BREAKING CHANGE`` in the body, or a
                                           ``type!:`` subject, e.g. ``feat!:``)
    * a ``feat:`` commit  -> bump MINOR   (the "middle" number)
    * a ``fix:`` commit   -> bump PATCH   (the last number)

The highest-priority bump among all the commits wins (major > minor > patch).

It also computes the Android ``versionCode`` (a monotonically increasing integer
Play Store requires) using one of two strategies:

    * ``run_number``   -> the CI run number + an offset (what the user asked for)
    * ``commit_count`` -> total commits on HEAD + an offset (survives workflow
                           recreation; "smarter" because it never resets)

Outputs are printed and, when ``$GITHUB_OUTPUT`` is set, written there as
``version_name``, ``version_code``, ``bump``, ``previous_version`` and ``tag``
so later workflow steps can consume them.

This script is dependency-free (standard library only).
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
from dataclasses import dataclass

# A subject like "feat(scope)!: ..." or "fix!: ...". The "!" marks a breaking change.
_SUBJECT = re.compile(r"^(?P<type>[a-zA-Z]+)(?:\([^)]*\))?(?P<bang>!)?:\s")
_SEMVER_TAG = re.compile(r"^(?P<prefix>.*?)(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)$")

# Bump levels as sortable integers.
NONE, PATCH, MINOR, MAJOR = 0, 1, 2, 3
_LEVEL_NAME = {NONE: "none", PATCH: "patch", MINOR: "minor", MAJOR: "major"}
_NAME_LEVEL = {v: k for k, v in _LEVEL_NAME.items()}


@dataclass
class Version:
    major: int
    minor: int
    patch: int

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"

    def bumped(self, level: int) -> "Version":
        if level == MAJOR:
            return Version(self.major + 1, 0, 0)
        if level == MINOR:
            return Version(self.major, self.minor + 1, 0)
        if level == PATCH:
            return Version(self.major, self.minor, self.patch + 1)
        return Version(self.major, self.minor, self.patch)


def _git(*args: str) -> str:
    try:
        return subprocess.run(
            ["git", *args], capture_output=True, text=True, check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def latest_tag(tag_prefix: str) -> str | None:
    """Return the highest semver tag with ``tag_prefix``, or None if there is none."""
    tags = _git("tag", "--list", f"{tag_prefix}*", "--sort=-version:refname")
    for line in tags.splitlines():
        if _SEMVER_TAG.match(line.strip()):
            return line.strip()
    return None


def parse_version(tag: str | None, tag_prefix: str, initial: str) -> Version:
    """Parse a tag (or the initial version) into a :class:`Version`."""
    source = tag if tag else f"{tag_prefix}{initial}"
    match = _SEMVER_TAG.match(source)
    if not match:
        match = _SEMVER_TAG.match(f"{tag_prefix}{initial}")
    assert match is not None
    return Version(
        int(match.group("major")), int(match.group("minor")), int(match.group("patch")),
    )


def commits_since(tag: str | None) -> list[tuple[str, str]]:
    """Return ``(subject, body)`` for every commit after ``tag`` (or all commits)."""
    revision_range = f"{tag}..HEAD" if tag else "HEAD"
    # \x1f separates fields, \x1e separates records, so bodies with newlines survive.
    raw = _git("log", revision_range, "--format=%s%x1f%b%x1e")
    commits: list[tuple[str, str]] = []
    for record in raw.split("\x1e"):
        record = record.strip("\n")
        if not record:
            continue
        subject, _, body = record.partition("\x1f")
        commits.append((subject.strip(), body.strip()))
    return commits


def bump_level(commits: list[tuple[str, str]], default_bump: int) -> int:
    """Return the highest bump level implied by ``commits``."""
    level = NONE
    for subject, body in commits:
        match = _SUBJECT.match(subject)
        if "BREAKING CHANGE" in body or "BREAKING-CHANGE" in body:
            return MAJOR
        if match:
            if match.group("bang"):
                return MAJOR
            commit_type = match.group("type").lower()
            if commit_type == "feat":
                level = max(level, MINOR)
            elif commit_type == "fix":
                level = max(level, PATCH)
    if level == NONE and commits:
        return default_bump
    return level


def compute_version_code(strategy: str, run_number: int, offset: int) -> int:
    if strategy == "commit_count":
        count = _git("rev-list", "--count", "HEAD")
        base = int(count) if count.isdigit() else 0
        return base + offset
    return run_number + offset


def _write_output(pairs: dict[str, str]) -> None:
    target = os.environ.get("GITHUB_OUTPUT")
    if not target:
        return
    with open(target, "a", encoding="utf-8") as handle:
        for key, value in pairs.items():
            handle.write(f"{key}={value}\n")


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compute next semantic version.")
    parser.add_argument("--tag-prefix", default="v", help="Release tag prefix (default 'v').")
    parser.add_argument("--initial-version", default="0.0.0",
                        help="Version used when no tag exists yet.")
    parser.add_argument("--default-bump", default="patch",
                        choices=["none", "patch", "minor", "major"],
                        help="Bump when commits exist but none are feat/fix/breaking.")
    parser.add_argument("--version-code-strategy", default="run_number",
                        choices=["run_number", "commit_count"])
    parser.add_argument("--run-number", type=int, default=0,
                        help="CI run number (for the run_number strategy).")
    parser.add_argument("--version-code-offset", type=int, default=0,
                        help="Added to the computed versionCode.")
    return parser.parse_args(argv)


def run(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    tag = latest_tag(args.tag_prefix)
    previous = parse_version(tag, args.tag_prefix, args.initial_version)
    commits = commits_since(tag)
    level = bump_level(commits, _NAME_LEVEL[args.default_bump])
    new_version = previous.bumped(level)
    version_code = compute_version_code(
        args.version_code_strategy, args.run_number, args.version_code_offset,
    )
    new_tag = f"{args.tag_prefix}{new_version}"

    outputs = {
        "version_name": str(new_version),
        "version_code": str(version_code),
        "bump": _LEVEL_NAME[level],
        "previous_version": str(previous),
        "tag": new_tag,
    }
    for key, value in outputs.items():
        print(f"{key}={value}")
    _write_output(outputs)
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
