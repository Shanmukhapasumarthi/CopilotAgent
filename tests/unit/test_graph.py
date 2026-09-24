"""LangGraph state transitions without live LLM or Docker."""

from app.agent.graph import build_graph
from app.agent.state import initial_state
from app.schemas import (
    AgentAction,
    AgentStatus,
    ExecutionResult,
    GeneratedModule,
    GeneratedTests,
    Plan,
    PlanStep,
    TaskAnalysis,
    TaskType,
)


def _analysis(_state) -> TaskAnalysis:
    return TaskAnalysis(
        task_type=TaskType.BUILD,
        requirements=["Implement add(a, b)"],
        acceptance_criteria=["Returns the integer sum"],
        edge_cases=["Negatives"],
    )


def _plan(_state) -> Plan:
    return Plan(
        steps=[
            PlanStep(id=1, description="Write add", required_tools=["WRITE_CODE"]),
            PlanStep(id=2, description="Write tests", required_tools=["WRITE_TESTS"]),
        ],
        success_criteria=["pytest passes"],
    )


def _code(_state) -> GeneratedModule:
    return GeneratedModule(
        filename="solution.py",
        source="def add(a, b):\n    return a + b\n",
        entrypoint="add",
        explanation="Adds two numbers.",
    )


def _broken_code(_state) -> GeneratedModule:
    return GeneratedModule(
        filename="solution.py",
        source="def add(a, b):\n    return a - b\n",
        entrypoint="add",
        explanation="Wrong operator on purpose.",
    )


def _fixed_code(_state) -> GeneratedModule:
    return GeneratedModule(
        filename="solution.py",
        source="def add(a, b):\n    return a + b\n",
        entrypoint="add",
        explanation="Corrected operator.",
    )


def _tests(_state) -> GeneratedTests:
    return GeneratedTests(
        filename="test_solution.py",
        source=(
            "from solution import add\n"
            "\n"
            "def test_add_positive():\n"
            "    assert add(2, 3) == 5\n"
            "\n"
            "def test_add_negative():\n"
            "    assert add(-1, 1) == 0\n"
        ),
        explanation="Covers positive and negative addends.",
    )


def _passing_execute(_state) -> ExecutionResult:
    return ExecutionResult(
        exit_code=0,
        stdout="2 passed",
        stderr="",
        timed_out=False,
        passed=True,
        summary="2 passed",
        command=["docker", "run"],
    )


def _failing_execute(_state) -> ExecutionResult:
    return ExecutionResult(
        exit_code=1,
        stdout="1 failed",
        stderr="assert 0 == 1",
        timed_out=False,
        passed=False,
        summary="1 failed",
        command=["docker", "run"],
    )


def _execute_by_implementation(state) -> ExecutionResult:
    code = state.get("code") or ""
    if "return a + b" in code:
        return _passing_execute(state)
    return _failing_execute(state)


def _graph(**kwargs):
    defaults = dict(
        analyze_fn=_analysis,
        plan_fn=_plan,
        write_code_fn=_code,
        write_tests_fn=_tests,
        execute_fn=_passing_execute,
    )
    defaults.update(kwargs)
    return build_graph(**defaults)


def test_graph_reaches_verified_finish() -> None:
    result = _graph().invoke(initial_state("Implement add(a, b)"))
    assert result["status"] == AgentStatus.VERIFIED.value
    assert result["next_action"] == AgentAction.FINISH.value
    assert result["verification_result"]["passed"] is True
    summaries = [event["summary"] for event in result["trace"]]
    assert "Code generated" in summaries
    assert "Tests generated" in summaries
    assert "Tests passed" in summaries
    assert "Solution verified" in summaries
    assert result["iteration"] == 5


def test_graph_pauses_when_tests_fail() -> None:
    result = _graph(execute_fn=_failing_execute).invoke(
        initial_state("Implement add(a, b)", max_iterations=5)
    )
    assert result["status"] != AgentStatus.VERIFIED.value
    assert result["test_results"]["passed"] is False
    assert result["iteration"] >= 5


def test_graph_recovers_from_failed_tests() -> None:
    result = _graph(
        write_code_fn=_broken_code,
        execute_fn=_execute_by_implementation,
        modify_fn=_fixed_code,
    ).invoke(initial_state("Implement add(a, b)", max_iterations=10))
    assert result["status"] == AgentStatus.VERIFIED.value
    assert "return a + b" in result["code"]
    summaries = [event["summary"] for event in result["trace"]]
    assert "Tests failed" in summaries
    assert "Failure analyzed" in summaries
    assert "Code modified" in summaries
    assert "Tests passed" in summaries
    assert "Solution verified" in summaries


def test_graph_empty_request_fails() -> None:
    graph = build_graph()
    result = graph.invoke(initial_state(""))
    assert result["status"] == AgentStatus.FAILED.value
    assert result["next_action"] == AgentAction.FAIL.value


def test_graph_hits_iteration_limit() -> None:
    graph = _graph()
    state = initial_state("Implement add(a, b)", max_iterations=2)
    result = graph.invoke(state)
    assert result["status"] == AgentStatus.FAILED.value
    assert result["iteration"] >= 2
