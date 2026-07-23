"""Validate the repository-local agent contracts, roles, skills, and eval registry."""

from __future__ import annotations

import argparse
import re
import tomllib
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FILES = {
    "AGENTS.md",
    ".agents/context-map.toml",
    ".agents/roles/README.md",
    "docs/architecture/README.md",
    "docs/adr/README.md",
    "evals/manifest.toml",
    "specs/README.md",
    "specs/TEMPLATE.md",
}
REQUIRED_ROLES = {
    "architect",
    "backend",
    "documentation",
    "frontend",
    "security",
    "test",
}
REQUIRED_SKILLS = {
    "create-api",
    "create-component",
    "optimize-query",
    "refactor-module",
    "review-change",
    "write-tests",
}
SKILL_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _skill_frontmatter(path: Path) -> tuple[dict[str, str], list[str]]:
    errors: list[str] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return {}, [f"{path}: cannot read skill: {exc}"]
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        return {}, [f"{path}: SKILL.md must start with YAML frontmatter"]
    try:
        end = lines.index("---", 1)
    except ValueError:
        return {}, [f"{path}: SKILL.md frontmatter is not closed"]

    metadata: dict[str, str] = {}
    for line_number, line in enumerate(lines[1:end], start=2):
        if not line.strip():
            continue
        if ":" not in line:
            errors.append(f"{path}:{line_number}: invalid frontmatter line")
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key in metadata:
            errors.append(f"{path}:{line_number}: duplicate frontmatter key {key}")
        metadata[key] = value
    if set(metadata) != {"name", "description"}:
        errors.append(f"{path}: frontmatter must contain only name and description")
    if not metadata.get("description"):
        errors.append(f"{path}: skill description must not be empty")
    if not any(line.strip() for line in lines[end + 1 :]):
        errors.append(f"{path}: skill body must not be empty")
    return metadata, errors


def check_skills(root: Path) -> list[str]:
    skill_root = root / ".agents/skills"
    if not skill_root.is_dir():
        return [".agents/skills: project skill directory is missing"]
    found = {path.name for path in skill_root.iterdir() if path.is_dir()}
    errors = [
        f".agents/skills: missing required skill {name}"
        for name in sorted(REQUIRED_SKILLS - found)
    ]
    for folder in sorted(path for path in skill_root.iterdir() if path.is_dir()):
        relative = folder.relative_to(root)
        if SKILL_NAME.fullmatch(folder.name) is None:
            errors.append(f"{relative}: skill directory must use lower-case hyphenated name")
        metadata, skill_errors = _skill_frontmatter(folder / "SKILL.md")
        errors.extend(str(error).replace(str(root) + "/", "") for error in skill_errors)
        if metadata.get("name") and metadata["name"] != folder.name:
            errors.append(f"{relative}/SKILL.md: name must match the directory")
        interface = folder / "agents/openai.yaml"
        if not interface.is_file():
            errors.append(f"{relative}/agents/openai.yaml: UI metadata is missing")
            continue
        try:
            interface_text = interface.read_text(encoding="utf-8")
        except OSError as exc:
            errors.append(f"{relative}/agents/openai.yaml: cannot read: {exc}")
            continue
        for field in ("display_name:", "short_description:", "default_prompt:"):
            if field not in interface_text:
                errors.append(f"{relative}/agents/openai.yaml: missing {field[:-1]}")
        if f"${folder.name}" not in interface_text:
            errors.append(
                f"{relative}/agents/openai.yaml: default_prompt must mention ${folder.name}"
            )
    return errors


def check_roles(root: Path) -> list[str]:
    role_root = root / ".agents/roles"
    found = {path.stem for path in role_root.glob("*.md") if path.name != "README.md"}
    return [
        f".agents/roles: missing required role {name}.md"
        for name in sorted(REQUIRED_ROLES - found)
    ]


def check_eval_manifest(root: Path) -> list[str]:
    path = root / "evals/manifest.toml"
    try:
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        return [f"evals/manifest.toml: cannot read: {exc}"]
    if payload.get("version") != 1:
        return ["evals/manifest.toml: version must be 1"]
    evaluations = payload.get("eval")
    if not isinstance(evaluations, list) or not evaluations:
        return ["evals/manifest.toml: at least one [[eval]] entry is required"]

    errors: list[str] = []
    identifiers: set[str] = set()
    covered_areas: set[str] = set()
    for index, evaluation in enumerate(evaluations, start=1):
        if not isinstance(evaluation, dict):
            errors.append(f"evals/manifest.toml: eval {index} must be a table")
            continue
        identifier = evaluation.get("id")
        area = evaluation.get("area")
        tier = evaluation.get("tier")
        command = evaluation.get("command")
        if not isinstance(identifier, str) or not identifier:
            errors.append(f"evals/manifest.toml: eval {index} has invalid id")
        elif identifier in identifiers:
            errors.append(f"evals/manifest.toml: duplicate eval id {identifier}")
        else:
            identifiers.add(identifier)
        if area not in {"architecture", "performance", "prompt", "quality", "ui"}:
            errors.append(f"evals/manifest.toml: eval {identifier!r} has invalid area")
        else:
            covered_areas.add(area)
        if tier not in {"fast", "full", "dependency"}:
            errors.append(f"evals/manifest.toml: eval {identifier!r} has invalid tier")
        if not isinstance(command, list) or not command or not all(
            isinstance(part, str) and part for part in command
        ):
            errors.append(f"evals/manifest.toml: eval {identifier!r} has invalid command")
        environment = evaluation.get("env", {})
        if not isinstance(environment, dict) or not all(
            isinstance(key, str)
            and key
            and isinstance(value, str)
            for key, value in environment.items()
        ):
            errors.append(f"evals/manifest.toml: eval {identifier!r} has invalid env")
        elif (
            isinstance(command, list)
            and all(isinstance(part, str) for part in command)
            and any(part.startswith("tests/integration") for part in command)
            and environment.get("RUN_INTEGRATION_TESTS") != "1"
        ):
            errors.append(f"evals/manifest.toml: eval {identifier!r} must enable integration tests")
        working_directory = evaluation.get("working_directory", ".")
        if not isinstance(working_directory, str):
            errors.append(
                f"evals/manifest.toml: eval {identifier!r} has invalid working_directory"
            )
        elif not (root / working_directory).is_dir():
            errors.append(
                f"evals/manifest.toml: eval {identifier!r} working directory is missing"
            )
    missing_areas = {"architecture", "performance", "prompt", "quality", "ui"} - covered_areas
    if missing_areas:
        errors.append(f"evals/manifest.toml: missing areas {', '.join(sorted(missing_areas))}")
    return errors


def check_harness(root: Path = REPOSITORY_ROOT) -> list[str]:
    root = root.resolve()
    errors = [path for path in sorted(REQUIRED_FILES) if not (root / path).is_file()]
    errors = [f"{path}: required agent-governance file is missing" for path in errors]
    errors.extend(check_roles(root))
    errors.extend(check_skills(root))
    errors.extend(check_eval_manifest(root))
    return sorted(set(errors))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPOSITORY_ROOT)
    return parser.parse_args()


def main() -> int:
    errors = check_harness(_parse_args().root)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("Agent harness checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
