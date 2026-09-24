"""Generate pytest tests from requirements, not from the implementation's internals."""

from __future__ import annotations

from app.agent.prompts import TEST_SYSTEM, TEST_USER
from app.agent.state import AgentState
from app.llm.provider import LLMProvider, get_llm_provider
from app.schemas import GeneratedTests
from app.security.untrusted import wrap_untrusted
from app.tools.python_guard import validate_python


def write_tests(state: AgentState, *, llm: LLMProvider | None = None) -> GeneratedTests:
    provider = llm or get_llm_provider()
    prompt = TEST_USER.format(
        user_request=wrap_untrusted("user_request", state.get("user_request") or ""),
        requirements="\n".join(f"- {item}" for item in state.get("requirements") or []),
        acceptance_criteria="\n".join(f"- {item}" for item in state.get("acceptance_criteria") or []),
        edge_cases="\n".join(f"- {item}" for item in state.get("edge_cases") or []) or "- none",
        constraints="\n".join(f"- {item}" for item in state.get("constraints") or []) or "- none",
        entrypoint_hint=_entrypoint_hint(state.get("code") or ""),
    )
    tests = provider.complete_structured(prompt, GeneratedTests, system=TEST_SYSTEM)
    tests.filename = "test_solution.py"
    check = validate_python(tests.source, kind="tests")
    if not check.ok:
        raise ValueError(check.error)
    if "solution" not in tests.source:
        raise ValueError("Tests must import the implementation from solution")
    return tests


def _entrypoint_hint(code: str) -> str:
    if not code.strip():
        return "(unknown — import public functions from solution)"
    return "Public names in solution.py should be imported; do not copy the implementation."
