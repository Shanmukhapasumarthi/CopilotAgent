"""Run the hidden-test benchmark. Reports only metrics from actual executions."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from app.agent.run import run_agent
from app.config import get_settings
from app.sandbox.docker_runner import docker_available, run_pytest_in_docker
from evaluation.metrics import aggregate

TASKS_PATH = Path(__file__).with_name("tasks.json")
RESULTS_PATH = Path(__file__).with_name("last_run.json")


def load_tasks(path: Path = TASKS_PATH) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    tasks = payload.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("tasks.json must contain a non-empty tasks array")
    return tasks


def evaluate_task(task: dict) -> dict:
    started = time.perf_counter()
    agent = run_agent(
        task["problem"],
        existing_code=task.get("existing_code") or "",
        extra_constraints="\n".join(task.get("requirements") or []),
    )
    runtime = time.perf_counter() - started
    code = agent.get("code") or ""
    hidden = run_pytest_in_docker(code, task["hidden_tests"]) if code else None
    hidden_passed = bool(hidden and hidden.passed)
    record = {
        "id": task["id"],
        "category": task.get("category"),
        "difficulty": task.get("difficulty"),
        "iteration": agent.get("iteration"),
        "status": agent.get("status"),
        "agent_verified": (agent.get("verification_result") or {}).get("passed") is True,
        "hidden_passed": hidden_passed,
        "hidden_summary": None if hidden is None else hidden.summary,
        "code": code,
        "test_results": agent.get("test_results") or {},
        "trace": agent.get("trace") or [],
        "runtime_seconds": round(runtime, 3),
        "errors": agent.get("errors") or [],
    }
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate CodePilot on hidden tests.")
    parser.add_argument("--limit", type=int, default=0, help="Run only the first N tasks (0 = all)")
    parser.add_argument("--dry-run", action="store_true", help="Validate tasks.json and exit")
    args = parser.parse_args()
    tasks = load_tasks()
    print(f"Loaded {len(tasks)} benchmark tasks from {TASKS_PATH}")
    if args.dry_run:
        print("Dry run only. No agent calls and no metrics.")
        return
    settings = get_settings()
    if not settings.groq_api_key.strip():
        raise SystemExit("GROQ_API_KEY is required for evaluation.")
    if not docker_available():
        raise SystemExit("Docker must be running so hidden tests can execute in the sandbox.")
    selected = tasks[: args.limit] if args.limit else tasks
    records = [evaluate_task(task) for task in selected]
    metrics = aggregate(records)
    RESULTS_PATH.write_text(json.dumps({"metrics": metrics, "records": records}, indent=2), encoding="utf-8")
    print(json.dumps(metrics, indent=2))
    print(f"Wrote {RESULTS_PATH}")


if __name__ == "__main__":
    main()
