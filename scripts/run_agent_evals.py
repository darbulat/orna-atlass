"""Run registered ORNA Atlas agent evaluations by id or execution tier."""

from __future__ import annotations

from collections.abc import Mapping
import argparse
import os
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

try:
    from scripts.check_agent_harness import check_eval_manifest
except ModuleNotFoundError:
    from check_agent_harness import check_eval_manifest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = Path("evals/manifest.toml")


def resolve_command(command: list[str]) -> list[str]:
    """Run Python evals with the interpreter that launched this runner."""
    if command and command[0] == "python":
        return [sys.executable, *command[1:]]
    return command


def merge_environment(
    base: Mapping[str, str], overrides: Mapping[str, str] | None = None
) -> dict[str, str]:
    environment = dict(base)
    environment.update(overrides or {})
    return environment


def load_evaluations(root: Path) -> list[dict[str, Any]]:
    path = root / MANIFEST
    errors = check_eval_manifest(root)
    if errors:
        raise ValueError("; ".join(errors))
    payload = tomllib.loads(path.read_text(encoding="utf-8"))
    return payload["eval"]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--tier", choices=("fast", "full", "dependency"), default="fast")
    group.add_argument("--id", action="append", dest="identifiers")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--root", type=Path, default=REPOSITORY_ROOT)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    root = args.root.resolve()
    try:
        evaluations = load_evaluations(root)
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 2

    if args.list:
        for evaluation in evaluations:
            print(f"{evaluation['id']}\t{evaluation['area']}\t{evaluation['tier']}")
        return 0

    if args.identifiers:
        requested = set(args.identifiers)
        selected = [evaluation for evaluation in evaluations if evaluation["id"] in requested]
        missing = requested - {evaluation["id"] for evaluation in selected}
        if missing:
            print(f"ERROR: unknown eval ids: {', '.join(sorted(missing))}")
            return 2
    else:
        selected = [evaluation for evaluation in evaluations if evaluation["tier"] == args.tier]

    base_environment = os.environ.copy()
    base_environment["PYTHONPATH"] = os.pathsep.join(
        part for part in (str(root), base_environment.get("PYTHONPATH", "")) if part
    )
    for evaluation in selected:
        print(f"==> {evaluation['id']}", flush=True)
        environment = merge_environment(base_environment, evaluation.get("env"))
        result = subprocess.run(
            resolve_command(evaluation["command"]),
            cwd=root / evaluation.get("working_directory", "."),
            env=environment,
            check=False,
        )
        if result.returncode:
            print(f"ERROR: eval {evaluation['id']} failed with code {result.returncode}")
            return result.returncode
    print(f"Agent evals passed ({len(selected)} checks).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
