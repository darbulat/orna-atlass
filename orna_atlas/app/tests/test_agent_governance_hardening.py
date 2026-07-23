from dataclasses import replace
from pathlib import Path

import pytest

from scripts import build_agent_context as context_builder
from scripts.check_adr_policy import (
    Change,
    Policy,
    _parse_name_status,
    evaluate_changes,
)
from scripts.check_architecture import check_architecture
from scripts.run_agent_evals import load_evaluations, merge_environment


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def _write(root: Path, relative: str, content: str) -> None:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


@pytest.fixture(scope="module")
def context_map() -> context_builder.ContextMap:
    return context_builder.load_context_map(REPOSITORY_ROOT)


def test_context_builder_rejects_symlinks_on_every_file_path(
    context_map: context_builder.ContextMap,
    tmp_path: Path,
) -> None:
    for relative_path in ("AGENTS.md", "CURRENT.md", "security-role.md"):
        _write(tmp_path, relative_path, "safe context\n")
    _write(tmp_path, ".env", "not-a-real-secret\n")
    (tmp_path / "safe.py").symlink_to(".env")

    base_map = replace(
        context_map,
        repository_root=tmp_path,
        core_files=("AGENTS.md", "CURRENT.md"),
        roles={"security": "security-role.md"},
        domains=(),
    )
    with pytest.raises(context_builder.ContextError, match="symlink"):
        context_builder.build_context(
            base_map,
            task="Inspect an explicit file",
            role="security",
            target_paths=("safe.py",),
        )

    core_map = replace(base_map, core_files=("safe.py", "CURRENT.md"))
    with pytest.raises(context_builder.ContextError, match="symlink"):
        context_builder.build_context(
            core_map,
            task="Inspect mandatory context",
            role="security",
        )

    pattern_map = replace(
        base_map,
        domains=(
            context_builder.DomainRoute(
                name="symlink-pattern",
                keywords=("symlink",),
                path_roots=(),
                files=(),
                patterns=("safe*.py",),
            ),
        ),
    )
    with pytest.raises(context_builder.ContextError, match="symlink"):
        context_builder.build_context(
            pattern_map,
            task="Inspect a symlink pattern",
            role="security",
        )


def test_large_diff_keeps_domain_rules_ahead_of_source_files(
    context_map: context_builder.ContextMap,
) -> None:
    changed_paths = (
        "orna_atlas/app/modules/atlas/__init__.py",
        "orna_atlas/app/modules/atlas/repository.py",
        "orna_atlas/app/modules/atlas/router.py",
        "orna_atlas/app/modules/atlas/schemas.py",
        "orna_atlas/app/modules/atlas/service.py",
        "orna_atlas/app/modules/locations/__init__.py",
        "orna_atlas/app/modules/locations/models.py",
        "orna_atlas/app/modules/locations/public.py",
        "orna_atlas/app/modules/locations/repository.py",
        "orna_atlas/app/modules/locations/router.py",
        "orna_atlas/app/modules/locations/schemas.py",
    )

    selection = context_builder.build_context(
        context_map,
        task="Fix the public privacy coordinate projection",
        role="backend",
        changed_paths=changed_paths,
        max_files=14,
        max_bytes=context_builder.HARD_MAX_BYTES,
    )

    assert selection.files[3:5] == (
        "docs/DOMAIN_RULES.md",
        "docs/adr/0001-public-coordinate-projection.md",
    )
    assert not set(changed_paths).issubset(selection.files)


def test_adr_policy_requires_record_for_protected_deletion(tmp_path: Path) -> None:
    errors = evaluate_changes(
        tmp_path,
        [Change("D", "AGENTS.md")],
        Policy(("AGENTS.md",)),
    )

    assert errors and "without a new ADR" in errors[0]


def test_adr_policy_requires_record_for_accepted_adr_deletion(tmp_path: Path) -> None:
    errors = evaluate_changes(
        tmp_path,
        [Change("D", "docs/adr/0004-service-owned-transactions.md")],
        Policy(("AGENTS.md",)),
    )

    assert errors and "without a new ADR" in errors[0]


def test_adr_policy_checks_old_path_of_rename(tmp_path: Path) -> None:
    changes = _parse_name_status("R100\tAGENTS.md\tdocs/legacy-agent-guide.md\n")

    assert changes == [
        Change("D", "AGENTS.md"),
        Change("R", "docs/legacy-agent-guide.md"),
    ]
    errors = evaluate_changes(tmp_path, changes, Policy(("AGENTS.md",)))
    assert errors and "without a new ADR" in errors[0]


def test_architecture_check_rejects_local_router_repository_import(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "orna_atlas/app/modules/example/router.py",
        """async def handler():
    from orna_atlas.app.modules.example import repository

    return repository.find()
""",
    )
    _write(
        tmp_path,
        "orna_atlas/app/modules/example/repository.py",
        "def find():\n    return None\n",
    )

    errors = check_architecture(tmp_path)

    assert any("routers may import schemas and services" in error for error in errors)


def test_postgis_eval_cannot_silently_skip_integration_tests() -> None:
    evaluations = load_evaluations(REPOSITORY_ROOT)
    postgis = next(evaluation for evaluation in evaluations if evaluation["id"] == "postgis-scale")

    assert postgis["env"] == {"RUN_INTEGRATION_TESTS": "1"}
    base = {"PYTHONPATH": "/repo", "KEEP": "yes"}
    merged = merge_environment(base, postgis["env"])
    assert merged == {
        "PYTHONPATH": "/repo",
        "KEEP": "yes",
        "RUN_INTEGRATION_TESTS": "1",
    }
    assert base == {"PYTHONPATH": "/repo", "KEEP": "yes"}
