"""Independent verifier tests."""

from app.agent.state import initial_state
from app.tools.verifier import verify_solution


def test_verifier_requires_passing_sandbox_results() -> None:
    state = initial_state("add")
    state["requirements"] = ["add"]
    state["acceptance_criteria"] = ["sum"]
    state["code"] = "def add(a, b):\n    return a + b\n"
    state["tests"] = "from solution import add\n\ndef test_add():\n    assert add(1, 2) == 3\n"
    failed = verify_solution(state)
    assert failed.passed is False
    state["test_results"] = {"passed": True, "timed_out": False, "summary": "1 passed"}
    ok = verify_solution(state)
    assert ok.passed is True
    assert ok.tests_passed is True
