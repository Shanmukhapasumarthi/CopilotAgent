"""LangGraph: analyze → plan → route ⇄ tools → deliver | pause | fail."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.agent.router import decide_next_action
from app.agent.state import AgentState
from app.llm.provider import LLMProvider
from app.logging_config import get_logger
from app.schemas import (
    AgentAction,
    AgentStatus,
    ErrorAnalysis,
    ExecutionResult,
    GeneratedModule,
    GeneratedTests,
    TaskAnalysis,
    TraceEvent,
    VerificationResult,
)
from app.tools.code_modifier import modify_code
from app.tools.code_writer import write_code
from app.tools.error_analyzer import analyze_error
from app.tools.executor import execute_tests
from app.tools.planner import create_plan
from app.tools.task_analyzer import analyze_task
from app.tools.test_writer import write_tests
from app.tools.verifier import verify_solution

AnalyzeFn = Callable[[AgentState], Any]
PlanFn = Callable[[AgentState], Any]
DecideFn = Callable[[AgentState], Any]
WriteFn = Callable[[AgentState], Any]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _trace(
    *,
    iteration: int,
    summary: str,
    selected_action: str | None = None,
    tool: str | None = None,
    tool_input_summary: str = "",
    tool_result_summary: str = "",
    error: str | None = None,
    next_action: str | None = None,
) -> dict[str, Any]:
    return TraceEvent(
        timestamp=_now(),
        iteration=iteration,
        selected_action=selected_action,
        tool=tool,
        tool_input_summary=tool_input_summary,
        tool_result_summary=tool_result_summary,
        error=error,
        next_action=next_action,
        summary=summary,
    ).model_dump()


def _task_analysis_from_state(state: AgentState) -> TaskAnalysis:
    return TaskAnalysis.model_validate(
        {
            "task_type": state.get("task_type") or "unknown",
            "requirements": state.get("requirements") or ["Missing requirements"],
            "constraints": state.get("constraints") or [],
            "acceptance_criteria": state.get("acceptance_criteria")
            or ["Provide a valid coding task."],
            "edge_cases": state.get("edge_cases") or [],
        }
    )


def build_graph(
    *,
    llm: LLMProvider | None = None,
    analyze_fn: AnalyzeFn | None = None,
    plan_fn: PlanFn | None = None,
    decide_fn: DecideFn | None = None,
    write_code_fn: WriteFn | None = None,
    write_tests_fn: WriteFn | None = None,
    execute_fn: WriteFn | None = None,
    verify_fn: WriteFn | None = None,
    inspect_fn: WriteFn | None = None,
    modify_fn: WriteFn | None = None,
):
    """Compile the agent graph. Inject stubs in tests to avoid live LLM calls."""
    log = get_logger("graph")

    def analyze_node(state: AgentState) -> dict[str, Any]:
        log.info("analyze")
        fn = analyze_fn or (
            lambda s: analyze_task(
                s.get("user_request", ""),
                existing_code=s.get("existing_code", ""),
                extra_constraints=s.get("extra_constraints", ""),
                llm=llm,
                state=s,
            )
        )
        try:
            analysis = fn(state)
            if not isinstance(analysis, TaskAnalysis):
                analysis = TaskAnalysis.model_validate(analysis)
            return {
                "task_type": analysis.task_type.value,
                "requirements": analysis.requirements,
                "constraints": analysis.constraints,
                "acceptance_criteria": analysis.acceptance_criteria,
                "edge_cases": analysis.edge_cases,
                "status": AgentStatus.ANALYZED.value,
                "reasoning_summary": "The agent extracted requirements, constraints, and acceptance criteria.",
                "trace": [
                    _trace(
                        iteration=int(state.get("iteration", 0)),
                        selected_action="ANALYZE",
                        tool="task_analyzer",
                        tool_input_summary=(state.get("user_request") or "")[:160],
                        tool_result_summary=f"task_type={analysis.task_type.value}; {len(analysis.requirements)} requirements",
                        summary="Task analyzed",
                    )
                ],
            }
        except Exception as exc:
            log.error("Task analysis failed: %s", exc)
            return {
                "errors": [str(exc)],
                "trace": [
                    _trace(
                        iteration=int(state.get("iteration", 0)),
                        selected_action="ANALYZE",
                        tool="task_analyzer",
                        error=str(exc),
                        summary="Task analysis failed",
                    )
                ],
            }

    def plan_node(state: AgentState) -> dict[str, Any]:
        log.info("plan")
        analysis = _task_analysis_from_state(state)
        fn = plan_fn or (
            lambda s: create_plan(
                analysis,
                has_existing_code=bool(s.get("existing_code")),
                llm=llm,
                state=s,
            )
        )
        try:
            plan = fn(state)
            plan_data = plan.model_dump() if hasattr(plan, "model_dump") else plan
            return {
                "plan": plan_data,
                "current_step": 1,
                "status": AgentStatus.PLANNED.value,
                "reasoning_summary": "The agent produced an executable implementation plan.",
                "trace": [
                    _trace(
                        iteration=int(state.get("iteration", 0)),
                        selected_action="PLAN",
                        tool="planner",
                        tool_input_summary=f"{len(analysis.requirements)} requirements",
                        tool_result_summary=f"{len(plan_data.get('steps', []))} steps",
                        summary="Plan generated",
                    )
                ],
            }
        except Exception as exc:
            log.error("Planning failed: %s", exc)
            return {
                "errors": [str(exc)],
                "trace": [
                    _trace(
                        iteration=int(state.get("iteration", 0)),
                        selected_action="PLAN",
                        tool="planner",
                        error=str(exc),
                        summary="Planning failed",
                    )
                ],
            }

    def route_node(state: AgentState) -> dict[str, Any]:
        iteration = int(state.get("iteration", 0)) + 1
        log.info("route iteration=%s", iteration)
        fn = decide_fn or (lambda s: decide_next_action(s, llm=llm))
        try:
            decision = fn({**state, "iteration": iteration})
            if decision.action is AgentAction.FAIL:
                status = AgentStatus.FAILED.value
            elif decision.action is AgentAction.WRITE_CODE:
                status = AgentStatus.AWAITING_CODE.value
            elif decision.action is AgentAction.WRITE_TESTS:
                status = AgentStatus.CODE_READY.value
            elif decision.action is AgentAction.RUN_TESTS:
                status = AgentStatus.AWAITING_EXECUTION.value
            elif decision.action is AgentAction.VERIFY:
                status = AgentStatus.EXECUTED.value
            elif decision.action is AgentAction.INSPECT_ERROR:
                status = AgentStatus.EXECUTED.value
            elif decision.action is AgentAction.MODIFY_CODE:
                status = AgentStatus.DIAGNOSED.value
            elif decision.action is AgentAction.FINISH:
                status = AgentStatus.VERIFIED.value
            else:
                status = state.get("status") or AgentStatus.PLANNED.value
            return {
                "iteration": iteration,
                "next_action": decision.action.value,
                "reasoning_summary": decision.reasoning_summary,
                "status": status,
                "trace": [
                    _trace(
                        iteration=iteration,
                        selected_action=decision.action.value,
                        tool="router",
                        tool_input_summary=f"status={state.get('status')}",
                        tool_result_summary=decision.reason,
                        next_action=decision.action.value,
                        summary=decision.reasoning_summary,
                    )
                ],
            }
        except Exception as exc:
            log.error("Routing failed: %s", exc)
            return {
                "errors": [str(exc)],
                "trace": [
                    _trace(
                        iteration=iteration,
                        selected_action="ROUTE",
                        tool="router",
                        error=str(exc),
                        summary="Routing failed",
                    )
                ],
            }

    def write_code_node(state: AgentState) -> dict[str, Any]:
        log.info("write_code")
        fn = write_code_fn or (lambda s: write_code(s, llm=llm))
        try:
            module = fn(state)
            if not isinstance(module, GeneratedModule):
                module = GeneratedModule.model_validate(module)
            return {
                "code": module.source,
                "errors": [],
                "status": AgentStatus.CODE_READY.value,
                "reasoning_summary": "The agent generated an implementation module.",
                "trace": [
                    _trace(
                        iteration=int(state.get("iteration", 0)),
                        selected_action=AgentAction.WRITE_CODE.value,
                        tool="code_writer",
                        tool_input_summary=module.filename,
                        tool_result_summary=f"{len(module.source.splitlines())} lines",
                        summary="Code generated",
                    )
                ],
            }
        except Exception as exc:
            return {
                "errors": [str(exc)],
                "reasoning_summary": "Code generation failed validation and will be retried if iterations remain.",
                "trace": [
                    _trace(
                        iteration=int(state.get("iteration", 0)),
                        selected_action=AgentAction.WRITE_CODE.value,
                        tool="code_writer",
                        error=str(exc),
                        summary="Code generation failed validation",
                    )
                ],
            }

    def write_tests_node(state: AgentState) -> dict[str, Any]:
        log.info("write_tests")
        fn = write_tests_fn or (lambda s: write_tests(s, llm=llm))
        try:
            tests = fn(state)
            if not isinstance(tests, GeneratedTests):
                tests = GeneratedTests.model_validate(tests)
            return {
                "tests": tests.source,
                "errors": [],
                "status": AgentStatus.TESTS_READY.value,
                "reasoning_summary": "The agent generated requirement-based tests.",
                "trace": [
                    _trace(
                        iteration=int(state.get("iteration", 0)),
                        selected_action=AgentAction.WRITE_TESTS.value,
                        tool="test_writer",
                        tool_input_summary=tests.filename,
                        tool_result_summary=f"{len(tests.source.splitlines())} lines",
                        summary="Tests generated",
                    )
                ],
            }
        except Exception as exc:
            return {
                "errors": [str(exc)],
                "reasoning_summary": "Test generation failed validation and will be retried if iterations remain.",
                "trace": [
                    _trace(
                        iteration=int(state.get("iteration", 0)),
                        selected_action=AgentAction.WRITE_TESTS.value,
                        tool="test_writer",
                        error=str(exc),
                        summary="Test generation failed validation",
                    )
                ],
            }

    def execute_node(state: AgentState) -> dict[str, Any]:
        log.info("execute_tests")
        fn = execute_fn or (lambda s: execute_tests(s))
        try:
            result = fn(state)
            if not isinstance(result, ExecutionResult):
                result = ExecutionResult.model_validate(result)
            errors = [] if result.passed else [result.summary]
            if result.stderr.strip():
                errors.append(result.stderr.strip()[:500])
            observations = list(state.get("observations") or [])
            observations.append(result.summary)
            return {
                "execution_output": "\n".join(
                    part for part in (result.stdout, result.stderr) if part
                ),
                "test_results": result.model_dump(),
                "error_analysis": {},
                "errors": errors,
                "observations": observations,
                "status": AgentStatus.EXECUTED.value,
                "reasoning_summary": (
                    "Sandbox tests passed."
                    if result.passed
                    else "Sandbox execution reported failures."
                ),
                "trace": [
                    _trace(
                        iteration=int(state.get("iteration", 0)),
                        selected_action=AgentAction.RUN_TESTS.value,
                        tool="executor",
                        tool_input_summary="pytest in venv",
                        tool_result_summary=result.summary,
                        error=None if result.passed else result.summary,
                        summary="Tests passed" if result.passed else "Tests failed",
                    )
                ],
            }
        except Exception as exc:
            log.error("Execution failed: %s", exc)
            return {
                "errors": [str(exc)],
                "trace": [
                    _trace(
                        iteration=int(state.get("iteration", 0)),
                        selected_action=AgentAction.RUN_TESTS.value,
                        tool="executor",
                        error=str(exc),
                        summary="Execution failed",
                    )
                ],
            }

    def verify_node(state: AgentState) -> dict[str, Any]:
        log.info("verify")
        fn = verify_fn or (lambda s: verify_solution(s))
        result = fn(state)
        if not isinstance(result, VerificationResult):
            result = VerificationResult.model_validate(result)
        return {
            "verification_result": result.model_dump(),
            "status": AgentStatus.VERIFIED.value if result.passed else AgentStatus.EXECUTED.value,
            "errors": [] if result.passed else list(result.issues),
            "reasoning_summary": result.explanation,
            "trace": [
                _trace(
                    iteration=int(state.get("iteration", 0)),
                    selected_action=AgentAction.VERIFY.value,
                    tool="verifier",
                    tool_result_summary=result.explanation,
                    summary="Solution verified" if result.passed else "Verification failed",
                )
            ],
        }

    def inspect_node(state: AgentState) -> dict[str, Any]:
        log.info("inspect_error")
        fn = inspect_fn or (lambda s: analyze_error(s, llm=llm))
        analysis = fn(state)
        if not isinstance(analysis, ErrorAnalysis):
            analysis = ErrorAnalysis.model_validate(analysis)
        return {
            "error_analysis": analysis.model_dump(),
            "status": AgentStatus.DIAGNOSED.value,
            "reasoning_summary": analysis.root_cause,
            "trace": [
                _trace(
                    iteration=int(state.get("iteration", 0)),
                    selected_action=AgentAction.INSPECT_ERROR.value,
                    tool="error_analyzer",
                    tool_input_summary=analysis.error_type,
                    tool_result_summary=analysis.root_cause,
                    error=analysis.evidence[:200],
                    summary="Failure analyzed",
                )
            ],
        }

    def modify_node(state: AgentState) -> dict[str, Any]:
        log.info("modify_code")
        fn = modify_fn or (lambda s: modify_code(s, llm=llm))
        try:
            module = fn(state)
            if not isinstance(module, GeneratedModule):
                module = GeneratedModule.model_validate(module)
            return {
                "code": module.source,
                "errors": [],
                "test_results": {},
                "verification_result": {},
                "status": AgentStatus.MODIFIED.value,
                "reasoning_summary": "The implementation was revised after the diagnosed failure.",
                "trace": [
                    _trace(
                        iteration=int(state.get("iteration", 0)),
                        selected_action=AgentAction.MODIFY_CODE.value,
                        tool="code_modifier",
                        tool_input_summary=(state.get("error_analysis") or {}).get("error_type", ""),
                        tool_result_summary=f"{len(module.source.splitlines())} lines",
                        summary="Code modified",
                    )
                ],
            }
        except Exception as exc:
            return {
                "errors": [str(exc)],
                "reasoning_summary": "Code modification failed validation.",
                "trace": [
                    _trace(
                        iteration=int(state.get("iteration", 0)),
                        selected_action=AgentAction.MODIFY_CODE.value,
                        tool="code_modifier",
                        error=str(exc),
                        summary="Code modification failed validation",
                    )
                ],
            }

    def deliver_node(state: AgentState) -> dict[str, Any]:
        results = state.get("test_results") or {}
        final = (
            "Verified solution. "
            f"{results.get('summary') or 'Tests passed in the sandbox.'}"
        )
        return {
            "status": AgentStatus.VERIFIED.value,
            "final_answer": final,
            "next_action": AgentAction.FINISH.value,
            "trace": [
                _trace(
                    iteration=int(state.get("iteration", 0)),
                    selected_action=AgentAction.FINISH.value,
                    tool="deliver",
                    summary="Delivered verified solution",
                )
            ],
        }

    def pause_node(state: AgentState) -> dict[str, Any]:
        next_action = state.get("next_action") or ""
        final = (
            f"Stopped after action {next_action}. "
            "A later tool is not connected yet, or sandbox execution is unavailable."
        )
        return {
            "final_answer": final,
            "status": state.get("status") or AgentStatus.AWAITING_EXECUTION.value,
            "trace": [
                _trace(
                    iteration=int(state.get("iteration", 0)),
                    selected_action=next_action,
                    tool="pause",
                    summary="Paused",
                )
            ],
        }

    def fail_node(state: AgentState) -> dict[str, Any]:
        errors = list(state.get("errors") or [])
        reason = state.get("reasoning_summary") or "The run stopped without a verified solution."
        return {
            "status": AgentStatus.FAILED.value,
            "final_answer": (
                f"Controlled failure after {state.get('iteration', 0)} iteration(s). {reason}"
            ),
            "errors": errors,
            "trace": [
                _trace(
                    iteration=int(state.get("iteration", 0)),
                    selected_action=AgentAction.FAIL.value,
                    error=reason,
                    summary="Run stopped",
                )
            ],
        }

    def after_route(state: AgentState) -> str:
        action = state.get("next_action")
        mapping = {
            AgentAction.FAIL.value: "fail",
            AgentAction.WRITE_CODE.value: "write_code",
            AgentAction.WRITE_TESTS.value: "write_tests",
            AgentAction.RUN_TESTS.value: "execute",
            AgentAction.INSPECT_ERROR.value: "inspect",
            AgentAction.MODIFY_CODE.value: "modify",
            AgentAction.REPLAN.value: "plan",
            AgentAction.VERIFY.value: "verify",
            AgentAction.FINISH.value: "deliver",
        }
        return mapping.get(action or "", "pause")

    graph = StateGraph(AgentState)
    graph.add_node("analyze", analyze_node)
    graph.add_node("plan", plan_node)
    graph.add_node("route", route_node)
    graph.add_node("write_code", write_code_node)
    graph.add_node("write_tests", write_tests_node)
    graph.add_node("execute", execute_node)
    graph.add_node("inspect", inspect_node)
    graph.add_node("modify", modify_node)
    graph.add_node("verify", verify_node)
    graph.add_node("deliver", deliver_node)
    graph.add_node("pause", pause_node)
    graph.add_node("fail", fail_node)
    graph.add_edge(START, "analyze")
    graph.add_edge("analyze", "plan")
    graph.add_edge("plan", "route")
    graph.add_conditional_edges(
        "route",
        after_route,
        {
            "write_code": "write_code",
            "write_tests": "write_tests",
            "execute": "execute",
            "inspect": "inspect",
            "modify": "modify",
            "plan": "plan",
            "verify": "verify",
            "deliver": "deliver",
            "pause": "pause",
            "fail": "fail",
        },
    )
    graph.add_edge("write_code", "route")
    graph.add_edge("write_tests", "route")
    graph.add_edge("execute", "route")
    graph.add_edge("inspect", "route")
    graph.add_edge("modify", "route")
    graph.add_edge("verify", "route")
    return graph.compile()
