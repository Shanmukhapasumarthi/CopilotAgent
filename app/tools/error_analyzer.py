"""Diagnose sandbox and test failures. Heuristic first; LLM optional."""

from __future__ import annotations

import re

from app.agent.prompts import ERROR_SYSTEM, ERROR_USER
from app.agent.state import AgentState
from app.llm.provider import LLMProvider
from app.schemas import AgentAction, ErrorAnalysis, FailureKind

_FAILED_TEST = re.compile(r"(test_\w+)")


def analyze_error(state: AgentState, *, llm: LLMProvider | None = None) -> ErrorAnalysis:
    heuristic = _heuristic(state)
    if llm is None:
        return heuristic
    prompt = ERROR_USER.format(
        user_request=state.get("user_request") or "",
        requirements="\n".join(f"- {item}" for item in state.get("requirements") or []) or "- none",
        stdout=(state.get("test_results") or {}).get("stdout", ""),
        stderr=(state.get("test_results") or {}).get("stderr", "") or "\n".join(state.get("errors") or []),
        summary=(state.get("test_results") or {}).get("summary", ""),
        timed_out=(state.get("test_results") or {}).get("timed_out", False),
        heuristic=heuristic.model_dump_json(),
    )
    try:
        analysis = llm.complete_structured(prompt, ErrorAnalysis, system=ERROR_SYSTEM)
        if analysis.recommended_action is AgentAction.FINISH:
            analysis.recommended_action = AgentAction.MODIFY_CODE
        return analysis
    except Exception:
        return heuristic


def _heuristic(state: AgentState) -> ErrorAnalysis:
    results = state.get("test_results") or {}
    blob = "\n".join(
        [
            results.get("stdout") or "",
            results.get("stderr") or "",
            results.get("summary") or "",
            *(state.get("errors") or []),
            state.get("execution_output") or "",
        ]
    )
    match = _FAILED_TEST.search(blob)
    affected = match.group(1) if match else None

    if results.get("timed_out"):
        return ErrorAnalysis(
            error_type="Timeout",
            root_cause="The sandbox stopped the process after the time limit. The code is likely looping or too slow.",
            affected_test=affected,
            evidence=blob[:800] or "timed_out=true",
            recommended_action=AgentAction.MODIFY_CODE,
            failure_kind=FailureKind.RECOVERABLE,
        )
    if "SyntaxError" in blob:
        return ErrorAnalysis(
            error_type="SyntaxError",
            root_cause="The generated Python is not syntactically valid.",
            affected_test=affected,
            evidence=blob[:800],
            recommended_action=AgentAction.MODIFY_CODE,
            failure_kind=FailureKind.RECOVERABLE,
        )
    if "AssertionError" in blob or "assert " in blob.lower() or "failed" in blob.lower():
        return ErrorAnalysis(
            error_type="AssertionError",
            root_cause="A test assertion failed, so the implementation does not match the required behavior.",
            affected_test=affected,
            evidence=blob[:800] or "A test failed.",
            recommended_action=AgentAction.MODIFY_CODE,
            failure_kind=FailureKind.RECOVERABLE,
        )
    if "ModuleNotFoundError" in blob or "ImportError" in blob:
        return ErrorAnalysis(
            error_type="ImportError",
            root_cause="A module import failed. The solution must stay on the allowed standard library.",
            affected_test=affected,
            evidence=blob[:800],
            recommended_action=AgentAction.MODIFY_CODE,
            failure_kind=FailureKind.RECOVERABLE,
        )
    return ErrorAnalysis(
        error_type="RuntimeError",
        root_cause="Sandbox execution failed without a more specific classification.",
        affected_test=affected,
        evidence=blob[:800] or "No detailed output was captured.",
        recommended_action=AgentAction.MODIFY_CODE,
        failure_kind=FailureKind.RECOVERABLE,
    )
