"""CLI entry for the CodePilot graph."""

from __future__ import annotations

import argparse
import json
import os

from app.agent.graph import build_graph
from app.agent.present import merge_state
from app.agent.state import initial_state
from app.config import get_settings
from app.logging_config import configure_logging, get_logger


def _configure_langsmith() -> None:
    """Configure LangSmith tracing if enabled. Gracefully degrades if not available."""
    settings = get_settings()
    if settings.langchain_tracing_v2.lower() != "true":
        return
    
    try:
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        if settings.langchain_api_key:
            os.environ["LANGCHAIN_API_KEY"] = settings.langchain_api_key
        if settings.langchain_project:
            os.environ["LANGCHAIN_PROJECT"] = settings.langchain_project
        if settings.langchain_endpoint:
            os.environ["LANGCHAIN_ENDPOINT"] = settings.langchain_endpoint
    except Exception as exc:
        # LangSmith configuration failure should not break the agent
        log = get_logger("langsmith")
        log.warning("Failed to configure LangSmith tracing: %s", exc)


def run_agent(
    user_request: str,
    *,
    existing_code: str = "",
    extra_constraints: str = "",
) -> dict:
    # Build initial tags
    tags = ["codepilot", "python"]
    if existing_code.strip():
        tags.append("modify")
    else:
        tags.append("build")
    if extra_constraints.strip():
        tags.append("constrained")
    
    final = None
    for snapshot in stream_agent(
        user_request,
        existing_code=existing_code,
        extra_constraints=extra_constraints,
        tags=tags,
    ):
        final = snapshot
    
    # Add final status tags to result
    if final:
        final_status = final.get("status")
        
        if final_status == "verified":
            tags.append("success")
        elif final_status == "failed":
            tags.append("failure")
        else:
            tags.append("incomplete")
        
        if final.get("iteration") >= get_settings().max_iterations:
            tags.append("max_iterations")
        
        final["tags"] = tags
    
    return final or {}


def stream_agent(
    user_request: str,
    *,
    existing_code: str = "",
    extra_constraints: str = "",
    tags: list[str] | None = None,
):
    """Yield merged state after each graph node for the UI."""
    configure_logging()
    _configure_langsmith()
    
    graph = build_graph()
    state = initial_state(
        user_request,
        existing_code=existing_code,
        extra_constraints=extra_constraints,
    )
    
    # Store tags in state for later use
    if tags:
        state["tags"] = tags
    
    accumulated: dict = dict(state)
    yield accumulated
    for chunk in graph.stream(state, {"recursion_limit": get_settings().graph_recursion_limit}):
        if not isinstance(chunk, dict):
            continue
        for payload in chunk.values():
            if isinstance(payload, dict):
                accumulated = merge_state(accumulated, payload)
        yield accumulated


def main() -> None:
    parser = argparse.ArgumentParser(description="Run CodePilot through analysis, planning, and generation.")
    parser.add_argument("request", nargs="?", default="Write a Python function add(a, b) that returns the sum of two integers.")
    parser.add_argument("--code", default="", help="Optional existing code")
    parser.add_argument("--constraints", default="", help="Optional extra constraints")
    args = parser.parse_args()
    log = get_logger("run")
    result = run_agent(args.request, existing_code=args.code, extra_constraints=args.constraints)
    log.info("status=%s next_action=%s iterations=%s", result.get("status"), result.get("next_action"), result.get("iteration"))
    
    # Add final metadata for LangSmith
    final_tags = ["codepilot", "python"]
    if args.code.strip():
        final_tags.append("modify")
    else:
        final_tags.append("build")
    if args.constraints.strip():
        final_tags.append("constrained")
    
    final_status = result.get("status")
    if final_status == "verified":
        final_tags.append("success")
    elif final_status == "failed":
        final_tags.append("failure")
    else:
        final_tags.append("incomplete")
    
    if result.get("iteration") >= get_settings().max_iterations:
        final_tags.append("max_iterations")
    
    metadata = {
        "final_status": result.get("status"),
        "final_iterations": result.get("iteration"),
        "verification_status": (result.get("verification_result") or {}).get("passed"),
        "final_tags": final_tags,
    }
    
    print(json.dumps(
        {
            "status": result.get("status"),
            "task_type": result.get("task_type"),
            "requirements": result.get("requirements"),
            "plan": result.get("plan"),
            "code": result.get("code"),
            "tests": result.get("tests"),
            "test_results": result.get("test_results"),
            "verification_result": result.get("verification_result"),
            "error_analysis": result.get("error_analysis"),
            "next_action": result.get("next_action"),
            "reasoning_summary": result.get("reasoning_summary"),
            "iteration": result.get("iteration"),
            "errors": result.get("errors"),
            "final_answer": result.get("final_answer"),
            "trace": [
                {"iteration": event.get("iteration"), "summary": event.get("summary")}
                for event in result.get("trace", [])
            ],
            "metadata": metadata,
        },
        indent=2,
    ))


if __name__ == "__main__":
    main()
