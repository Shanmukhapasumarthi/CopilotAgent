"""LangSmith tracing utilities for CodePilot Agent."""

from __future__ import annotations

import time
from typing import Any, Callable

from app.logging_config import get_logger


def trace_tool_call(
    tool_name: str,
    input_data: dict[str, Any],
    output_data: dict[str, Any],
    duration_ms: float,
    iteration: int,
) -> None:
    """Log tool call details for LangSmith tracing via local logging."""
    log = get_logger("tool_tracing")
    log.info(
        "Tool: %s | Iteration: %d | Duration: %.2fms | Input: %s | Output: %s",
        tool_name,
        iteration,
        duration_ms,
        _sanitize_for_logging(input_data),
        _sanitize_for_logging(output_data),
    )


def _sanitize_for_logging(data: dict[str, Any]) -> str:
    """Sanitize data for logging to avoid exposing secrets."""
    if not data:
        return "{}"
    
    sanitized = {}
    for key, value in data.items():
        # Truncate long values
        if isinstance(value, str) and len(value) > 200:
            sanitized[key] = value[:200] + "..."
        elif isinstance(value, (list, dict)):
            sanitized[key] = f"<{type(value).__name__} data>"
        else:
            sanitized[key] = str(value)[:100] if value else ""
    
    return str(sanitized)


class ToolTracer:
    """Context manager for tracing tool execution."""
    
    def __init__(self, tool_name: str, iteration: int):
        self.tool_name = tool_name
        self.iteration = iteration
        self.start_time = None
        self.input_data = {}
        self.output_data = {}
        self.log = get_logger("tool_tracing")
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration_ms = (time.time() - self.start_time) * 1000
        if exc_type is None:
            trace_tool_call(
                self.tool_name,
                self.input_data,
                self.output_data,
                duration_ms,
                self.iteration,
            )
        else:
            self.log.error(
                "Tool: %s | Iteration: %d | Duration: %.2fms | Error: %s",
                self.tool_name,
                self.iteration,
                duration_ms,
                str(exc_val),
            )
        return False  # Don't suppress exceptions
    
    def set_input(self, **kwargs: Any) -> None:
        """Set input data for tracing."""
        self.input_data.update(kwargs)
    
    def set_output(self, **kwargs: Any) -> None:
        """Set output data for tracing."""
        self.output_data.update(kwargs)
