import sys

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
