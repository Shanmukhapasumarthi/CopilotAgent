"""User-visible presentation helpers. No chain-of-thought."""

from __future__ import annotations

from typing import Any


def trace_icon(summary: str) -> str:
    text = (summary or "").lower()
    if any(token in text for token in ("failed validation", "run stopped", "timed out")):
        return "✗"
    if "fail" in text and "analyzed" not in text:
        return "⚠"
    if summary:
        return "✓"
    return "•"


def format_trace_event(event: dict[str, Any]) -> str:
    summary = (event.get("summary") or "Step").strip()
    iteration = event.get("iteration")
    prefix = f"Iteration {iteration}" if iteration not in (None, 0) else "Setup"
    return f"{prefix}  {trace_icon(summary)} {summary}"


def merge_state(current: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
    merged = dict(current)
    for key, value in update.items():
        if key == "trace":
            merged["trace"] = list(merged.get("trace") or []) + list(value or [])
        else:
            merged[key] = value
    return merged
