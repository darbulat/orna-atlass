import sys

from scripts import run_agent_evals
from scripts.run_agent_evals import resolve_command


def test_python_eval_uses_runner_interpreter() -> None:
    assert resolve_command(["python", "-m", "pytest"]) == [
        sys.executable,
        "-m",
        "pytest",
    ]


def test_non_python_eval_command_is_unchanged() -> None:
    command = ["npm", "run", "test:unit"]

    assert resolve_command(command) is command


def test_tier_without_registered_evaluations_fails(
    monkeypatch, capsys, tmp_path
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["run_agent_evals.py", "--tier", "fast", "--root", str(tmp_path)],
    )
    monkeypatch.setattr(
        run_agent_evals,
        "load_evaluations",
        lambda root: [
            {
                "id": "backend-contracts",
                "area": "quality",
                "tier": "full",
                "command": ["python", "-m", "pytest"],
            }
        ],
    )

    assert run_agent_evals.main() == 2
    assert capsys.readouterr().out == "ERROR: no evals registered for tier 'fast'.\n"
