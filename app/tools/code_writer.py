"""Generate a stdlib-only Python implementation from requirements."""

from __future__ import annotations

from app.agent.prompts import CODE_SYSTEM, CODE_USER
from app.agent.state import AgentState
from app.llm.provider import LLMProvider, get_llm_provider
from app.schemas import GeneratedModule
from app.security.untrusted import wrap_untrusted
from app.tools.python_guard import validate_python


def write_code(state: AgentState, *, llm: LLMProvider | None = None) -> GeneratedModule:
    provider = llm or get_llm_provider()
    prompt = CODE_USER.format(
        user_request=wrap_untrusted("user_request", state.get("user_request") or ""),
        task_type=state.get("task_type") or "build",
        requirements="\n".join(f"- {item}" for item in state.get("requirements") or []),
        constraints="\n".join(f"- {item}" for item in state.get("constraints") or []) or "- none",
        acceptance_criteria="\n".join(f"- {item}" for item in state.get("acceptance_criteria") or []),
        edge_cases="\n".join(f"- {item}" for item in state.get("edge_cases") or []) or "- none",
        existing_code=wrap_untrusted("existing_code", state.get("existing_code") or ""),
    )
    module = provider.complete_structured(prompt, GeneratedModule, system=CODE_SYSTEM)
    module.filename = "solution.py"
    check = validate_python(module.source, kind="solution")
    if not check.ok:
        raise ValueError(check.error)
    return module
