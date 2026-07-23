"""Require a new ADR when a change touches durable architecture surfaces."""

from __future__ import annotations

import argparse
import fnmatch
import re
import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = Path("evals/architecture/adr-policy.toml")
ADR_INDEX_PATH = "docs/adr/README.md"
ADR_PATH = re.compile(r"^docs/adr/(?P<number>\d{4})-[a-z0-9][a-z0-9-]*\.md$")
ADR_STATUS = re.compile(r"^- Status: (accepted|proposed|superseded|rejected)$", re.MULTILINE)
ADR_INDEX_LINK = re.compile(
    r"^ {0,3}-[ \t]+\[[^\]\n]+\]\([ \t]*(?:\./)?"
    r"(?P<filename>\d{4}-[a-z0-9][a-z0-9-]*\.md)"
    r"(?:#[^)\s]*)?(?:[ \t]+(?:\"[^\"]*\"|'[^']*'))?[ \t]*\)[ \t]*$",
    re.MULTILINE,
)
HTML_COMMENT = re.compile(r"<!--.*?(?:-->|\Z)", re.DOTALL)
FENCE_OPEN = re.compile(r"^ {0,3}(?P<fence>`{3,}|~{3,})")


@dataclass(frozen=True)
class Change:
    status: str
    path: str


@dataclass(frozen=True)
class Policy:
    protected_patterns: tuple[str, ...]


def load_policy(root: Path, path: Path = DEFAULT_POLICY) -> Policy:
    target = path if path.is_absolute() else root / path
    try:
        payload = tomllib.loads(target.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ValueError(f"cannot read ADR policy {target}: {exc}") from exc
    if payload.get("version") != 1:
        raise ValueError("ADR policy version must be 1")
    patterns = payload.get("protected_patterns")
    if not isinstance(patterns, list) or not patterns or not all(
        isinstance(pattern, str) and pattern for pattern in patterns
    ):
        raise ValueError("ADR policy protected_patterns must be a non-empty string list")
    return Policy(tuple(patterns))


def _run_git(root: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if check and result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise ValueError(f"git {' '.join(args)} failed: {detail}")
    return result.stdout


def _usable_base(root: Path, base_ref: str) -> str | None:
    if not base_ref or set(base_ref) == {"0"}:
        return None
    result = subprocess.run(
        ["git", "rev-parse", "--verify", f"{base_ref}^{{commit}}"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    return base_ref if result.returncode == 0 else None


def _parse_name_status(output: str) -> list[Change]:
    changes: list[Change] = []
    for line in output.splitlines():
        fields = line.split("\t")
        if len(fields) < 2:
            continue
        raw_status = fields[0]
        status = raw_status[0]
        if status == "R" and len(fields) >= 3:
            source_path = fields[-2].replace("\\", "/")
            changes.append(Change("D", source_path))
        path = fields[-1].replace("\\", "/")
        changes.append(Change(status, path))
    return changes


def changed_files(root: Path, base_ref: str | None) -> list[Change]:
    if base_ref and set(base_ref) == {"0"}:
        base_ref = "HEAD^"
        if _usable_base(root, base_ref) is None:
            return []

    if base_ref:
        base = _usable_base(root, base_ref)
        if base is None:
            raise ValueError(f"base ref is not available: {base_ref}")
        return _parse_name_status(
            _run_git(root, "diff", "--name-status", "--find-renames", f"{base}...HEAD")
        )

    tracked = _parse_name_status(
        _run_git(root, "diff", "--name-status", "--find-renames", "HEAD")
    )
    untracked = [
        Change("A", line)
        for line in _run_git(root, "ls-files", "--others", "--exclude-standard").splitlines()
        if line
    ]
    return sorted({*tracked, *untracked}, key=lambda change: (change.path, change.status))


def _is_protected(path: str, policy: Policy) -> bool:
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in policy.protected_patterns)


def _validate_new_adr(root: Path, change: Change) -> list[str]:
    errors: list[str] = []
    match = ADR_PATH.fullmatch(change.path)
    if match is None:
        return errors
    target = (root / change.path).resolve()
    try:
        target.relative_to(root.resolve())
        text = target.read_text(encoding="utf-8")
    except (OSError, ValueError) as exc:
        return [f"{change.path}: cannot read new ADR: {exc}"]
    expected_title = f"# ADR-{match.group('number')}:"
    if not text.startswith(expected_title):
        errors.append(f"{change.path}: title must start with {expected_title}")
    if ADR_STATUS.search(text) is None:
        errors.append(f"{change.path}: missing a supported '- Status:' line")
    if "- Date: " not in text:
        errors.append(f"{change.path}: missing '- Date:'")
    if "## Decision" not in text:
        errors.append(f"{change.path}: missing '## Decision'")
    if "## Consequences" not in text and "## Rationale and consequences" not in text:
        errors.append(f"{change.path}: missing consequences section")
    return errors


def _strip_non_rendered_markdown(text: str) -> str:
    without_comments = HTML_COMMENT.sub("", text)
    visible_lines: list[str] = []
    fence_character: str | None = None
    fence_length = 0
    for line in without_comments.splitlines():
        if fence_character is not None:
            closing = line.lstrip(" ")
            indentation = len(line) - len(closing)
            if indentation <= 3 and re.fullmatch(
                rf"{re.escape(fence_character)}{{{fence_length},}}[ \t]*",
                closing,
            ):
                fence_character = None
                fence_length = 0
            continue

        opening = FENCE_OPEN.match(line)
        if opening is not None:
            fence = opening.group("fence")
            fence_character = fence[0]
            fence_length = len(fence)
            continue
        visible_lines.append(line)
    return "\n".join(visible_lines)


def _validate_adr_index(root: Path, new_adrs: list[Change]) -> list[str]:
    target = (root / ADR_INDEX_PATH).resolve()
    try:
        target.relative_to(root.resolve())
        text = target.read_text(encoding="utf-8")
    except (OSError, ValueError) as exc:
        return [f"{ADR_INDEX_PATH}: cannot read ADR index: {exc}"]

    visible_text = _strip_non_rendered_markdown(text)
    linked_adrs = {
        match.group("filename") for match in ADR_INDEX_LINK.finditer(visible_text)
    }
    errors: list[str] = []
    for change in new_adrs:
        filename = Path(change.path).name
        if filename not in linked_adrs:
            errors.append(f"{ADR_INDEX_PATH}: must link to {filename}")
    return errors


def evaluate_changes(root: Path, changes: list[Change], policy: Policy) -> list[str]:
    architecture_changes = [
        change.path for change in changes if _is_protected(change.path, policy)
    ]
    new_adrs = [
        change for change in changes if change.status == "A" and ADR_PATH.fullmatch(change.path)
    ]
    modified_adrs = [
        change.path
        for change in changes
        if change.status != "A" and ADR_PATH.fullmatch(change.path)
    ]
    errors: list[str] = []
    requires_new_adr = bool(architecture_changes or modified_adrs)
    if requires_new_adr and not new_adrs:
        surfaces = ", ".join(sorted({*architecture_changes, *modified_adrs}))
        errors.append(
            "durable architecture changed without a new ADR: "
            f"{surfaces}; add docs/adr/NNNN-short-title.md"
        )
    if new_adrs:
        index_updated = any(
            change.path == ADR_INDEX_PATH and change.status != "D" for change in changes
        )
        if not index_updated:
            errors.append(f"new ADR added without updating {ADR_INDEX_PATH}")
        else:
            errors.extend(_validate_adr_index(root, new_adrs))
    for change in new_adrs:
        errors.extend(_validate_new_adr(root, change))
    return errors


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPOSITORY_ROOT)
    parser.add_argument("--base-ref")
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    root = args.root.resolve()
    try:
        policy = load_policy(root, args.policy)
        changes = changed_files(root, args.base_ref)
        errors = evaluate_changes(root, changes, policy)
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 2
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("ADR policy check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
