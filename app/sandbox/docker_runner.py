"""Docker sandbox runner. Generated code never runs on the host interpreter."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from uuid import uuid4

from app.logging_config import get_logger
from app.sandbox.limits import SandboxLimits, load_limits
from app.schemas import ExecutionResult

_HOST_ENV_ALLOWLIST = {
    "PATH",
    "PATHEXT",
    "SYSTEMROOT",
    "WINDIR",
    "COMSPEC",
    "USERPROFILE",
    "HOME",
    "HOMEDRIVE",
    "HOMEPATH",
    "DOCKER_HOST",
    "DOCKER_TLS_VERIFY",
    "DOCKER_CERT_PATH",
    "DOCKER_CONTEXT",
    "PROGRAMFILES",
    "PROGRAMDATA",
    "PROGRAMFILES(X86)",
    "LOCALAPPDATA",
    "APPDATA",
    "TEMP",
    "TMP",
}

_SECRET_ENV_NAMES = {
    "GROQ_API_KEY",
    "GEMINI_API_KEY",
    "OPENAI_API_KEY",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_ACCESS_KEY_ID",
    "SSH_AUTH_SOCK",
}


def host_env_for_docker_cli(source: dict[str, str] | None = None) -> dict[str, str]:
    """Environment for the docker CLI on the host. Secrets are never forwarded."""
    raw = source if source is not None else os.environ
    env: dict[str, str] = {}
    for key, value in raw.items():
        upper = key.upper()
        if upper in _SECRET_ENV_NAMES:
            continue
        if "API_KEY" in upper or "SECRET" in upper or "PASSWORD" in upper or "TOKEN" in upper:
            continue
        if upper in _HOST_ENV_ALLOWLIST or key in _HOST_ENV_ALLOWLIST:
            env[key] = value
    return env


def build_docker_command(
    workspace: Path,
    container_name: str,
    limits: SandboxLimits,
) -> list[str]:
    workspace_path = str(workspace.resolve())
    return [
        "docker",
        "run",
        "--name",
        container_name,
        "--rm",
        "--network",
        "none",
        "--cpus",
        limits.cpus,
        "--memory",
        limits.memory,
        "--memory-swap",
        limits.memory,
        "--pids-limit",
        str(limits.pids),
        "--read-only",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=16m",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--user",
        "65534:65534",
        "--workdir",
        "/workspace",
        "-v",
        f"{workspace_path}:/workspace:ro",
        "-e",
        "PYTHONDONTWRITEBYTECODE=1",
        "-e",
        "PYTHONUNBUFFERED=1",
        "-e",
        "HOME=/tmp",
        limits.image,
        "python",
        "-m",
        "pytest",
        "test_solution.py",
        "-p",
        "no:cacheprovider",
        "-q",
        "--tb=short",
    ]


def docker_available(*, timeout_seconds: int = 20) -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            env=host_env_for_docker_cli(),
        )
    except (subprocess.TimeoutExpired, OSError):
        return False
    return result.returncode == 0


def run_pytest_in_docker(
    code: str,
    tests: str,
    *,
    limits: SandboxLimits | None = None,
) -> ExecutionResult:
    cfg = limits or load_limits()
    log = get_logger("sandbox")
    if shutil.which("docker") is None:
        return ExecutionResult(
            exit_code=127,
            stdout="",
            stderr="docker executable not found on PATH",
            timed_out=False,
            passed=False,
            summary="Docker is not installed or not on PATH.",
            command=[],
        )
    if not docker_available():
        return ExecutionResult(
            exit_code=127,
            stdout="",
            stderr="Docker CLI is present but the daemon did not respond to docker info.",
            timed_out=False,
            passed=False,
            summary="Docker Desktop is not running. Start it, then build codepilot-sandbox:latest.",
            command=[],
        )

    name = f"codepilot-{uuid4().hex[:12]}"
    with tempfile.TemporaryDirectory(prefix="codepilot-sandbox-") as tmp:
        workspace = Path(tmp)
        (workspace / "solution.py").write_text(code, encoding="utf-8")
        (workspace / "test_solution.py").write_text(tests, encoding="utf-8")
        command = build_docker_command(workspace, name, cfg)
        log.info("sandbox start container=%s timeout=%ss image=%s", name, cfg.timeout_seconds, cfg.image)
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=cfg.timeout_seconds,
                env=host_env_for_docker_cli(),
            )
            stdout = completed.stdout or ""
            stderr = completed.stderr or ""
            timed_out = False
            exit_code = completed.returncode
        except subprocess.TimeoutExpired as exc:
            stdout = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
            stderr = (exc.stderr or "") if isinstance(exc.stderr, str) else "execution timed out"
            timed_out = True
            exit_code = 124
            subprocess.run(
                ["docker", "rm", "-f", name],
                capture_output=True,
                text=True,
                timeout=10,
                env=host_env_for_docker_cli(),
            )
        summary = _summarize(exit_code, stdout, stderr, timed_out)
        passed = (not timed_out) and exit_code == 0
        log.info("sandbox end container=%s passed=%s exit=%s", name, passed, exit_code)
        return ExecutionResult(
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            timed_out=timed_out,
            passed=passed,
            summary=summary,
            command=command,
        )


def _summarize(exit_code: int, stdout: str, stderr: str, timed_out: bool) -> str:
    if timed_out:
        return "Execution timed out and the container was killed."
    text = "\n".join(part for part in (stdout, stderr) if part).strip()
    for line in reversed(text.splitlines()):
        if "passed" in line or "failed" in line or "error" in line:
            return line.strip()
    if exit_code == 0:
        return "Tests passed."
    return f"Tests failed with exit code {exit_code}."
