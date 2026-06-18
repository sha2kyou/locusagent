"""CLI entry for desktop sidecar."""

from __future__ import annotations

import os


def main() -> None:
    os.environ.setdefault("LOCUSAGENT_MONOLITH", "1")
    import uvicorn

    from locusagent.main import app
    from locus_shared.ports import LOCUSAGENT_HOST, LOCUSAGENT_PORT

    uvicorn.run(app, host=LOCUSAGENT_HOST, port=LOCUSAGENT_PORT, log_level="info")


if __name__ == "__main__":
    main()
