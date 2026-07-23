from pathlib import Path

from scripts.check_adr_policy import Change, Policy, evaluate_changes
from scripts.check_agent_harness import check_harness
from scripts.check_architecture import check_architecture


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def _write(root: Path, relative: str, content: str) -> None:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def test_repository_agent_harness_is_complete() -> None:
    assert check_harness(REPOSITORY_ROOT) == []


def test_runtime_architecture_respects_declared_boundaries() -> None:
    assert check_architecture(REPOSITORY_ROOT) == []


def test_architecture_check_rejects_repository_commit(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "orna_atlas/app/modules/example/repository.py",
        "async def save(session):\n    await session.commit()\n",
    )

    errors = check_architecture(tmp_path)

    assert any("repositories must not commit" in error for error in errors)


def test_architecture_check_rejects_router_repository_import(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "orna_atlas/app/modules/example/router.py",
        "from orna_atlas.app.modules.example import repository\n",
    )
    _write(
        tmp_path,
        "orna_atlas/app/modules/example/repository.py",
        "def find():\n    return None\n",
    )

    errors = check_architecture(tmp_path)

    assert any("routers may import schemas and services" in error for error in errors)


def test_architecture_check_rejects_runtime_import_cycle(tmp_path: Path) -> None:
    _write(tmp_path, "orna_atlas/app/core/first.py", "import orna_atlas.app.core.second\n")
    _write(tmp_path, "orna_atlas/app/core/second.py", "import orna_atlas.app.core.first\n")

    errors = check_architecture(tmp_path)

    assert any("runtime import cycle" in error for error in errors)


def test_adr_policy_requires_new_record_for_protected_surface(tmp_path: Path) -> None:
    errors = evaluate_changes(
        tmp_path,
        [Change("M", "AGENTS.md")],
        Policy(("AGENTS.md",)),
    )

    assert errors and "without a new ADR" in errors[0]


def test_adr_policy_accepts_well_formed_new_record(tmp_path: Path) -> None:
    adr_path = "docs/adr/0001-agent-contract.md"
    _write(
        tmp_path,
        adr_path,
        """# ADR-0001: Agent contract

- Status: accepted
- Date: 2026-07-23

## Decision

Keep the contract in the repository.

## Consequences

Architecture changes remain reviewable.
""",
    )
    _write(
        tmp_path,
        "docs/adr/README.md",
        "- [ADR-0001: Agent contract](0001-agent-contract.md)\n",
    )

    errors = evaluate_changes(
        tmp_path,
        [
            Change("M", "AGENTS.md"),
            Change("A", adr_path),
            Change("M", "docs/adr/README.md"),
        ],
        Policy(("AGENTS.md",)),
    )

    assert errors == []


def test_adr_policy_requires_index_update_for_new_record(tmp_path: Path) -> None:
    adr_path = "docs/adr/0001-agent-contract.md"
    _write(
        tmp_path,
        adr_path,
        """# ADR-0001: Agent contract

- Status: proposed
- Date: 2026-07-23

## Decision

Keep the contract in the repository.

## Consequences

Architecture changes remain reviewable.
""",
    )

    errors = evaluate_changes(
        tmp_path,
        [Change("M", "AGENTS.md"), Change("A", adr_path)],
        Policy(("AGENTS.md",)),
    )

    assert any("without updating docs/adr/README.md" in error for error in errors)


def test_adr_policy_requires_index_to_link_new_record(tmp_path: Path) -> None:
    adr_path = "docs/adr/0001-agent-contract.md"
    _write(
        tmp_path,
        adr_path,
        """# ADR-0001: Agent contract

- Status: accepted
- Date: 2026-07-23

## Decision

Keep the contract in the repository.

## Consequences

Architecture changes remain reviewable.
""",
    )
    _write(
        tmp_path,
        "docs/adr/README.md",
        (
            "Pending file: 0001-agent-contract.md\n"
            "<!-- - [ADR-0001: Hidden](0001-agent-contract.md) -->\n"
            "`- [ADR-0001: Code](0001-agent-contract.md)`\n"
            "- ![ADR-0001: Image](0001-agent-contract.md)\n"
            "<!--\n- [ADR-0001: Multiline comment](0001-agent-contract.md)\n-->\n"
            "```markdown\n- [ADR-0001: Fenced code](0001-agent-contract.md)\n```\n"
        ),
    )

    errors = evaluate_changes(
        tmp_path,
        [
            Change("M", "AGENTS.md"),
            Change("A", adr_path),
            Change("M", "docs/adr/README.md"),
        ],
        Policy(("AGENTS.md",)),
    )

    assert "docs/adr/README.md: must link to 0001-agent-contract.md" in errors
