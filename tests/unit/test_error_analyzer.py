"""Heuristic error diagnosis without an LLM."""

from app.agent.state import initial_state
from app.schemas import AgentAction
from app.tools.error_analyzer import analyze_error


def test_timeout_is_recoverable() -> None:
    state = initial_state("add")
    state["test_results"] = {
        "passed": False,
        "timed_out": True,
        "stdout": "",
        "stderr": "",
        "summary": "timeout",
    }
    analysis = analyze_error(state)
    assert analysis.error_type == "Timeout"
    assert analysis.recommended_action is AgentAction.MODIFY_CODE
    assert analysis.failure_kind.value == "recoverable"


def test_assertion_failure_extracts_test_name() -> None:
    state = initial_state("add")
    state["test_results"] = {
        "passed": False,
        "timed_out": False,
        "stdout": "FAILED test_add_positive",
        "stderr": "AssertionError: assert 0 == 1",
        "summary": "1 failed",
    }
    analysis = analyze_error(state)
    assert analysis.error_type == "AssertionError"
    assert analysis.affected_test == "test_add_positive"
