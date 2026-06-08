#!/usr/bin/env python3
"""将仓库根目录 VERSION 同步到 npm / Cargo / 根 pyproject.toml。"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_version() -> str:
    vf = ROOT / "VERSION"
    if not vf.is_file():
        raise SystemExit(f"missing {vf}")
    ver = vf.read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+", ver):
        raise SystemExit(f"invalid VERSION: {ver!r}")
    return ver


def update_pyproject(path: Path, ver: str) -> None:
    text = path.read_text(encoding="utf-8")
    new, n = re.subn(r'^version = "[^"]+"', f'version = "{ver}"', text, count=1, flags=re.M)
    if n != 1:
        raise SystemExit(f"version line not found in {path}")
    path.write_text(new, encoding="utf-8")


def update_json_version(path: Path, ver: str) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    data["version"] = ver
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def update_cargo_version(path: Path, ver: str) -> None:
    text = path.read_text(encoding="utf-8")
    new, n = re.subn(r'^version = "[^"]+"', f'version = "{ver}"', text, count=1, flags=re.M)
    if n != 1:
        raise SystemExit(f"version line not found in {path}")
    path.write_text(new, encoding="utf-8")


def update_tauri_conf_version(path: Path, ver: str) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    data["version"] = ver
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    ver = read_version()
    update_pyproject(ROOT / "pyproject.toml", ver)
    update_pyproject(ROOT / "host" / "pyproject.toml", ver)
    update_pyproject(ROOT / "agent" / "pyproject.toml", ver)
    update_json_version(ROOT / "frontend" / "package.json", ver)
    update_pyproject(ROOT / "sidecar" / "pyproject.toml", ver)
    update_json_version(ROOT / "desktop" / "package.json", ver)
    update_cargo_version(ROOT / "desktop" / "src-tauri" / "Cargo.toml", ver)
    update_tauri_conf_version(ROOT / "desktop" / "src-tauri" / "tauri.conf.json", ver)
    print(f"synced version {ver}")


if __name__ == "__main__":
    main()
