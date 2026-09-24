"""Task analyzer and planner without a live LLM when the request is invalid."""

from app.schemas import TaskType
from app.tools.planner import create_plan
from app.tools.task_analyzer import analyze_task


def test_empty_request_does_not_call_llm() -> None:
    analysis = analyze_task("   ")
    assert analysis.task_type is TaskType.UNKNOWN
    plan = create_plan(analysis)
    assert "invalid request" in plan.success_criteria[0].lower() or "not a coding" in plan.steps[0].description.lower()
