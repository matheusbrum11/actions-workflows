"""Rule: Kotlin source should carry no implementation comments.

This enforces a stricter convention than Now in Android itself (which uses
inline comments and ``// TODO`` notes): the codebase should explain itself
through naming and structure, not prose in the body.

What it flags (configurable):
    * ``//`` line comments
    * ``/* ... */`` block comments

What it exempts (configurable):
    * The license header (the leading block comment before ``package``).
    * ``/** ... */`` KDoc on **public** declarations (public API docs are
      allowed; KDoc on private/internal members is still flagged).
    * Any path matching ``exempt_paths`` (handled upstream in the context).

The scanner is a small Kotlin-aware state machine so ``//`` inside a string
literal is never mistaken for a comment.
"""

from __future__ import annotations

import re
from typing import Iterable

from ..context import GateContext
from ..finding import Finding
from ..registry import Rule, register

_VISIBILITY = re.compile(r"\b(private|internal|protected)\b")
_DECLARATION = re.compile(
    r"\b(class|interface|object|fun|val|var|enum|sealed|annotation|typealias)\b",
)


@register
class NoCommentsRule(Rule):
    """Flag comments in Kotlin sources, with license-header and KDoc exemptions."""

    id = "no-comments"
    description = "Kotlin files must not contain implementation comments."

    def check(self, context: GateContext) -> Iterable[Finding]:
        allow_license = bool(self.options.get("allow_license_header", True))
        allow_kdoc = bool(self.options.get("allow_kdoc_on_public_api", True))
        flag_line = bool(self.options.get("flag_line_comments", True))
        flag_block = bool(self.options.get("flag_block_comments", True))

        for rel_path in context.kotlin_files_to_check():
            source = context.read_text(rel_path)
            lines = source.splitlines()
            for comment in _scan_comments(source):
                if comment.kind == "line" and not flag_line:
                    continue
                if comment.kind == "block" and not flag_block:
                    continue
                if comment.kind == "block" and allow_license and _is_license_header(
                    comment, lines,
                ):
                    continue
                if comment.kind == "kdoc":
                    if allow_kdoc and _documents_public_api(comment, lines):
                        continue
                    yield self.finding(
                        "KDoc is only allowed on public declarations.",
                        file=rel_path, line=comment.line,
                    )
                    continue
                yield self.finding(
                    f"Remove the {comment.kind} comment; code should be self-explanatory.",
                    file=rel_path, line=comment.line,
                )


class _Comment:
    """A comment token located in a source file (1-based ``line``)."""

    __slots__ = ("line", "end_line", "kind")

    def __init__(self, line: int, end_line: int, kind: str) -> None:
        self.line = line
        self.end_line = end_line
        self.kind = kind  # "line" | "block" | "kdoc"


def _scan_comments(source: str) -> list[_Comment]:
    """Return every comment in ``source`` as a list of :class:`_Comment`.

    A hand-rolled state machine walks the characters tracking whether we are in
    a normal context, a string, a char literal, or a comment, so comment markers
    inside string literals are ignored.
    """
    comments: list[_Comment] = []
    i, n = 0, len(source)
    line = 1
    state = "normal"  # normal | line_str | multi_str | char | line_cmt | block_cmt
    cmt_start_line = 0
    cmt_is_kdoc = False

    while i < n:
        ch = source[i]
        nxt = source[i + 1] if i + 1 < n else ""
        if ch == "\n":
            line += 1

        if state == "normal":
            if ch == '"' and source[i:i + 3] == '"""':
                state, i = "multi_str", i + 3
                continue
            if ch == '"':
                state = "line_str"
            elif ch == "'":
                state = "char"
            elif ch == "/" and nxt == "/":
                comments.append(_Comment(line, line, "line"))
                state = "line_cmt"
                i += 2
                continue
            elif ch == "/" and nxt == "*":
                cmt_start_line = line
                cmt_is_kdoc = source[i:i + 3] == "/**"
                state = "block_cmt"
                i += 2
                continue
        elif state == "line_str":
            if ch == "\\":
                i += 2
                continue
            if ch == '"' or ch == "\n":
                state = "normal"
        elif state == "multi_str":
            if source[i:i + 3] == '"""':
                state, i = "normal", i + 3
                continue
        elif state == "char":
            if ch == "\\":
                i += 2
                continue
            if ch == "'" or ch == "\n":
                state = "normal"
        elif state == "line_cmt":
            if ch == "\n":
                state = "normal"
        elif state == "block_cmt":
            if ch == "*" and nxt == "/":
                comments.append(
                    _Comment(cmt_start_line, line, "kdoc" if cmt_is_kdoc else "block"),
                )
                state, i = "normal", i + 2
                continue
        i += 1
    return comments


def _is_license_header(comment: _Comment, lines: list[str]) -> bool:
    """A block comment is the license header if it precedes the ``package`` line."""
    for idx, text in enumerate(lines, start=1):
        stripped = text.strip()
        if not stripped:
            continue
        if stripped.startswith("package "):
            return comment.line < idx
        if stripped.startswith(("/*", "*", "//")):
            continue
        return False
    return comment.line == 1


def _documents_public_api(comment: _Comment, lines: list[str]) -> bool:
    """True if the KDoc block is immediately followed by a public declaration."""
    head: list[str] = []
    for text in lines[comment.end_line:]:
        stripped = text.strip()
        if not stripped or stripped.startswith("@"):
            continue
        head.append(stripped)
        if len(head) >= 3:
            break
    joined = " ".join(head)
    if not _DECLARATION.search(joined):
        return False
    return not _VISIBILITY.search(joined)
