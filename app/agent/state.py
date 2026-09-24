"""LangGraph working memory for a single coding task."""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

from app.config import get_settings
from app.schemas import AgentStatus
from app.security.untrusted import clip_text


class AgentState(TypedDict, total=False):
    user_request: str
    existing_code: str
    extra_constraints: str

    task_type: str
    requirements: list[str]
    constraints: list[str]
    acceptance_criteria: list[str]
    edge_cases: list[str]

    plan: dict[str, Any]
    current_step: int

    code: str
    tests: str

    execution_output: str
    test_results: dict[str, Any]
    errors: list[str]
    observations: list[str]

    iteration: int
    max_iterations: int

    next_action: str
    status: str
    reasoning_summary: str

    verification_result: dict[str, Any]
    error_analysis: dict[str, Any]
    final_answer: str

    trace: Annotated[list[dict[str, Any]], operator.add]


def initial_state(
    user_request: str,
    *,
    existing_code: str = "",
    extra_constraints: str = "",
    max_iterations: int | None = None,
) -> AgentState:
    settings = get_settings()
    return AgentState(
        user_request=clip_text(user_request.strip(), settings.max_request_chars),
        existing_code=clip_text(existing_code, settings.max_source_chars),
        extra_constraints=clip_text(extra_constraints, settings.max_request_chars),
        task_type="",
        requirements=[],
        constraints=[],
        acceptance_criteria=[],
        edge_cases=[],
        plan={},
        current_step=0,
        code="",
        tests="",
        execution_output="",
        test_results={},
        errors=[],
        observations=[],
        iteration=0,
        max_iterations=max_iterations or settings.max_iterations,
        next_action="",
        status=AgentStatus.NEW.value,
        reasoning_summary="",
        verification_result={},
        error_analysis={},
        final_answer="",
        trace=[],
    )
