"""Build a small, deterministic repository context for a specialist agent.

The routing policy lives in ``.agents/context-map.toml``.  This module intentionally
uses only the Python 3.12 standard library so it can run before project dependencies
are installed.
"""

from __future__ import annotations

import argparse
import fnmatch
import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = Path(".agents/context-map.toml")
EXPECTED_ROLES = frozenset(
    {"architect", "backend", "documentation", "frontend", "security", "test"}
)
HARD_MAX_FILES = 40
HARD_MAX_BYTES = 512 * 1024
MAX_TASK_LENGTH = 4096


class ContextError(ValueError):
    """Raised when context configuration or requested input is unsafe or invalid."""


@dataclass(frozen=True)
class DomainRoute:
    """One configured relevance route."""

    name: str
    keywords: tuple[str, ...]
    path_roots: tuple[str, ...]
    files: tuple[str, ...]
    patterns: tuple[str, ...]


@dataclass(frozen=True)
class ContextMap:
    """Validated context routing configuration."""

    repository_root: Path
    config_path: Path
    max_files: int
    max_bytes: int
    excluded_directories: frozenset[str]
    excluded_names: tuple[str, ...]
    text_extensions: frozenset[str]
    text_names: frozenset[str]
    core_files: tuple[str, ...]
    roles: dict[str, str]
    domains: tuple[DomainRoute, ...]


@dataclass(frozen=True)
class ContextSelection:
    """Selected paths and their aggregate source payload size."""

    files: tuple[str, ...]
    total_bytes: int
    max_files: int
    max_bytes: int


def _expect_table(container: dict[str, Any], key: str, location: str) -> dict[str, Any]:
    value = container.get(key)
    if not isinstance(value, dict):
        raise ContextError(f"{location}.{key} must be a table")
    return value


def _expect_string_list(
    container: dict[str, Any],
    key: str,
    location: str,
    *,
    allow_empty: bool = False,
) -> tuple[str, ...]:
    value = container.get(key)
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ContextError(f"{location}.{key} must be an array of strings")
    if not allow_empty and not value:
        raise ContextError(f"{location}.{key} must not be empty")
    if any(not item.strip() for item in value):
        raise ContextError(f"{location}.{key} contains an empty value")
    if len(value) != len(set(value)):
        raise ContextError(f"{location}.{key} contains duplicate values")
    return tuple(value)


def _expect_positive_int(container: dict[str, Any], key: str, location: str) -> int:
    value = container.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ContextError(f"{location}.{key} must be a positive integer")
    return value


def _reject_unknown_keys(
    table: dict[str, Any], allowed: set[str], location: str
) -> None:
    unknown = sorted(set(table) - allowed)
    if unknown:
        raise ContextError(f"{location} contains unknown keys: {', '.join(unknown)}")


def _relative_syntax(raw: str, *, location: str, allow_glob: bool = False) -> str:
    if not raw or "\x00" in raw or "\\" in raw:
        raise ContextError(f"{location} is not a safe repository-relative path")
    path = PurePosixPath(raw)
    if path.is_absolute() or ".." in path.parts:
        raise ContextError(f"{location} must stay inside the repository")
    if path == PurePosixPath("."):
        raise ContextError(f"{location} must not select the repository root")
    if not allow_glob and any(character in raw for character in "*?[]"):
        raise ContextError(f"{location} must not contain glob characters")
    return path.as_posix()


def _is_inside(repository_root: Path, candidate: Path) -> bool:
    return candidate == repository_root or repository_root in candidate.parents


def _reject_symlink_path(
    candidate: Path, resolved: Path, relative_path: str, *, location: str
) -> None:
    if candidate != resolved:
        raise ContextError(
            f"{location} must not traverse symlinks: {relative_path}"
        )


def _is_excluded(relative_path: str, mapping: ContextMap) -> bool:
    path = PurePosixPath(relative_path)
    lowered_parts = {part.casefold() for part in path.parts}
    if lowered_parts & mapping.excluded_directories:
        return True
    name = path.name.casefold()
    return any(fnmatch.fnmatchcase(name, pattern.casefold()) for pattern in mapping.excluded_names)


def _resolve_config_path(repository_root: Path, config_path: Path | None) -> Path:
    requested = config_path or DEFAULT_CONFIG_PATH
    candidate = requested if requested.is_absolute() else repository_root / requested
    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ContextError(f"context map does not exist: {candidate}") from exc
    if not resolved.is_file() or not _is_inside(repository_root, resolved):
        raise ContextError("context map must be a file inside the repository")
    return resolved


def _resolve_file(relative_path: str, mapping: ContextMap, *, location: str) -> Path:
    safe_path = _relative_syntax(relative_path, location=location)
    if _is_excluded(safe_path, mapping):
        raise ContextError(f"{location} points to an excluded path: {safe_path}")
    candidate = mapping.repository_root / PurePosixPath(safe_path)
    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ContextError(f"{location} does not exist: {safe_path}") from exc
    _reject_symlink_path(candidate, resolved, safe_path, location=location)
    if not resolved.is_file() or not _is_inside(mapping.repository_root, resolved):
        raise ContextError(f"{location} must be a file inside the repository: {safe_path}")
    _read_text_payload(resolved, safe_path, mapping, location=location)
    return resolved


def _read_text_payload(
    resolved: Path,
    relative_path: str,
    mapping: ContextMap,
    *,
    location: str,
) -> bytes:
    logical = PurePosixPath(relative_path)
    suffix = logical.suffix.casefold()
    if logical.name not in mapping.text_names and suffix not in mapping.text_extensions:
        raise ContextError(f"{location} is not an allowlisted text file: {relative_path}")
    try:
        payload = resolved.read_bytes()
    except OSError as exc:
        raise ContextError(f"cannot read {location}: {relative_path}") from exc
    if b"\x00" in payload:
        raise ContextError(f"{location} appears to be binary: {relative_path}")
    try:
        payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ContextError(f"{location} is not UTF-8 text: {relative_path}") from exc
    return payload


def _expand_pattern(pattern: str, mapping: ContextMap, *, location: str) -> tuple[str, ...]:
    safe_pattern = _relative_syntax(pattern, location=location, allow_glob=True)
    if _is_excluded(safe_pattern, mapping):
        raise ContextError(f"{location} points into an excluded path: {safe_pattern}")
    try:
        matches = sorted(mapping.repository_root.glob(safe_pattern), key=lambda item: item.as_posix())
    except (OSError, ValueError) as exc:
        raise ContextError(f"{location} is not a valid glob: {safe_pattern}") from exc

    relative_matches: list[str] = []
    for match in matches:
        relative = match.relative_to(mapping.repository_root).as_posix()
        try:
            resolved = match.resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise ContextError(f"{location} contains an unreadable match: {match}") from exc
        if not resolved.is_file():
            continue
        if not _is_inside(mapping.repository_root, resolved):
            raise ContextError(f"{location} resolves outside the repository: {match}")
        _reject_symlink_path(match, resolved, relative, location=location)
        if _is_excluded(relative, mapping):
            raise ContextError(f"{location} matches an excluded path: {relative}")
        _read_text_payload(resolved, relative, mapping, location=location)
        relative_matches.append(relative)

    if not relative_matches:
        raise ContextError(f"{location} does not match any text files: {safe_pattern}")
    return tuple(relative_matches)


def _validate_configured_paths(mapping: ContextMap) -> None:
    for index, relative_path in enumerate(mapping.core_files):
        _resolve_file(relative_path, mapping, location=f"core.files[{index}]")
    for role, relative_path in sorted(mapping.roles.items()):
        _resolve_file(relative_path, mapping, location=f"roles.{role}.contract")
    for domain_index, domain in enumerate(mapping.domains):
        prefix = f"domains[{domain_index}]"
        for index, relative_path in enumerate(domain.files):
            _resolve_file(relative_path, mapping, location=f"{prefix}.files[{index}]")
        for index, pattern in enumerate(domain.patterns):
            _expand_pattern(pattern, mapping, location=f"{prefix}.patterns[{index}]")


def load_context_map(
    repository_root: Path = REPOSITORY_ROOT,
    config_path: Path | None = None,
) -> ContextMap:
    """Load and fully validate the routing map, failing closed on any drift."""

    try:
        root = repository_root.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ContextError(f"repository root does not exist: {repository_root}") from exc
    if not root.is_dir():
        raise ContextError(f"repository root is not a directory: {root}")

    resolved_config = _resolve_config_path(root, config_path)
    try:
        raw = tomllib.loads(resolved_config.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise ContextError(f"cannot parse context map: {resolved_config}") from exc
    if not isinstance(raw, dict):
        raise ContextError("context map root must be a table")
    _reject_unknown_keys(raw, {"version", "defaults", "core", "roles", "domains"}, "root")
    if raw.get("version") != 1:
        raise ContextError("context map version must be 1")

    defaults = _expect_table(raw, "defaults", "root")
    _reject_unknown_keys(
        defaults,
        {
            "excluded_directories",
            "excluded_names",
            "max_bytes",
            "max_files",
            "text_extensions",
            "text_names",
        },
        "defaults",
    )
    max_files = _expect_positive_int(defaults, "max_files", "defaults")
    max_bytes = _expect_positive_int(defaults, "max_bytes", "defaults")
    if max_files > HARD_MAX_FILES or max_bytes > HARD_MAX_BYTES:
        raise ContextError("configured defaults exceed the hard context budget")
    excluded_directories = _expect_string_list(
        defaults, "excluded_directories", "defaults"
    )
    excluded_names = _expect_string_list(defaults, "excluded_names", "defaults")
    text_extensions = _expect_string_list(defaults, "text_extensions", "defaults")
    text_names = _expect_string_list(defaults, "text_names", "defaults")
    if any("/" in item or "\\" in item for item in excluded_directories):
        raise ContextError("defaults.excluded_directories entries must be directory names")
    if any(not item.startswith(".") for item in text_extensions):
        raise ContextError("defaults.text_extensions entries must start with a dot")

    core = _expect_table(raw, "core", "root")
    _reject_unknown_keys(core, {"files"}, "core")
    core_files = tuple(
        _relative_syntax(path, location=f"core.files[{index}]")
        for index, path in enumerate(_expect_string_list(core, "files", "core"))
    )

    roles_table = _expect_table(raw, "roles", "root")
    if set(roles_table) != EXPECTED_ROLES:
        missing = sorted(EXPECTED_ROLES - set(roles_table))
        extra = sorted(set(roles_table) - EXPECTED_ROLES)
        details = []
        if missing:
            details.append(f"missing: {', '.join(missing)}")
        if extra:
            details.append(f"unknown: {', '.join(extra)}")
        raise ContextError(f"roles must be the canonical specialist set ({'; '.join(details)})")
    roles: dict[str, str] = {}
    for role, role_config in sorted(roles_table.items()):
        if not isinstance(role_config, dict):
            raise ContextError(f"roles.{role} must be a table")
        _reject_unknown_keys(role_config, {"contract"}, f"roles.{role}")
        contract = role_config.get("contract")
        if not isinstance(contract, str):
            raise ContextError(f"roles.{role}.contract must be a string")
        roles[role] = _relative_syntax(contract, location=f"roles.{role}.contract")

    raw_domains = raw.get("domains")
    if not isinstance(raw_domains, list) or not raw_domains:
        raise ContextError("domains must be a non-empty array of tables")
    domains: list[DomainRoute] = []
    domain_names: set[str] = set()
    for index, domain_config in enumerate(raw_domains):
        location = f"domains[{index}]"
        if not isinstance(domain_config, dict):
            raise ContextError(f"{location} must be a table")
        _reject_unknown_keys(
            domain_config,
            {"files", "keywords", "name", "path_roots", "patterns"},
            location,
        )
        name = domain_config.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ContextError(f"{location}.name must be a non-empty string")
        if name in domain_names:
            raise ContextError(f"duplicate domain name: {name}")
        domain_names.add(name)
        keywords = _expect_string_list(domain_config, "keywords", location)
        path_roots = tuple(
            _relative_syntax(path, location=f"{location}.path_roots[{path_index}]")
            for path_index, path in enumerate(
                _expect_string_list(domain_config, "path_roots", location)
            )
        )
        files = tuple(
            _relative_syntax(path, location=f"{location}.files[{path_index}]")
            for path_index, path in enumerate(
                _expect_string_list(domain_config, "files", location, allow_empty=True)
            )
        )
        patterns = tuple(
            _relative_syntax(
                pattern,
                location=f"{location}.patterns[{pattern_index}]",
                allow_glob=True,
            )
            for pattern_index, pattern in enumerate(
                _expect_string_list(domain_config, "patterns", location, allow_empty=True)
            )
        )
        if not files and not patterns:
            raise ContextError(f"{location} must configure files or patterns")
        domains.append(
            DomainRoute(
                name=name,
                keywords=tuple(keyword.casefold() for keyword in keywords),
                path_roots=path_roots,
                files=files,
                patterns=patterns,
            )
        )

    mapping = ContextMap(
        repository_root=root,
        config_path=resolved_config,
        max_files=max_files,
        max_bytes=max_bytes,
        excluded_directories=frozenset(item.casefold() for item in excluded_directories),
        excluded_names=excluded_names,
        text_extensions=frozenset(item.casefold() for item in text_extensions),
        text_names=frozenset(text_names),
        core_files=core_files,
        roles=roles,
        domains=tuple(domains),
    )
    _validate_configured_paths(mapping)
    return mapping


def _normalize_requested_path(raw: str, mapping: ContextMap, *, location: str) -> tuple[str, bool]:
    relative = _relative_syntax(raw, location=location)
    if _is_excluded(relative, mapping):
        raise ContextError(f"{location} points to an excluded path: {relative}")
    candidate = mapping.repository_root / PurePosixPath(relative)
    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ContextError(f"{location} does not exist: {relative}") from exc
    _reject_symlink_path(candidate, resolved, relative, location=location)
    if not _is_inside(mapping.repository_root, resolved) or resolved == mapping.repository_root:
        raise ContextError(f"{location} must stay inside the repository")
    if not (resolved.is_file() or resolved.is_dir()):
        raise ContextError(f"{location} must name a file or directory: {relative}")
    if resolved.is_file():
        _read_text_payload(resolved, relative, mapping, location=location)
    return relative, resolved.is_file()


def _path_matches_root(path: str, root: str) -> bool:
    return path == root or path.startswith(f"{root.rstrip('/')}/")


def _keyword_matches(keyword: str, normalized_task: str) -> bool:
    if keyword.isascii() and len(keyword) <= 3:
        boundary = rf"(?<![a-z0-9_]){re.escape(keyword)}(?![a-z0-9_])"
        return re.search(boundary, normalized_task, flags=re.ASCII) is not None
    return keyword in normalized_task


def _rank_domains(
    task: str,
    requested_paths: Sequence[str],
    domains: Sequence[DomainRoute],
) -> tuple[DomainRoute, ...]:
    normalized_task = " ".join(task.casefold().split())
    ranked: list[tuple[int, int, DomainRoute]] = []
    for index, domain in enumerate(domains):
        keyword_score = sum(
            _keyword_matches(keyword, normalized_task) for keyword in domain.keywords
        )
        path_score = sum(
            4
            for path in requested_paths
            for root in domain.path_roots
            if _path_matches_root(path, root)
        )
        score = keyword_score + path_score
        if score:
            ranked.append((-score, index, domain))
    ranked.sort(key=lambda item: (item[0], item[1]))
    return tuple(item[2] for item in ranked)


def _deduplicate(paths: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for path in paths:
        if path not in seen:
            seen.add(path)
            result.append(path)
    return tuple(result)


def build_context(
    mapping: ContextMap,
    *,
    task: str,
    role: str,
    changed_paths: Sequence[str] = (),
    target_paths: Sequence[str] = (),
    max_files: int | None = None,
    max_bytes: int | None = None,
) -> ContextSelection:
    """Select relevant files in stable priority order and enforce both budgets."""

    normalized_task = " ".join(task.split())
    if not normalized_task:
        raise ContextError("task text must not be empty")
    if len(normalized_task) > MAX_TASK_LENGTH or "\x00" in normalized_task:
        raise ContextError(f"task text must be at most {MAX_TASK_LENGTH} safe characters")
    if role not in mapping.roles:
        available = ", ".join(sorted(mapping.roles))
        raise ContextError(f"unknown specialist role {role!r}; choose one of: {available}")

    selected_max_files = mapping.max_files if max_files is None else max_files
    selected_max_bytes = mapping.max_bytes if max_bytes is None else max_bytes
    if (
        isinstance(selected_max_files, bool)
        or not isinstance(selected_max_files, int)
        or selected_max_files <= 0
        or selected_max_files > HARD_MAX_FILES
    ):
        raise ContextError(f"max-files must be between 1 and {HARD_MAX_FILES}")
    if (
        isinstance(selected_max_bytes, bool)
        or not isinstance(selected_max_bytes, int)
        or selected_max_bytes <= 0
        or selected_max_bytes > HARD_MAX_BYTES
    ):
        raise ContextError(f"max-bytes must be between 1 and {HARD_MAX_BYTES}")

    normalized_requests: list[tuple[str, bool]] = []
    raw_requests = list(changed_paths) + list(target_paths)
    for index, raw_path in enumerate(raw_requests):
        normalized_requests.append(
            _normalize_requested_path(
                raw_path,
                mapping,
                location=f"requested_paths[{index}]",
            )
        )
    normalized_requests.sort(key=lambda item: item[0])
    requested_paths = tuple(path for path, _is_file in normalized_requests)
    explicit_files = tuple(path for path, is_file in normalized_requests if is_file)

    ranked_domains = _rank_domains(normalized_task, requested_paths, mapping.domains)
    mandatory = _deduplicate((*mapping.core_files, mapping.roles[role]))
    candidates: list[str] = [*mandatory]
    for domain in ranked_domains:
        candidates.extend(domain.files)
    candidates.extend(explicit_files)
    for domain in ranked_domains:
        for pattern_index, pattern in enumerate(domain.patterns):
            candidates.extend(
                _expand_pattern(
                    pattern,
                    mapping,
                    location=f"domain.{domain.name}.patterns[{pattern_index}]",
                )
            )
    candidates = list(_deduplicate(candidates))

    selected: list[str] = []
    total_bytes = 0
    mandatory_set = set(mandatory)
    for relative_path in candidates:
        resolved = _resolve_file(relative_path, mapping, location="context candidate")
        payload_size = resolved.stat().st_size
        exceeds_files = len(selected) + 1 > selected_max_files
        exceeds_bytes = total_bytes + payload_size > selected_max_bytes
        if exceeds_files or exceeds_bytes:
            if relative_path in mandatory_set:
                raise ContextError(
                    "context budget cannot include core files and the selected role contract"
                )
            continue
        selected.append(relative_path)
        total_bytes += payload_size

    if not mandatory_set.issubset(selected):
        raise ContextError("context selection omitted a mandatory file")
    return ContextSelection(
        files=tuple(selected),
        total_bytes=total_bytes,
        max_files=selected_max_files,
        max_bytes=selected_max_bytes,
    )


def render_manifest(selection: ContextSelection) -> str:
    """Render one repository-relative path per line."""

    return "".join(f"{path}\n" for path in selection.files)


def _language_for(path: str) -> str:
    logical = PurePosixPath(path)
    languages = {
        ".cjs": "javascript",
        ".css": "css",
        ".html": "html",
        ".ini": "ini",
        ".js": "javascript",
        ".json": "json",
        ".md": "markdown",
        ".mjs": "javascript",
        ".py": "python",
        ".sql": "sql",
        ".toml": "toml",
        ".ts": "typescript",
        ".tsx": "tsx",
        ".yaml": "yaml",
        ".yml": "yaml",
    }
    return languages.get(logical.suffix.casefold(), "text")


def _safe_fence(content: str) -> str:
    longest = 0
    current = 0
    for character in content:
        if character == "`":
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return "`" * max(3, longest + 1)


def render_markdown(
    mapping: ContextMap,
    selection: ContextSelection,
    *,
    task: str,
    role: str,
) -> str:
    """Render selected UTF-8 files as a single Markdown context bundle."""

    normalized_task = " ".join(task.split())
    sections = [
        "# ORNA Atlas agent context",
        "",
        f"- Task: {normalized_task}",
        f"- Specialist role: `{role}`",
        f"- Source payload: {selection.total_bytes} / {selection.max_bytes} bytes",
        f"- Files: {len(selection.files)} / {selection.max_files}",
    ]
    for relative_path in selection.files:
        resolved = _resolve_file(relative_path, mapping, location="context bundle")
        content = resolved.read_text(encoding="utf-8")
        fence = _safe_fence(content)
        sections.extend(
            [
                "",
                f"## `{relative_path}`",
                "",
                f"{fence}{_language_for(relative_path)}",
                content.rstrip("\n"),
                fence,
            ]
        )
    return "\n".join(sections) + "\n"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Assemble deterministic, budgeted context for an ORNA specialist agent."
    )
    parser.add_argument("task", nargs="?", help="task text (or use --task)")
    parser.add_argument("--task", dest="task_option", help="task text")
    parser.add_argument("--role", "--specialist-role", dest="role")
    parser.add_argument(
        "--changed-path",
        "--changed",
        dest="changed_paths",
        action="append",
        default=[],
        help="changed repository-relative file or directory; repeatable",
    )
    parser.add_argument(
        "--target-path",
        "--target",
        dest="target_paths",
        action="append",
        default=[],
        help="target repository-relative file or directory; repeatable",
    )
    parser.add_argument("--max-files", type=int)
    parser.add_argument("--max-bytes", type=int)
    output_group = parser.add_mutually_exclusive_group()
    output_group.add_argument(
        "--format", choices=("manifest", "markdown"), default="manifest"
    )
    output_group.add_argument(
        "--bundle",
        "--markdown",
        dest="format",
        action="store_const",
        const="markdown",
        help="emit a Markdown bundle instead of a path manifest",
    )
    parser.add_argument(
        "--check", action="store_true", help="validate the mapping without building context"
    )
    parser.add_argument("--repo-root", type=Path, default=REPOSITORY_ROOT)
    parser.add_argument("--config", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        mapping = load_context_map(args.repo_root, args.config)
        if args.check:
            print(
                f"context map OK: {len(mapping.roles)} roles, "
                f"{len(mapping.domains)} domains"
            )
            return 0
        if args.task and args.task_option:
            raise ContextError("provide task text either positionally or with --task, not both")
        task = args.task_option or args.task
        if task is None:
            raise ContextError("task text is required unless --check is used")
        if args.role is None:
            raise ContextError("--role is required unless --check is used")
        selection = build_context(
            mapping,
            task=task,
            role=args.role,
            changed_paths=args.changed_paths,
            target_paths=args.target_paths,
            max_files=args.max_files,
            max_bytes=args.max_bytes,
        )
        if args.format == "markdown":
            sys.stdout.write(render_markdown(mapping, selection, task=task, role=args.role))
        else:
            sys.stdout.write(render_manifest(selection))
        return 0
    except ContextError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
