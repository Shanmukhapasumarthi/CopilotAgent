"""Planner: structured implementation plan from an analysis."""

from __future__ import annotations

from app.agent.prompts import PLAN_SYSTEM, PLAN_USER
from app.agent.state import AgentState
from app.llm.provider import LLMProvider, get_llm_provider
from app.observability.tracing import ToolTracer
from app.schemas import Plan, PlanStep, TaskAnalysis


def create_plan(
    analysis: TaskAnalysis,
    *,
    has_existing_code: bool = False,
    llm: LLMProvider | None = None,
    state: AgentState | None = None,
) -> Plan:
    iteration = int(state.get("iteration", 0)) if state else 0
    with ToolTracer("planner", iteration) as tracer:
        tracer.set_input(
            task_type=analysis.task_type.value,
            requirements_count=len(analysis.requirements),
            has_existing_code=has_existing_code,
        )
        
        if analysis.task_type.value == "unknown":
            result = Plan(
                steps=[
                    PlanStep(
                        id=1,
                        description="Reject the request; it is not a coding task.",
                        required_tools=[],
                    )
                ],
                success_criteria=["Do not generate code for an invalid request."],
            )
            tracer.set_output(steps_count=len(result.steps))
            return result
        
        provider = llm or get_llm_provider()
        prompt = PLAN_USER.format(
            task_type=analysis.task_type.value,
            requirements="\n".join(f"- {item}" for item in analysis.requirements),
            constraints="\n".join(f"- {item}" for item in analysis.constraints) or "- none",
            acceptance_criteria="\n".join(f"- {item}" for item in analysis.acceptance_criteria),
            edge_cases="\n".join(f"- {item}" for item in analysis.edge_cases) or "- none",
            has_existing_code=has_existing_code,
        )
        result = provider.complete_structured(prompt, Plan, system=PLAN_SYSTEM)
        tracer.set_output(steps_count=len(result.steps))
        return result
