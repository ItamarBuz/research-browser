"""Engine entry point: `rb-engine --port N [--parent-pid PID]`.

The token is read from the RB_ENGINE_TOKEN environment variable so it does not show up in
process listings; `--token` exists only for manual development runs.
"""

import argparse
import logging
import os
import sys

import uvicorn

from rb_engine.api.app import create_app
from rb_engine.runtime.settings import LOOPBACK_HOST, EngineSettings
from rb_engine.runtime.watchdog import watch_parent

TOKEN_ENV_VAR = "RB_ENGINE_TOKEN"


def _parse_settings(argv: list[str]) -> EngineSettings:
    parser = argparse.ArgumentParser(prog="rb-engine", description=__doc__)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--token", help=f"dev only; prefer the {TOKEN_ENV_VAR} env var")
    parser.add_argument("--parent-pid", type=int, help="exit when this process exits")
    args = parser.parse_args(argv)

    token = args.token or os.environ.get(TOKEN_ENV_VAR)
    if not token:
        parser.error(f"an engine token is required ({TOKEN_ENV_VAR} or --token)")
    try:
        return EngineSettings(port=args.port, token=token, parent_pid=args.parent_pid)
    except ValueError as exc:
        parser.error(str(exc))


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = _parse_settings(sys.argv[1:] if argv is None else argv)
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(settings),
            host=LOOPBACK_HOST,
            port=settings.port,
            log_level="info",
            access_log=False,
        )
    )
    if settings.parent_pid is not None:

        def _stop() -> None:
            server.should_exit = True

        watch_parent(settings.parent_pid, _stop)
    server.run()


if __name__ == "__main__":
    main()
