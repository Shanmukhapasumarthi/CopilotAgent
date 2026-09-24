"""Deterministic plus LLM-backed next-action selection."""

from __future__ import annotations

from app.agent.prompts import ROUTE_SYSTEM, ROUTE_USER
from app.agent.state import AgentState
from app.llm.provider import LLMProvider
from app.schemas import AgentAction, AgentDecision


def constrain_decision(state: AgentState, decision: AgentDecision) -> AgentDecision:
    """Override illegal actions with a safe alternative. Python, not the LLM."""
    has_code = bool(state.get("code"))
    has_tests = bool(state.get("tests"))
    has_errors = bool(state.get("errors"))
    has_plan = bool(state.get("plan"))
    has_results = bool(state.get("test_results"))
    verified = (state.get("verification_result") or {}).get("passed") is True

    action = decision.action
    if action is AgentAction.FINISH and not verified:
        action = AgentAction.WRITE_CODE if not has_code else (
            AgentAction.WRITE_TESTS if not has_tests else AgentAction.RUN_TESTS
        )
    elif action is AgentAction.RUN_TESTS and not has_tests:
        action = AgentAction.WRITE_TESTS if has_code else AgentAction.WRITE_CODE
    elif action is AgentAction.WRITE_TESTS and not has_code:
        action = AgentAction.WRITE_CODE
    elif action is AgentAction.INSPECT_ERROR and not has_errors:
        action = AgentAction.RUN_TESTS if has_tests else AgentAction.WRITE_CODE
    elif action is AgentAction.MODIFY_CODE and not has_code:
        action = AgentAction.WRITE_CODE
    elif action is AgentAction.VERIFY and not has_results:
        action = AgentAction.RUN_TESTS if has_tests else AgentAction.WRITE_CODE
    elif action is AgentAction.REPLAN and not has_plan:
        action = AgentAction.WRITE_CODE

    if action is decision.action:
        return decision
    return AgentDecision(
        action=action,
        reasoning_summary="The requested action was not valid for the current state, so a safer next step was selected.",
        target_tool=action.value,
        reason=f"Constrained {decision.action.value} to {action.value}.",
    )


def heuristic_decision(state: AgentState) -> AgentDecision:
    """Python policy for the next tool. Used when no LLM is injected."""
    if not state.get("code"):
        return AgentDecision(
            action=AgentAction.WRITE_CODE,
            reasoning_summary="The plan is ready, so the next step is to write the implementation.",
            target_tool="code_writer",
            reason="No implementation exists yet.",
        )
    if not state.get("tests"):
        return AgentDecision(
            action=AgentAction.WRITE_TESTS,
            reasoning_summary="The implementation exists, so the next step is to write requirement-based tests.",
            target_tool="test_writer",
            reason="No tests exist yet.",
        )
    if not state.get("test_results"):
        return AgentDecision(
            action=AgentAction.RUN_TESTS,
            reasoning_summary="Code and tests are ready for sandboxed execution.",
            target_tool="executor",
            reason="Tests have not been executed.",
        )

    results = state.get("test_results") or {}
    failed = (not results.get("passed")) or bool(state.get("errors"))
    verification = state.get("verification_result") or {}
    if verification and verification.get("passed") is False:
        failed = True
    if failed:
        analysis = state.get("error_analysis") or {}
        if analysis.get("failure_kind") == "terminal":
            return AgentDecision(
                action=AgentAction.FAIL,
                reasoning_summary="The diagnosis is a terminal failure.",
                target_tool=None,
                reason="Terminal failure from error analysis.",
            )
        if not analysis:
            return AgentDecision(
                action=AgentAction.INSPECT_ERROR,
                reasoning_summary="The sandbox reported a failure, so the agent will diagnose it before changing code.",
                target_tool="error_analyzer",
                reason="Recoverable failure has not been diagnosed yet.",
            )
        recommended = analysis.get("recommended_action") or AgentAction.MODIFY_CODE.value
        action = AgentAction.MODIFY_CODE
        if recommended == AgentAction.REPLAN.value:
            action = AgentAction.REPLAN
        elif recommended == AgentAction.WRITE_TESTS.value:
            action = AgentAction.WRITE_TESTS
        return AgentDecision(
            action=action,
            reasoning_summary="The failure was diagnosed, so the implementation will be revised and tests will be re-run.",
            target_tool="code_modifier",
            reason="Recoverable execution or test failure.",
        )
    return AgentDecision(
        action=AgentAction.VERIFY,
        reasoning_summary="Tests ran without recorded errors; independent verification is next.",
        target_tool="verifier",
        reason="Need verification before finish.",
    )


def decide_next_action(
    state: AgentState,
    llm: LLMProvider | None = None,
) -> AgentDecision:
    iteration = int(state.get("iteration", 0))
    max_iterations = int(state.get("max_iterations", 5))
    request = (state.get("user_request") or "").strip()

    if not request:
        return AgentDecision(
            action=AgentAction.FAIL,
            reasoning_summary="The request is empty, so the run cannot continue.",
            target_tool=None,
            reason="Terminal: invalid user request.",
        )
    if (state.get("task_type") or "") == "unknown":
        return AgentDecision(
            action=AgentAction.FAIL,
            reasoning_summary="The input is not a coding task the agent can execute.",
            target_tool=None,
            reason="Terminal: invalid user request.",
        )
    if (state.get("verification_result") or {}).get("passed") is True:
        return AgentDecision(
            action=AgentAction.FINISH,
            reasoning_summary="Independent verification succeeded, so the agent is delivering the solution.",
            target_tool=None,
            reason="Verified solution.",
        )
    if iteration >= max_iterations:
        return AgentDecision(
            action=AgentAction.FAIL,
            reasoning_summary="The iteration limit was reached without a verified solution.",
            target_tool=None,
            reason="Terminal: maximum iterations exceeded.",
        )

    if llm is None:
        return constrain_decision(state, heuristic_decision(state))

    prompt = ROUTE_USER.format(
        iteration=iteration,
        max_iterations=max_iterations,
        status=state.get("status", ""),
        task_type=state.get("task_type", ""),
        has_plan=bool(state.get("plan")),
        has_code=bool(state.get("code")),
        has_tests=bool(state.get("tests")),
        has_errors=bool(state.get("errors")),
        errors=state.get("errors") or [],
    )
    decision = llm.complete_structured(prompt, AgentDecision, system=ROUTE_SYSTEM)
    return constrain_decision(state, decision)
