"""Presentation helpers."""

from app.agent.present import format_trace_event, merge_state, trace_icon


def test_failed_tests_use_warning_icon() -> None:
    assert trace_icon("Tests failed") == "⚠"


def test_format_trace_event_includes_iteration() -> None:
    line = format_trace_event({"iteration": 3, "summary": "Code generated"})
    assert "Iteration 3" in line
    assert "Code generated" in line


def test_merge_state_appends_trace() -> None:
    merged = merge_state(
        {"code": "a", "trace": [{"summary": "one"}]},
        {"code": "b", "trace": [{"summary": "two"}]},
    )
    assert merged["code"] == "b"
    assert [event["summary"] for event in merged["trace"]] == ["one", "two"]
