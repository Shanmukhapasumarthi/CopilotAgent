"""Streamlit interface for CodePilot. No secrets or hidden reasoning."""

from __future__ import annotations

import sys
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from app.agent.present import format_trace_event
from app.config import get_settings

st.set_page_config(page_title="CodePilot Agent", layout="wide")

EXAMPLES = {
    "Add two integers": "Write a Python function add(a, b) that returns the sum of two integers.",
    "Palindrome check": "Write is_palindrome(text) that returns True if text is a palindrome, ignoring case and spaces.",
    "Safe divide": "Write safe_divide(a, b) that returns a/b as a float and raises ValueError when b is 0.",
}


def _render_snapshot(snapshot: dict) -> None:
    status = snapshot.get("status") or "new"
    verified = (snapshot.get("verification_result") or {}).get("passed") is True
    st.subheader("Execution")
    cols = st.columns(4)
    cols[0].metric("Status", status)
    cols[1].metric("Iterations", snapshot.get("iteration") or 0)
    cols[2].metric("Next action", snapshot.get("next_action") or "—")
    cols[3].metric("Verified", "yes" if verified else "no")

    if snapshot.get("reasoning_summary"):
        st.info(snapshot["reasoning_summary"])

    # Show LangSmith trace link if available
    tags = snapshot.get("tags", [])
    if tags:
        st.caption(f"Tags: {', '.join(tags)}")

    st.markdown("### Trace")
    events = snapshot.get("trace") or []
    if not events:
        st.caption("The agent has not recorded a step yet.")
    for event in events:
        st.write(format_trace_event(event))

    analysis_tab, plan_tab, code_tab, tests_tab, run_tab, verify_tab = st.tabs(
        ["Analysis", "Plan", "Code", "Tests", "Execution", "Verification"]
    )
    with analysis_tab:
        st.write(f"Task type: `{snapshot.get('task_type') or '—'}`")
        st.write("Requirements")
        st.write(snapshot.get("requirements") or [])
        st.write("Constraints")
        st.write(snapshot.get("constraints") or [])
        st.write("Acceptance criteria")
        st.write(snapshot.get("acceptance_criteria") or [])
        st.write("Edge cases")
        st.write(snapshot.get("edge_cases") or [])
    with plan_tab:
        plan = snapshot.get("plan") or {}
        st.write("Success criteria")
        st.write(plan.get("success_criteria") or [])
        st.write("Steps")
        st.write(plan.get("steps") or [])
    with code_tab:
        code = snapshot.get("code") or ""
        if code:
            st.code(code, language="python")
        else:
            st.caption("No implementation yet.")
    with tests_tab:
        tests = snapshot.get("tests") or ""
        if tests:
            st.code(tests, language="python")
        else:
            st.caption("No tests yet.")
    with run_tab:
        results = snapshot.get("test_results") or {}
        st.write(results.get("summary") or "Not executed.")
        if results.get("stdout"):
            st.code(results["stdout"])
        if results.get("stderr"):
            st.code(results["stderr"])
        errors = snapshot.get("errors") or []
        if errors:
            st.write("Errors")
            st.write(errors)
        diagnosis = snapshot.get("error_analysis") or {}
        if diagnosis.get("error_type"):
            st.write("Diagnosis")
            st.write(
                {
                    "error_type": diagnosis.get("error_type"),
                    "root_cause": diagnosis.get("root_cause"),
                    "recommended_action": diagnosis.get("recommended_action"),
                }
            )
    with verify_tab:
        verification = snapshot.get("verification_result") or {}
        if verification:
            st.write(verification.get("explanation") or "")
            st.json(
                {
                    "passed": verification.get("passed"),
                    "requirements_met": verification.get("requirements_met"),
                    "tests_passed": verification.get("tests_passed"),
                    "issues": verification.get("issues") or [],
                }
            )
        else:
            st.caption("Not verified yet.")
        final = snapshot.get("final_answer")
        if final:
            if verified:
                st.success(final)
            else:
                st.warning(final)


def main() -> None:
    settings = get_settings()
    st.title("CodePilot Agent")
    st.caption("Goal → Plan → Act → Observe → Reason → Adapt → Verify → Deliver")

    with st.sidebar:
        st.header("Runtime")
        st.write(f"Model: `{settings.llm_model}`")
        st.write(f"API key loaded: {'yes' if settings.groq_api_key.strip() else 'no'}")
        st.write(f"Max iterations: {settings.max_iterations}")
        st.write(f"Backend: FastAPI + Virtual Environment")
        if not settings.groq_api_key.strip():
            st.error("Set GROQ_API_KEY in .env before running.")
        example = st.selectbox("Example task", ["(none)"] + list(EXAMPLES))
        if example != "(none)" and st.button("Load example"):
            st.session_state["task_text"] = EXAMPLES[example]

    task = st.text_area(
        "Task description",
        height=140,
        key="task_text",
        placeholder="Write a Python function add(a, b) that returns the sum of two integers.",
    )
    existing = st.text_area("Existing code (optional)", height=120, key="existing_code")
    constraints = st.text_input(
        "Constraints (optional)",
        placeholder="stdlib only, no network",
        key="constraints_text",
    )

    if st.button("Run agent", type="primary", disabled=not bool((task or "").strip())):
        placeholder = st.empty()
        try:
            with st.spinner("Running agent..."):
                response = requests.post(
                    "http://localhost:8000/run",
                    json={
                        "task": task,
                        "existing_code": existing or "",
                        "extra_constraints": constraints or "",
                    },
                    timeout=300,  # 5 minutes timeout
                )
                response.raise_for_status()
                snapshot = response.json()
                with placeholder.container():
                    _render_snapshot(snapshot)
                st.session_state["last_run"] = snapshot
        except requests.exceptions.ConnectionError:
            st.error("Could not connect to FastAPI backend. Start the backend with: uvicorn app.api.main:app --reload")
        except requests.exceptions.Timeout:
            st.error("Request timed out. The agent may be taking longer than expected.")
        except Exception as exc:
            st.error(str(exc))
    elif st.session_state.get("last_run"):
        _render_snapshot(st.session_state["last_run"])


main()
