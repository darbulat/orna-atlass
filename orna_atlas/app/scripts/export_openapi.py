import argparse
import json
from pathlib import Path

from orna_atlas.app.main import app


def main() -> None:
    parser = argparse.ArgumentParser(description="Export the authoritative FastAPI OpenAPI schema")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
