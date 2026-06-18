"""SKILL.md 分块：供 skill 向量索引与语义召回。"""

from __future__ import annotations

import re

from .loader import Skill

_SECTION_RE = re.compile(r"^##\s+", re.MULTILINE)
_MAX_CHUNK_CHARS = 2000


def _slug(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.strip().lower())
    return slug.strip("-") or "section"


def _clip(text: str) -> str:
    text = text.strip()
    if len(text) <= _MAX_CHUNK_CHARS:
        return text
    return text[: _MAX_CHUNK_CHARS - 1] + "…"


def chunk_skill(skill: Skill) -> list[tuple[str, str]]:
    """Return (chunk_id, chunk_text) pairs for embedding."""
    chunks: list[tuple[str, str]] = []
    meta = f"{skill.name}: {(skill.description or '').strip()}".strip(": ").strip()
    if meta:
        chunks.append(("meta", _clip(meta)))

    body = (skill.body or "").strip()
    if not body:
        return chunks

    parts = _SECTION_RE.split(body)
    if len(parts) == 1:
        chunks.append(("body", _clip(f"{skill.name}\n{body}")))
        return chunks

    preamble = parts[0].strip()
    if preamble:
        chunks.append(("preamble", _clip(f"{skill.name}\n{preamble}")))

    for section in parts[1:]:
        title, _, rest = section.partition("\n")
        title = title.strip()
        content = rest.strip()
        text = f"{skill.name} — {title}\n{content}".strip()
        if text:
            chunks.append((f"section:{_slug(title)}", _clip(text)))
    return chunks
