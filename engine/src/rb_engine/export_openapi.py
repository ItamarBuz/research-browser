"""Print the engine's OpenAPI schema; the desktop app generates its typed client from it."""

import io
import json
import sys

from rb_engine.api.app import create_app
from rb_engine.runtime.container import EngineServices
from rb_engine.runtime.settings import EngineSettings


def main() -> None:
    def no_services() -> EngineServices:
        raise AssertionError("schema export never starts the app")

    app = create_app(EngineSettings(port=1, token="schema-export-only"), no_services)
    # Windows consoles default to a legacy code page and CRLF; the schema carries Hebrew text
    # and must be byte-identical on every OS (CI checks it for drift).
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    json.dump(app.openapi(), sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
