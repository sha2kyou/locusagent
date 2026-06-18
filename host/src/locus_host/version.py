from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version as pkg_version
from pathlib import Path

_PKG_NAME = "locus-host"


def get_version() -> str:
    try:
        return pkg_version(_PKG_NAME)
    except PackageNotFoundError:
        pass
    vf = Path(__file__).resolve().parents[3] / "VERSION"
    if vf.is_file():
        return vf.read_text(encoding="utf-8").strip()
    return "0.0.0"
