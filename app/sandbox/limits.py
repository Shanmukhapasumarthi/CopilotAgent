"""Sandbox resource limits. Python enforces these; the LLM cannot change them."""

from __future__ import annotations

from dataclasses import dataclass

from app.config import Settings, get_settings


@dataclass(frozen=True)
class SandboxLimits:
    timeout_seconds: int
    memory: str
    cpus: str
    pids: int


def load_limits(settings: Settings | None = None) -> SandboxLimits:
    cfg = settings or get_settings()
    return SandboxLimits(
        timeout_seconds=cfg.sandbox_timeout_seconds,
        memory=cfg.sandbox_memory,
        cpus=cfg.sandbox_cpus,
        pids=cfg.sandbox_pids,
    )
