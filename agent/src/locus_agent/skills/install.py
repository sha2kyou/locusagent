"""从 URL 安装 Skill 到当前工作区 skills/ 目录。"""

from __future__ import annotations

import io
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import unquote, urlparse

import httpx
import yaml

from ..logging import get_logger
from .embeddings import mark_skill_reindex
from .loader import FRONTMATTER_RE, _parse_skill_md, private_skill_dir
from .store import _is_valid_skill_name

log = get_logger("skill_install")

MAX_DOWNLOAD_BYTES = 25 * 1024 * 1024
MAX_ZIP_ENTRIES = 500
USER_AGENT = "Locus Agent-SkillInstaller/1.0"

GITHUB_SHORTHAND_RE = re.compile(
    r"^github:(?P<owner>[^/]+)/(?P<repo>[^/]+)(?:/(?P<subpath>.+))?$",
    re.IGNORECASE,
)
GITHUB_TREE_RE = re.compile(
    r"^https://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/tree/(?P<ref>[^/]+)(?:/(?P<subpath>.*))?$",
    re.IGNORECASE,
)
GITHUB_BLOB_RE = re.compile(
    r"^https://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/blob/(?P<ref>[^/]+)/(?P<subpath>.+)$",
    re.IGNORECASE,
)
GITHUB_REPO_RE = re.compile(
    r"^https://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/?$",
    re.IGNORECASE,
)
RAW_GITHUB_RE = re.compile(
    r"^https://raw\.githubusercontent\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/(?P<ref>[^/]+)/(?P<subpath>.+)$",
    re.IGNORECASE,
)

BLOCKED_HOSTS = {
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "::1",
    "metadata.google.internal",
}


@dataclass(slots=True)
class InstallResult:
    name: str
    description: str
    source_url: str
    install_path: str
    file_count: int

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "source_url": self.source_url,
            "install_path": self.install_path,
            "file_count": self.file_count,
        }


@dataclass(slots=True)
class SkillMdAnalysis:
    name: str
    description: str


@dataclass(slots=True)
class _FetchPlan:
    kind: Literal["archive", "skill_md"]
    download_url: str
    subpath: str | None = None


def _is_hidden(part: str) -> bool:
    return part.startswith(".") or part.startswith("_")


def _validate_https_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme != "https":
        raise ValueError("only https URLs are supported")
    host = (parsed.hostname or "").lower()
    if not host or host in BLOCKED_HOSTS or host.endswith(".local"):
        raise ValueError(f"blocked host: {host or '(empty)'}")
    if host.startswith("127.") or host.startswith("10.") or host.startswith("192.168."):
        raise ValueError(f"blocked host: {host}")
    return url.strip()


def _github_archive_url(owner: str, repo: str, ref: str = "main") -> str:
    ref = ref.strip() or "main"
    return f"https://codeload.github.com/{owner}/{repo}/zip/refs/heads/{ref}"


def _normalize_subpath(subpath: str | None) -> str | None:
    if subpath is None:
        return None
    text = unquote(subpath.strip().strip("/"))
    return text or None


def _blob_subpath_to_skill_dir(subpath: str) -> str:
    path = Path(subpath)
    if path.name.lower() == "skill.md":
        parent = path.parent.as_posix()
        return "" if parent == "." else parent
    return subpath


def parse_install_source(url: str, *, subpath: str | None = None) -> _FetchPlan:
    raw = url.strip()
    if not raw:
        raise ValueError("url is required")

    explicit_subpath = _normalize_subpath(subpath)

    m = GITHUB_SHORTHAND_RE.match(raw)
    if m:
        owner = m.group("owner")
        repo = m.group("repo")
        merged = explicit_subpath or _normalize_subpath(m.group("subpath"))
        return _FetchPlan(
            kind="archive",
            download_url=_github_archive_url(owner, repo),
            subpath=merged,
        )

    m = GITHUB_TREE_RE.match(raw)
    if m:
        merged = explicit_subpath or _normalize_subpath(m.group("subpath"))
        return _FetchPlan(
            kind="archive",
            download_url=_github_archive_url(m.group("owner"), m.group("repo"), m.group("ref")),
            subpath=merged,
        )

    m = GITHUB_BLOB_RE.match(raw)
    if m:
        merged = explicit_subpath or _blob_subpath_to_skill_dir(m.group("subpath"))
        return _FetchPlan(
            kind="archive",
            download_url=_github_archive_url(m.group("owner"), m.group("repo"), m.group("ref")),
            subpath=_normalize_subpath(merged),
        )

    m = GITHUB_REPO_RE.match(raw)
    if m:
        return _FetchPlan(
            kind="archive",
            download_url=_github_archive_url(m.group("owner"), m.group("repo")),
            subpath=explicit_subpath,
        )

    m = RAW_GITHUB_RE.match(raw)
    if m:
        if m.group("subpath").lower().endswith("skill.md"):
            return _FetchPlan(kind="skill_md", download_url=_validate_https_url(raw))
        merged = explicit_subpath or _normalize_subpath(m.group("subpath"))
        return _FetchPlan(
            kind="archive",
            download_url=_github_archive_url(m.group("owner"), m.group("repo"), m.group("ref")),
            subpath=merged,
        )

    validated = _validate_https_url(raw)
    lower = validated.lower()
    if lower.endswith(".zip") or "/archive/" in lower or "codeload.github.com/" in lower:
        return _FetchPlan(kind="archive", download_url=validated, subpath=explicit_subpath)
    if lower.endswith("/skill.md"):
        return _FetchPlan(kind="skill_md", download_url=validated)
    if explicit_subpath:
        return _FetchPlan(kind="archive", download_url=validated, subpath=explicit_subpath)
    raise ValueError(
        "unsupported URL; use a GitHub repo/tree/blob link, zip archive URL, or direct SKILL.md URL"
    )


def _download_bytes(url: str) -> bytes:
    safe_url = _validate_https_url(url)
    with httpx.Client(
        timeout=httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=5.0),
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
    ) as client:
        with client.stream("GET", safe_url) as resp:
            resp.raise_for_status()
            chunks: list[bytes] = []
            total = 0
            for chunk in resp.iter_bytes():
                total += len(chunk)
                if total > MAX_DOWNLOAD_BYTES:
                    raise ValueError(f"download too large (> {MAX_DOWNLOAD_BYTES} bytes)")
                chunks.append(chunk)
    return b"".join(chunks)


def _safe_extract_zip(data: bytes, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        if len(zf.infolist()) > MAX_ZIP_ENTRIES:
            raise ValueError(f"zip has too many entries (> {MAX_ZIP_ENTRIES})")
        for info in zf.infolist():
            member = Path(info.filename)
            if member.is_absolute() or ".." in member.parts:
                raise ValueError("unsafe zip entry")
            target = (dest / member).resolve()
            try:
                target.relative_to(dest.resolve())
            except ValueError as exc:
                raise ValueError("unsafe zip entry") from exc
        zf.extractall(dest)


def _single_extract_root(root: Path) -> Path:
    children = [p for p in root.iterdir() if p.is_dir() and not _is_hidden(p.name)]
    if len(children) == 1 and not any(root.glob("SKILL.md")):
        return children[0]
    return root


def locate_skill_dir(root: Path, subpath: str | None) -> Path:
    base = _single_extract_root(root)
    if subpath:
        rel = Path(subpath.replace("\\", "/"))
        if rel.is_absolute() or ".." in rel.parts:
            raise ValueError("invalid subpath")
        target = (base / rel).resolve()
        try:
            target.relative_to(base.resolve())
        except ValueError as exc:
            raise ValueError("subpath escapes archive root") from exc
        if target.is_file():
            if target.name != "SKILL.md":
                raise ValueError("subpath must point to a skill directory or SKILL.md")
            return target.parent
        if target.is_dir() and (target / "SKILL.md").is_file():
            return target
        raise ValueError(f"SKILL.md not found at subpath: {subpath}")

    direct = [p for p in base.glob("*/SKILL.md") if not _is_hidden(p.parent.name)]
    if len(direct) == 1:
        return direct[0].parent

    all_md = [
        p
        for p in base.rglob("SKILL.md")
        if not any(_is_hidden(part) for part in p.relative_to(base).parts)
    ]
    if len(all_md) == 1:
        return all_md[0].parent
    if len(all_md) > 1:
        rel_paths = sorted(p.parent.relative_to(base).as_posix() or "." for p in all_md)
        raise ValueError(
            "multiple SKILL.md found; specify path parameter. candidates: "
            + ", ".join(rel_paths[:12])
        )
    raise ValueError("SKILL.md not found in archive")


def analyze_skill_md(text: str, *, fallback_name: str = "") -> SkillMdAnalysis:
    """安装前校验内容是否符合 SKILL.md 规范。"""
    stripped = text.strip()
    if not stripped:
        raise ValueError("not a valid SKILL.md: file is empty")

    match = FRONTMATTER_RE.match(stripped)
    if not match:
        raise ValueError("not a valid SKILL.md: missing YAML frontmatter (--- ... ---)")

    try:
        frontmatter = yaml.safe_load(match.group("fm")) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"not a valid SKILL.md: invalid frontmatter YAML: {exc}") from exc
    if not isinstance(frontmatter, dict):
        raise ValueError("not a valid SKILL.md: frontmatter must be a mapping")

    name = str(frontmatter.get("name") or fallback_name or "").strip()
    if not name:
        raise ValueError("not a valid SKILL.md: frontmatter must include name")
    if not _is_valid_skill_name(name):
        raise ValueError(f"not a valid SKILL.md: invalid name: {name}")

    description = str(frontmatter.get("description") or "").strip()
    if not description:
        raise ValueError("not a valid SKILL.md: frontmatter must include description")

    body = match.group("body").strip()
    if not body:
        raise ValueError("not a valid SKILL.md: markdown body is empty")

    return SkillMdAnalysis(name=name, description=description)


def _copy_skill_tree(src: Path, dest: Path) -> int:
    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dest)
    count = sum(1 for p in dest.rglob("*") if p.is_file())
    return count


def install_skill_from_url(
    url: str,
    *,
    subpath: str | None = None,
    overwrite: bool = False,
) -> InstallResult:
    plan = parse_install_source(url, subpath=subpath)

    with tempfile.TemporaryDirectory(prefix="locusagent-skill-") as tmp:
        tmp_dir = Path(tmp)

        if plan.kind == "skill_md":
            text = _download_bytes(plan.download_url).decode("utf-8")
            analysis = analyze_skill_md(text)
            dest = private_skill_dir() / analysis.name
            if dest.exists() and not overwrite:
                raise FileExistsError(f"skill already exists: {analysis.name}")
            dest.mkdir(parents=True, exist_ok=True)
            (dest / "SKILL.md").write_text(text, encoding="utf-8")
            parsed = _parse_skill_md(dest / "SKILL.md", "private")
            if parsed is None:
                raise ValueError("failed to parse installed SKILL.md")
            log.info("skill_installed", name=analysis.name, source=url, kind="skill_md")
            mark_skill_reindex(parsed.name)
            return InstallResult(
                name=parsed.name,
                description=parsed.description,
                source_url=url,
                install_path=str(dest),
                file_count=1,
            )

        archive_bytes = _download_bytes(plan.download_url)
        extract_dir = tmp_dir / "extract"
        _safe_extract_zip(archive_bytes, extract_dir)
        skill_src = locate_skill_dir(extract_dir, plan.subpath)
        skill_md_text = (skill_src / "SKILL.md").read_text(encoding="utf-8")
        analysis = analyze_skill_md(skill_md_text, fallback_name=skill_src.name)
        parsed = _parse_skill_md(skill_src / "SKILL.md", "public")
        if parsed is None:
            raise ValueError("failed to parse SKILL.md")

        dest = private_skill_dir() / analysis.name
        if dest.exists() and not overwrite:
            raise FileExistsError(f"skill already exists: {analysis.name}")
        file_count = _copy_skill_tree(skill_src, dest)
        _parse_skill_md(dest / "SKILL.md", "private")
        log.info(
            "skill_installed",
            name=parsed.name,
            source=url,
            kind="archive",
            files=file_count,
        )
        mark_skill_reindex(parsed.name)
        return InstallResult(
            name=parsed.name,
            description=parsed.description,
            source_url=url,
            install_path=str(dest),
            file_count=file_count,
        )
