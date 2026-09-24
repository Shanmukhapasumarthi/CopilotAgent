"""Unit tests for structured control schemas."""

import pytest
from pydantic import ValidationError

from app.schemas import (
    AgentAction,
    AgentDecision,
    ErrorAnalysis,
    Plan,
    PlanStep,
    TaskAnalysis,
    TaskType,
    VerificationResult,
)


def test_task_analysis_requires_requirements_and_criteria() -> None:
    analysis = TaskAnalysis(
        task_type=TaskType.BUILD,
        requirements=["Implement add(a, b)"],
        acceptance_criteria=["Returns the sum of two integers"],
        edge_cases=["Overflow is out of scope"],
    )
    assert analysis.task_type is TaskType.BUILD
    assert len(analysis.requirements) == 1


def test_task_analysis_rejects_empty_requirements() -> None:
    with pytest.raises(ValidationError):
        TaskAnalysis(
            task_type=TaskType.FIX,
            requirements=[],
            acceptance_criteria=["tests pass"],
        )


def test_task_analysis_strips_blank_items() -> None:
    analysis = TaskAnalysis(
        task_type=TaskType.BUILD,
        requirements=[" keep this ", "  "],
        acceptance_criteria=[" ok "],
        constraints=["", "no network"],
    )
    assert analysis.requirements == ["keep this"]
    assert analysis.constraints == ["no network"]


def test_invalid_task_type_rejected() -> None:
    with pytest.raises(ValidationError):
        TaskAnalysis.model_validate(
            {
                "task_type": "refactor-everything",
                "requirements": ["x"],
                "acceptance_criteria": ["y"],
            }
        )


def test_plan_requires_steps() -> None:
    plan = Plan(
        steps=[PlanStep(id=1, description="Write function", required_tools=["WRITE_CODE"])],
        success_criteria=["pytest passes"],
    )
    assert plan.steps[0].id == 1


def test_agent_decision_rejects_unknown_action() -> None:
    with pytest.raises(ValidationError):
        AgentDecision.model_validate(
            {
                "action": "HACK_THE_PLANET",
                "reasoning_summary": "no",
                "reason": "no",
            }
        )


def test_agent_decision_accepts_enum_action() -> None:
    decision = AgentDecision(
        action=AgentAction.WRITE_TESTS,
        reasoning_summary="Implementation exists; tests are missing.",
        target_tool="test_writer",
        reason="Need executable acceptance checks before running the sandbox.",
    )
    assert decision.action is AgentAction.WRITE_TESTS


def test_error_analysis_and_verification_round_trip() -> None:
    error = ErrorAnalysis(
        error_type="AssertionError",
        root_cause="Off-by-one in boundary case",
        affected_test="test_empty_input",
        evidence="assert 0 == 1",
        recommended_action=AgentAction.MODIFY_CODE,
    )
    verification = VerificationResult(
        passed=False,
        requirements_met=False,
        tests_passed=False,
        issues=["one failing test"],
        explanation="Independent checks are not satisfied yet.",
    )
    dumped = error.model_dump()
    assert ErrorAnalysis.model_validate(dumped).root_cause == error.root_cause
    assert verification.passed is False
