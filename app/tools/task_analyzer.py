"""Task analysis tool: structured requirements extraction."""

from __future__ import annotations

from app.agent.prompts import ANALYZE_SYSTEM, ANALYZE_USER
from app.agent.state import AgentState
from app.llm.provider import LLMProvider, get_llm_provider
from app.observability.tracing import ToolTracer
from app.schemas import TaskAnalysis, TaskType
from app.security.untrusted import wrap_untrusted


def analyze_task(
    user_request: str,
    *,
    existing_code: str = "",
    extra_constraints: str = "",
    llm: LLMProvider | None = None,
    state: AgentState | None = None,
) -> TaskAnalysis:
    iteration = int(state.get("iteration", 0)) if state else 0
    with ToolTracer("task_analyzer", iteration) as tracer:
        tracer.set_input(
            user_request=user_request[:100],
            has_existing_code=bool(existing_code.strip()),
            has_constraints=bool(extra_constraints.strip()),
        )
        
        request = user_request.strip()
        if not request:
            result = TaskAnalysis(
                task_type=TaskType.UNKNOWN,
                requirements=["No coding task was provided."],
                constraints=[],
                acceptance_criteria=["Provide a non-empty software engineering request."],
                edge_cases=[],
            )
            tracer.set_output(task_type=result.task_type.value, requirements_count=len(result.requirements))
            return result
        
        provider = llm or get_llm_provider()
        prompt = ANALYZE_USER.format(
            user_request=wrap_untrusted("user_request", request),
            existing_code=wrap_untrusted("existing_code", existing_code or ""),
            extra_constraints=wrap_untrusted("extra_constraints", extra_constraints or ""),
        )
        result = provider.complete_structured(prompt, TaskAnalysis, system=ANALYZE_SYSTEM)
        tracer.set_output(task_type=result.task_type.value, requirements_count=len(result.requirements))
        return result
