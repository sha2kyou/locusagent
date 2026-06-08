#!/usr/bin/env bash
# 将 Python.framework 打入 .app，并重写 sidecar-venv 内 Mach-O 的加载路径。
set -euo pipefail

APP="${1:?usage: relocate-bundle-python.sh AgentPod.app}"
PYTHON_VERSION="${PYTHON_VERSION:-3.11}"
VENV="$APP/Contents/Resources/sidecar-venv"
FRAMEWORKS="$APP/Contents/Frameworks"
PY_BIN="$VENV/bin/python${PYTHON_VERSION}"

if [[ ! -f "$PY_BIN" ]]; then
  echo "error: missing bundled python: $PY_BIN" >&2
  exit 1
fi

mapfile -t FW_DEPS < <(otool -L "$PY_BIN" | tail -n +2 | awk '{print $1}' | grep Python.framework || true)
if ((${#FW_DEPS[@]} == 0)); then
  echo "==> no Python.framework dependency; skip relocate"
  exit 0
fi

FW_SRC="$(echo "${FW_DEPS[0]}" | sed -E 's|(/.*/Python.framework)/Versions/.*|\1|')"
if [[ ! -d "$FW_SRC" ]]; then
  echo "error: Python.framework not found at $FW_SRC (build machine must have source framework)" >&2
  exit 1
fi

echo "==> embed Python.framework from $FW_SRC"
mkdir -p "$FRAMEWORKS"
rm -rf "$FRAMEWORKS/Python.framework"
ditto "$FW_SRC" "$FRAMEWORKS/Python.framework"

export APP VENV FRAMEWORKS PYTHON_VERSION
python3 <<'PY'
import os
import subprocess
from pathlib import Path

app = Path(os.environ["APP"])
venv = Path(os.environ["VENV"])
frameworks = Path(os.environ["FRAMEWORKS"])
version = os.environ["PYTHON_VERSION"]
fw_python = frameworks / "Python.framework" / "Versions" / version / "Python"

if not fw_python.is_file():
    raise SystemExit(f"missing embedded framework python: {fw_python}")


def macho_files(root: Path) -> list[Path]:
    out: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        try:
            if path.stat().st_size == 0:
                continue
        except OSError:
            continue
        proc = subprocess.run(["file", "-b", str(path)], capture_output=True, text=True, check=False)
        if "Mach-O" in proc.stdout:
            out.append(path)
    return out


def deps(path: Path) -> list[str]:
    proc = subprocess.run(["otool", "-L", str(path)], capture_output=True, text=True, check=True)
    lines = proc.stdout.splitlines()[1:]
    return [line.split()[0] for line in lines if "Python.framework" in line]


def rel_loader_path(path: Path) -> str:
    rel = os.path.relpath(fw_python, path.parent)
    return f"@loader_path/{rel}"


def change_dep(path: Path, old: str, new: str) -> None:
    subprocess.run(
        ["install_name_tool", "-change", old, new, str(path)],
        check=True,
        capture_output=True,
    )


for macho in macho_files(venv):
    for old in deps(macho):
        change_dep(macho, old, rel_loader_path(macho))

print(f"relocated {len(macho_files(venv))} Mach-O files under {venv}")
PY

echo "==> verify bundled python"
otool -L "$PY_BIN" | head -3

PY