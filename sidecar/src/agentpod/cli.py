"""CLI entry for desktop sidecar."""

from __future__ import annotations

import os


def main() -> None:
    os.environ.setdefault("AGENTPOD_MONOLITH", "1")
    import uvicorn

    from agentpod.main import app
    from agentpod_shared.ports import AGENTPOD_HOST, AGENTPOD_PORT

    uvicorn.run(app, host=AGENTPOD_HOST, port=AGENTPOD_PORT, log_level="info")


if __name__ == "__main__":
    main()
