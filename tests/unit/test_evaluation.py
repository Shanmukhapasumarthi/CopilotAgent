"""Evaluation task catalog and metric aggregation. No live agent calls."""

from app.tools.python_guard import validate_python
from evaluation.evaluate import load_tasks
from evaluation.metrics import aggregate, classify_failure, first_pass, recovered


def test_benchmark_has_twenty_valid_tasks() -> None:
    tasks = load_tasks()
    assert len(tasks) >= 20
    ids = [task["id"] for task in tasks]
    assert len(ids) == len(set(ids))
    required = {"id", "category", "difficulty", "problem", "requirements", "expected_behavior", "hidden_tests"}
    categories = {task["category"] for task in tasks}
    for task in tasks:
        assert required.issubset(task)
        check = validate_python(task["hidden_tests"], kind="tests")
        assert check.ok, f"{task['id']}: {check.error}"
    expected = {
        "basic_implementation",
        "edge_cases",
        "bug_fixing",
        "data_processing",
        "string_processing",
        "algorithmic",
        "file_handling",
        "exception_handling",
    }
    assert expected.issubset(categories)


def test_aggregate_empty_does_not_invent_rates() -> None:
    metrics = aggregate([])
    assert metrics["tasks_run"] == 0
    assert "task_success_rate" not in metrics


def test_aggregate_from_real_records_only() -> None:
    records = [
        {
            "hidden_passed": True,
            "agent_verified": True,
            "iteration": 5,
            "runtime_seconds": 2.0,
            "trace": [{"summary": "Tests passed"}, {"summary": "Solution verified"}],
            "code": "x",
            "test_results": {"passed": True},
        },
        {
            "hidden_passed": True,
            "agent_verified": True,
            "iteration": 8,
            "runtime_seconds": 4.0,
            "trace": [
                {"summary": "Tests failed"},
                {"summary": "Failure analyzed"},
                {"summary": "Code modified"},
                {"summary": "Tests passed"},
            ],
            "code": "x",
            "test_results": {"passed": True},
        },
        {
            "hidden_passed": False,
            "agent_verified": False,
            "iteration": 8,
            "runtime_seconds": 3.0,
            "trace": [{"summary": "Tests failed"}],
            "code": "x",
            "test_results": {"passed": False},
        },
    ]
    metrics = aggregate(records)
    assert metrics["tasks_run"] == 3
    assert metrics["task_success_rate"] == 0.6667
    assert first_pass(records[0]["trace"]) is True
    assert recovered(records[1]["trace"], True) is True
    assert classify_failure(records[2]) == "debugging_failure"
