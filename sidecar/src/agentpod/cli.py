"""CLI entry for desktop sidecar."""

from __future__ import annotations

import os


def main() -> None:
    os.environ.setdefault("AGENTPOD_MONOLITH", "1")
    import uvicorn

    from agentpod.main import app

    uvicorn.run(app, host="127.0.0.1", port=8080, log_level="info")


if __name__ == "__main__":
    main()
