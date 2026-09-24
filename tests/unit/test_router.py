"""Router decisions and iteration limits."""

from app.agent.router import constrain_decision, decide_next_action
from app.agent.state import initial_state
from app.schemas import AgentAction, AgentDecision


def test_empty_request_is_terminal_failure() -> None:
    state = initial_state("")
    decision = decide_next_action(state)
    assert decision.action is AgentAction.FAIL
    assert "invalid" in decision.reason.lower()


def test_max_iterations_is_terminal_failure() -> None:
    state = initial_state("add two numbers")
    state["iteration"] = 5
    state["max_iterations"] = 5
    decision = decide_next_action(state)
    assert decision.action is AgentAction.FAIL
    assert "maximum iterations" in decision.reason.lower()


def test_unknown_task_is_terminal_failure() -> None:
    state = initial_state("what is the weather")
    state["task_type"] = "unknown"
    decision = decide_next_action(state)
    assert decision.action is AgentAction.FAIL


def test_default_after_plan_is_write_code() -> None:
    state = initial_state("add two numbers")
    state["task_type"] = "build"
    state["plan"] = {"steps": [{"id": 1, "description": "write add"}]}
    decision = decide_next_action(state)
    assert decision.action is AgentAction.WRITE_CODE


def test_default_after_code_is_write_tests() -> None:
    state = initial_state("add two numbers")
    state["task_type"] = "build"
    state["plan"] = {"steps": [{"id": 1, "description": "write add"}]}
    state["code"] = "def add(a, b): return a + b"
    decision = decide_next_action(state)
    assert decision.action is AgentAction.WRITE_TESTS


def test_default_after_tests_is_run_tests() -> None:
    state = initial_state("add two numbers")
    state["task_type"] = "build"
    state["code"] = "def add(a, b): return a + b"
    state["tests"] = "from solution import add\n\ndef test_add():\n    assert add(1, 2) == 3\n"
    decision = decide_next_action(state)
    assert decision.action is AgentAction.RUN_TESTS


def test_failed_tests_without_diagnosis_are_inspected() -> None:
    state = initial_state("add two numbers")
    state["task_type"] = "build"
    state["code"] = "def add(a, b): return a - b"
    state["tests"] = "from solution import add\n"
    state["test_results"] = {"passed": False, "summary": "1 failed"}
    state["errors"] = ["1 failed"]
    decision = decide_next_action(state)
    assert decision.action is AgentAction.INSPECT_ERROR


def test_failed_tests_with_diagnosis_are_modified() -> None:
    state = initial_state("add two numbers")
    state["task_type"] = "build"
    state["code"] = "def add(a, b): return a - b"
    state["tests"] = "from solution import add\n"
    state["test_results"] = {"passed": False, "summary": "1 failed"}
    state["errors"] = ["1 failed"]
    state["error_analysis"] = {
        "error_type": "AssertionError",
        "root_cause": "Wrong operator",
        "recommended_action": "MODIFY_CODE",
        "failure_kind": "recoverable",
    }
    decision = decide_next_action(state)
    assert decision.action is AgentAction.MODIFY_CODE


def test_verified_solution_finishes_even_at_limit() -> None:
    state = initial_state("add two numbers")
    state["task_type"] = "build"
    state["iteration"] = 5
    state["max_iterations"] = 5
    state["verification_result"] = {"passed": True}
    decision = decide_next_action(state)
    assert decision.action is AgentAction.FINISH


def test_constrain_blocks_run_tests_without_tests() -> None:
    state = initial_state("add two numbers")
    state["code"] = "def add(a, b): return a + b"
    raw = AgentDecision(
        action=AgentAction.RUN_TESTS,
        reasoning_summary="Ready to run tests.",
        reason="tests",
        target_tool="executor",
    )
    constrained = constrain_decision(state, raw)
    assert constrained.action is AgentAction.WRITE_TESTS


def test_constrain_blocks_finish_before_verification() -> None:
    state = initial_state("add two numbers")
    raw = AgentDecision(
        action=AgentAction.FINISH,
        reasoning_summary="Done.",
        reason="done",
    )
    constrained = constrain_decision(state, raw)
    assert constrained.action is AgentAction.WRITE_CODE
