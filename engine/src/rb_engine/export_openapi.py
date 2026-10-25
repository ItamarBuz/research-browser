"""Print the engine's OpenAPI schema; the desktop app generates its typed client from it."""

import io
import json
import sys

from rb_engine.api.app import create_app
from rb_engine.runtime.settings import EngineSettings


def main() -> None:
    app = create_app(EngineSettings(port=1, token="schema-export-only"))
    # Windows consoles default to a legacy code page; the schema will carry Hebrew text.
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")
    json.dump(app.openapi(), sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
