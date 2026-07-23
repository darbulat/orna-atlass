from pathlib import Path

from scripts.check_adr_policy import _is_protected, load_policy


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def test_adr_gate_protects_its_governance_surfaces() -> None:
    policy = load_policy(REPOSITORY_ROOT)

    protected = (
        "evals/architecture/adr-policy.toml",
        "evals/manifest.toml",
        "scripts/build_agent_context.py",
        "scripts/check_adr_policy.py",
        "scripts/check_agent_harness.py",
        "scripts/check_architecture.py",
        "scripts/run_agent_evals.py",
    )
    assert all(_is_protected(path, policy) for path in protected)


def test_adr_gate_protects_repository_skill_workflows() -> None:
    policy = load_policy(REPOSITORY_ROOT)

    assert _is_protected(".agents/skills/create-api/SKILL.md", policy)
