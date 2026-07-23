"""Deterministic architecture checks for the ORNA Atlas Python application."""

from __future__ import annotations

import argparse
import ast
from collections.abc import Iterable
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ROOT = Path("orna_atlas/app")
EXCLUDED_PARTS = {"migrations", "scripts", "tests", "__pycache__"}
LAYER_NAMES = {"models", "schemas", "repository", "service", "router"}
FORBIDDEN_LAYER_IMPORTS = {
    "models": {"schemas", "repository", "service", "router"},
    "schemas": {"repository", "service", "router"},
    "repository": {"service", "router"},
    "service": {"router"},
    "router": set(),
}


def _runtime_files(root: Path) -> list[Path]:
    app_root = root / RUNTIME_ROOT
    if not app_root.is_dir():
        return []
    return [
        path
        for path in sorted(app_root.rglob("*.py"))
        if not EXCLUDED_PARTS.intersection(path.relative_to(app_root).parts)
    ]


def _module_name(root: Path, path: Path) -> str:
    relative = path.relative_to(root).with_suffix("")
    parts = relative.parts[:-1] if relative.name == "__init__" else relative.parts
    return ".".join(parts)


def _import_names(
    tree: ast.Module, importer: str, *, top_level_only: bool = True
) -> Iterable[tuple[str, int]]:
    package = importer.rsplit(".", 1)[0]
    nodes: Iterable[ast.AST] = tree.body if top_level_only else ast.walk(tree)
    for node in nodes:
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, node.lineno
            continue
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.level:
            package_parts = package.split(".")
            keep = len(package_parts) - node.level + 1
            if keep < 0:
                continue
            prefix = ".".join(package_parts[:keep])
            base = ".".join(part for part in (prefix, node.module or "") if part)
        else:
            base = node.module or ""
        if base:
            yield base, node.lineno
        for alias in node.names:
            if alias.name != "*" and base:
                yield f"{base}.{alias.name}", node.lineno


def _load_graph(
    root: Path,
) -> tuple[dict[Path, ast.Module], dict[Path, set[Path]], list[str]]:
    files = _runtime_files(root)
    module_paths = {_module_name(root, path): path for path in files}
    trees: dict[Path, ast.Module] = {}
    graph: dict[Path, set[Path]] = {path: set() for path in files}
    errors: list[str] = []

    for path in files:
        relative = path.relative_to(root)
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(relative))
        except (OSError, SyntaxError) as exc:
            errors.append(f"{relative}: cannot parse Python source: {exc}")
            continue
        trees[path] = tree
        importer = _module_name(root, path)
        for imported, _line in _import_names(tree, importer):
            target = module_paths.get(imported)
            if target is not None and target != path:
                graph[path].add(target)
    return trees, graph, errors


def _display(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def check_repository_transactions(root: Path, trees: dict[Path, ast.Module]) -> list[str]:
    errors: list[str] = []
    for path, tree in trees.items():
        if path.name != "repository.py":
            continue
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "commit"
            ):
                errors.append(
                    f"{_display(root, path)}:{node.lineno}: repositories must not commit; "
                    "the service owns the transaction"
                )
    return errors


def check_layer_imports(
    root: Path,
    trees: dict[Path, ast.Module],
) -> list[str]:
    errors: list[str] = []
    module_paths = {_module_name(root, path): path for path in trees}
    for path, tree in trees.items():
        source_layer = path.stem
        if source_layer not in LAYER_NAMES:
            continue
        forbidden = FORBIDDEN_LAYER_IMPORTS[source_layer]
        importer = _module_name(root, path)
        for imported, line in _import_names(tree, importer, top_level_only=False):
            target = module_paths.get(imported)
            if target is None:
                continue
            target_layer = target.stem
            if target_layer in forbidden:
                errors.append(
                    f"{_display(root, path)}:{line}: {source_layer} must not import "
                    f"{_display(root, target)} ({target_layer} layer)"
                )

    for path, tree in trees.items():
        if path.name != "router.py":
            continue
        importer = _module_name(root, path)
        for imported, line in _import_names(tree, importer, top_level_only=False):
            parts = imported.split(".")
            if len(parts) >= 2 and parts[-1] in {"models", "repository"}:
                errors.append(
                    f"{_display(root, path)}:{line}: routers may import schemas and services, "
                    f"not {parts[-1]} modules ({imported})"
                )
    return errors


def _canonical_cycle(root: Path, paths: list[Path]) -> tuple[str, ...]:
    names = [_display(root, path) for path in paths[:-1]]
    rotations = [tuple(names[index:] + names[:index]) for index in range(len(names))]
    return min(rotations)


def check_import_cycles(root: Path, graph: dict[Path, set[Path]]) -> list[str]:
    state: dict[Path, int] = {}
    stack: list[Path] = []
    cycles: set[tuple[str, ...]] = set()

    def visit(path: Path) -> None:
        state[path] = 1
        stack.append(path)
        for target in sorted(graph[path]):
            if state.get(target, 0) == 0:
                visit(target)
            elif state.get(target) == 1:
                start = stack.index(target)
                cycles.add(_canonical_cycle(root, stack[start:] + [target]))
        stack.pop()
        state[path] = 2

    for path in sorted(graph):
        if state.get(path, 0) == 0:
            visit(path)

    return [f"runtime import cycle: {' -> '.join(cycle + (cycle[0],))}" for cycle in sorted(cycles)]


def check_architecture(root: Path = REPOSITORY_ROOT) -> list[str]:
    root = root.resolve()
    trees, graph, errors = _load_graph(root)
    if not trees and not errors:
        errors.append(f"{RUNTIME_ROOT.as_posix()}: runtime source tree is missing")
        return errors
    errors.extend(check_repository_transactions(root, trees))
    errors.extend(check_layer_imports(root, trees))
    errors.extend(check_import_cycles(root, graph))
    return sorted(set(errors))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPOSITORY_ROOT)
    return parser.parse_args()


def main() -> int:
    errors = check_architecture(_parse_args().root)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("Architecture checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
