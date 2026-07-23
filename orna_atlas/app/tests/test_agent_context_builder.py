from dataclasses import replace
from pathlib import Path

import pytest

from scripts import build_agent_context as context_builder


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def context_map() -> context_builder.ContextMap:
    return context_builder.load_context_map(REPOSITORY_ROOT)


def test_routes_task_and_target_path_to_privacy_context(
    context_map: context_builder.ContextMap,
) -> None:
    selection = context_builder.build_context(
        context_map,
        task="Fix hidden coordinate projection in the public atlas",
        role="backend",
        target_paths=("orna_atlas/app/modules/locations/public.py",),
        max_files=8,
        max_bytes=90_000,
    )

    assert selection.files[:3] == (
        "AGENTS.md",
        "docs/CURRENT_STATE.md",
        ".agents/roles/backend.md",
    )
    assert "orna_atlas/app/modules/locations/public.py" in selection.files
    assert "docs/DOMAIN_RULES.md" in selection.files
    assert "docs/adr/0001-public-coordinate-projection.md" in selection.files
    assert "docs/adr/0005-segmented-hls-playback.md" not in selection.files
    assert len(selection.files) <= selection.max_files
    assert selection.total_bytes <= selection.max_bytes


@pytest.mark.parametrize(
    ("frontend_path", "backend_context"),
    [
        ("web/lib/api/auth.ts", "orna_atlas/app/modules/auth/service.py"),
        ("web/lib/api/library.ts", "orna_atlas/app/modules/library/service.py"),
    ],
)
def test_frontend_auth_and_library_files_route_to_responsible_backend_context(
    context_map: context_builder.ContextMap,
    frontend_path: str,
    backend_context: str,
) -> None:
    selection = context_builder.build_context(
        context_map,
        task="Fix frontend client bug",
        role="frontend",
        changed_paths=(frontend_path,),
    )
    manifest = context_builder.render_manifest(selection).splitlines()

    assert frontend_path in manifest
    assert "docs/DOMAIN_RULES.md" in manifest
    assert backend_context in manifest
    assert len(manifest) <= context_map.max_files
    assert selection.total_bytes <= context_map.max_bytes


@pytest.mark.parametrize(
    "role",
    ["architect", "backend", "documentation", "frontend", "security", "test"],
)
def test_selects_exact_specialist_role_contract(
    context_map: context_builder.ContextMap,
    role: str,
) -> None:
    selection = context_builder.build_context(
        context_map,
        task="Make a small focused change",
        role=role,
    )

    assert selection.files == (
        "AGENTS.md",
        "docs/CURRENT_STATE.md",
        f".agents/roles/{role}.md",
    )


@pytest.mark.parametrize(
    ("unsafe_path", "message"),
    [
        ("../AGENTS.md", "inside the repository"),
        ("/etc/passwd", "inside the repository"),
        (".env", "excluded path"),
        ("web/node_modules", "excluded path"),
    ],
)
def test_rejects_traversal_secrets_and_build_directories(
    context_map: context_builder.ContextMap,
    unsafe_path: str,
    message: str,
) -> None:
    with pytest.raises(context_builder.ContextError, match=message):
        context_builder.build_context(
            context_map,
            task="Inspect a target",
            role="security",
            target_paths=(unsafe_path,),
        )


def test_order_and_truncation_are_deterministic(
    context_map: context_builder.ContextMap,
) -> None:
    paths = (
        "orna_atlas/app/modules/sessions/service.py",
        "orna_atlas/app/modules/sessions/router.py",
    )
    first = context_builder.build_context(
        context_map,
        task="Make a small focused change",
        role="backend",
        changed_paths=paths,
        max_files=5,
        max_bytes=context_builder.HARD_MAX_BYTES,
    )
    second = context_builder.build_context(
        context_map,
        task="Make a small focused change",
        role="backend",
        changed_paths=tuple(reversed(paths)),
        max_files=5,
        max_bytes=context_builder.HARD_MAX_BYTES,
    )

    assert first == second
    assert first.files[-2:] == tuple(sorted(paths))
    assert len(first.files) == 5


def test_short_frontend_keyword_does_not_match_build(
    context_map: context_builder.ContextMap,
) -> None:
    selection = context_builder.build_context(
        context_map,
        task="Build a backend helper",
        role="backend",
    )

    assert selection.files == (
        "AGENTS.md",
        "docs/CURRENT_STATE.md",
        ".agents/roles/backend.md",
    )


def test_rejects_explicit_secret_named_file(
    context_map: context_builder.ContextMap,
    tmp_path: Path,
) -> None:
    for relative_path in ("AGENTS.md", "CURRENT.md", "security-role.md"):
        (tmp_path / relative_path).write_text("safe context\n", encoding="utf-8")
    secret_path = tmp_path / "production-credentials.txt"
    secret_path.write_text("not-a-real-secret\n", encoding="utf-8")
    temporary_map = replace(
        context_map,
        repository_root=tmp_path,
        core_files=("AGENTS.md", "CURRENT.md"),
        roles={"security": "security-role.md"},
        domains=(),
    )

    with pytest.raises(context_builder.ContextError, match="excluded path"):
        context_builder.build_context(
            temporary_map,
            task="Audit configured credentials",
            role="security",
            target_paths=(secret_path.name,),
        )


def test_byte_budget_never_drops_mandatory_context(
    context_map: context_builder.ContextMap,
) -> None:
    mandatory = (
        *context_map.core_files,
        context_map.roles["backend"],
    )
    mandatory_bytes = sum(
        (context_map.repository_root / relative_path).stat().st_size
        for relative_path in mandatory
    )

    selection = context_builder.build_context(
        context_map,
        task="Make a small focused change",
        role="backend",
        max_files=3,
        max_bytes=mandatory_bytes,
    )
    assert selection.files == mandatory
    assert selection.total_bytes == mandatory_bytes

    with pytest.raises(context_builder.ContextError, match="core files"):
        context_builder.build_context(
            context_map,
            task="Make a small focused change",
            role="backend",
            max_files=3,
            max_bytes=mandatory_bytes - 1,
        )


def test_markdown_bundle_contains_only_selected_files(
    context_map: context_builder.ContextMap,
) -> None:
    selection = context_builder.build_context(
        context_map,
        task="Make a small focused change",
        role="documentation",
        max_files=3,
    )

    bundle = context_builder.render_markdown(
        context_map,
        selection,
        task="Make a small focused change",
        role="documentation",
    )

    assert "## `AGENTS.md`" in bundle
    assert "## `docs/CURRENT_STATE.md`" in bundle
    assert "## `.agents/roles/documentation.md`" in bundle
    assert bundle.count("\n## `") == 3
    assert "node_modules" not in context_builder.render_manifest(selection)


def test_check_mode_validates_mapping_and_rejects_bad_version(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert context_builder.main(["--check", "--repo-root", str(REPOSITORY_ROOT)]) == 0
    captured = capsys.readouterr()
    assert captured.out == "context map OK: 6 roles, 9 domains\n"
    assert captured.err == ""

    config_directory = tmp_path / ".agents"
    config_directory.mkdir()
    (config_directory / "context-map.toml").write_text("version = 99\n", encoding="utf-8")

    assert context_builder.main(["--check", "--repo-root", str(tmp_path)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "context map version must be 1" in captured.err
