"""Aggregate evaluation metrics from completed runs. Never invent numbers."""

from __future__ import annotations

from collections import Counter
from typing import Any


def summaries_from_trace(trace: list[dict[str, Any]]) -> list[str]:
    return [str(event.get("summary") or "") for event in trace]


def first_pass(trace: list[dict[str, Any]]) -> bool:
    texts = " ".join(summaries_from_trace(trace)).lower()
    return "tests failed" not in texts and "code modified" not in texts


def recovered(trace: list[dict[str, Any]], hidden_passed: bool) -> bool:
    texts = " ".join(summaries_from_trace(trace)).lower()
    return hidden_passed and "tests failed" in texts and "code modified" in texts


def classify_failure(record: dict[str, Any]) -> str | None:
    if record.get("hidden_passed"):
        return None
    trace = summaries_from_trace(record.get("trace") or [])
    joined = " ".join(trace).lower()
    results = record.get("test_results") or {}
    if results.get("timed_out") or "timed out" in joined:
        return "timeout"
    if "tests failed" in joined and "code modified" not in joined:
        return "debugging_failure"
    if not record.get("code"):
        return "code_generation_failure"
    if "plan generated" not in joined:
        return "planning_failure"
    if "tests generated" not in joined:
        return "test_generation_failure"
    if record.get("agent_verified") and not record.get("hidden_passed"):
        return "verification_failure"
    if "sandbox" in joined or results:
        return "execution_failure"
    return "debugging_failure"


def aggregate(records: list[dict[str, Any]]) -> dict[str, Any]:
    if not records:
        return {
            "tasks_run": 0,
            "note": "No evaluation runs recorded. Metrics are omitted until evaluate.py is executed.",
        }
    n = len(records)
    hidden_ok = [r for r in records if r.get("hidden_passed")]
    first = [r for r in hidden_ok if first_pass(r.get("trace") or [])]
    initially_failed = [r for r in records if "tests failed" in " ".join(summaries_from_trace(r.get("trace") or [])).lower()]
    recovered_ok = [r for r in records if recovered(r.get("trace") or [], bool(r.get("hidden_passed")))]
    categories = Counter(classify_failure(r) for r in records if not r.get("hidden_passed"))
    categories.pop(None, None)
    iterations = [int(r.get("iteration") or 0) for r in records]
    runtimes = [float(r.get("runtime_seconds") or 0) for r in records]
    agent_verified = [r for r in records if r.get("agent_verified")]
    return {
        "tasks_run": n,
        "task_success_rate": round(len(hidden_ok) / n, 4),
        "first_pass_success_rate": round(len(first) / n, 4),
        "recovery_rate": round(len(recovered_ok) / len(initially_failed), 4) if initially_failed else None,
        "average_iterations": round(sum(iterations) / n, 3),
        "verification_rate": round(len(agent_verified) / n, 4),
        "average_runtime_seconds": round(sum(runtimes) / n, 3),
        "failure_categories": dict(categories),
        "note": "These figures come only from the records passed in. They are not estimates.",
    }
