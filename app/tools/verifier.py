"""Independent verification. The LLM is not the authority that the solution works."""

from __future__ import annotations

from app.agent.state import AgentState
from app.schemas import VerificationResult
from app.tools.python_guard import validate_python


def verify_solution(state: AgentState) -> VerificationResult:
    issues: list[str] = []
    code = state.get("code") or ""
    tests = state.get("tests") or ""
    results = state.get("test_results") or {}
    requirements = state.get("requirements") or []
    acceptance = state.get("acceptance_criteria") or []

    if not code.strip():
        issues.append("No implementation is present.")
    else:
        guard = validate_python(code, kind="solution")
        if not guard.ok:
            issues.append(guard.error or "Implementation failed the static guard.")

    if not tests.strip():
        issues.append("No tests are present.")
    else:
        guard = validate_python(tests, kind="tests")
        if not guard.ok:
            issues.append(guard.error or "Tests failed the static guard.")
        if "solution" not in tests:
            issues.append("Tests do not import solution.")

    tests_passed = bool(results.get("passed")) and not results.get("timed_out")
    if not results:
        issues.append("Tests have not been executed.")
        tests_passed = False
    elif not tests_passed:
        issues.append(results.get("summary") or "Sandbox tests did not pass.")

    if not requirements:
        issues.append("Requirements are missing.")
    if not acceptance:
        issues.append("Acceptance criteria are missing.")

    requirements_met = tests_passed and not issues
    passed = requirements_met
    if passed:
        explanation = "Sandbox tests passed and static checks succeeded."
    else:
        explanation = "Verification failed: " + "; ".join(issues)
    return VerificationResult(
        passed=passed,
        requirements_met=requirements_met,
        tests_passed=tests_passed,
        issues=issues,
        explanation=explanation,
    )
