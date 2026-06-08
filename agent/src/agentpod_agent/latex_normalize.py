"""Repair LaTeX commands broken by JSON escape decoding (e.g. artifact tool args).

Keep in sync with frontend/src/lib/latex-normalize.ts and tests/agent/test_latex_normalize.py.
"""

from __future__ import annotations

import re

_MATH_SEGMENT_RE = re.compile(r"\$\$[\s\S]*?\$\$|\$[^$\n]+\$")


def _fix_latex_escapes_in_math(segment: str) -> str:
    # Require letters after control char — avoids treating CRLF (\r\n) as \r-command.
    segment = re.sub(r"\x08([a-zA-Z]+)", r"\\b\1", segment)
    segment = re.sub(r"\x0c([a-zA-Z]+)", r"\\f\1", segment)
    segment = re.sub(r"\x0d([a-zA-Z]+)", r"\\r\1", segment)
    segment = re.sub(r"\x09([a-zA-Z]+)", r"\\t\1", segment)
    segment = re.sub(r"\newline\b", r"\\newline", segment)
    return segment


def normalize_latex_input(text: str) -> str:
    if not text:
        return text
    text = re.sub(r"\x08([a-zA-Z]+)", r"\\b\1", text)

    def repl(match: re.Match[str]) -> str:
        return _fix_latex_escapes_in_math(match.group(0))

    return _MATH_SEGMENT_RE.sub(repl, text)
