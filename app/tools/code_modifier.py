"""Rewrite implementation from a structured failure diagnosis."""

from __future__ import annotations

from app.agent.prompts import CODE_SYSTEM, MODIFY_USER
from app.agent.state import AgentState
from app.llm.provider import LLMProvider, get_llm_provider
from app.schemas import GeneratedModule
from app.security.untrusted import wrap_untrusted
from app.tools.python_guard import validate_python


def modify_code(state: AgentState, *, llm: LLMProvider | None = None) -> GeneratedModule:
    provider = llm or get_llm_provider()
    analysis = state.get("error_analysis") or {}
    prompt = MODIFY_USER.format(
        user_request=wrap_untrusted("user_request", state.get("user_request") or ""),
        requirements="\n".join(f"- {item}" for item in state.get("requirements") or []),
        acceptance_criteria="\n".join(f"- {item}" for item in state.get("acceptance_criteria") or []),
        current_code=state.get("code") or "",
        error_type=analysis.get("error_type") or "unknown",
        root_cause=analysis.get("root_cause") or "unknown",
        evidence=analysis.get("evidence") or "\n".join(state.get("errors") or []),
        affected_test=analysis.get("affected_test") or "unknown",
    )
    module = provider.complete_structured(prompt, GeneratedModule, system=CODE_SYSTEM)
    module.filename = "solution.py"
    check = validate_python(module.source, kind="solution")
    if not check.ok:
        raise ValueError(check.error)
    return module
