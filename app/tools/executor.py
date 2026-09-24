"""Run generated tests in virtual environment. Uses venv for isolation instead of Docker."""

from __future__ import annotations

from app.agent.state import AgentState
from app.sandbox.venv_runner import run_pytest_in_venv
from app.sandbox.limits import SandboxLimits
from app.schemas import ExecutionResult


def execute_tests(state: AgentState, *, limits: SandboxLimits | None = None) -> ExecutionResult:
    code = state.get("code") or ""
    tests = state.get("tests") or ""
    if not code.strip() or not tests.strip():
        return ExecutionResult(
            exit_code=2,
            stdout="",
            stderr="Missing code or tests",
            timed_out=False,
            passed=False,
            summary="Cannot execute until both implementation and tests exist.",
            command=[],
        )
    return run_pytest_in_venv(code, tests, limits=limits)
