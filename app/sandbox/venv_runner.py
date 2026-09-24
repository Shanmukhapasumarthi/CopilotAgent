"""Virtual environment sandbox runner. Uses Python venv for isolation instead of Docker."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from uuid import uuid4

from app.logging_config import get_logger
from app.sandbox.limits import SandboxLimits, load_limits
from app.schemas import ExecutionResult


def venv_available() -> bool:
    """Check if venv is available."""
    return shutil.which("python") is not None and shutil.which("pip") is not None


def run_pytest_in_venv(
    code: str,
    tests: str,
    *,
    limits: SandboxLimits | None = None,
) -> ExecutionResult:
    """Run pytest in a temporary virtual environment."""
    cfg = limits or load_limits()
    log = get_logger("venv_sandbox")
    
    if not venv_available():
        return ExecutionResult(
            exit_code=127,
            stdout="",
            stderr="Python or pip not found on PATH",
            timed_out=False,
            passed=False,
            summary="Python environment not available.",
            command=[],
        )

    name = f"codepilot-{uuid4().hex[:12]}"
    with tempfile.TemporaryDirectory(prefix="codepilot-venv-") as tmp:
        workspace = Path(tmp)
        venv_dir = workspace / "venv"
        
        # Create virtual environment
        log.info("Creating virtual environment %s", name)
        try:
            subprocess.run(
                [sys.executable, "-m", "venv", str(venv_dir)],
                capture_output=True,
                text=True,
                timeout=cfg.timeout_seconds,
                check=True,
            )
        except subprocess.TimeoutExpired:
            return ExecutionResult(
                exit_code=124,
                stdout="",
                stderr="Virtual environment creation timed out",
                timed_out=True,
                passed=False,
                summary="Virtual environment creation timed out.",
                command=[],
            )
        except subprocess.CalledProcessError as exc:
            return ExecutionResult(
                exit_code=exc.returncode,
                stdout=exc.stdout or "",
                stderr=exc.stderr or "Failed to create virtual environment",
                timed_out=False,
                passed=False,
                summary="Failed to create virtual environment.",
                command=[],
            )

        # Determine Python and pip paths in the venv
        if os.name == "nt":  # Windows
            python_path = venv_dir / "Scripts" / "python.exe"
            pip_path = venv_dir / "Scripts" / "pip.exe"
        else:  # Unix-like
            python_path = venv_dir / "bin" / "python"
            pip_path = venv_dir / "bin" / "pip"

        # Install pytest in the virtual environment
        log.info("Installing pytest in virtual environment %s", name)
        try:
            subprocess.run(
                [str(pip_path), "install", "pytest"],
                capture_output=True,
                text=True,
                timeout=cfg.timeout_seconds,
                check=True,
            )
        except subprocess.TimeoutExpired:
            return ExecutionResult(
                exit_code=124,
                stdout="",
                stderr="pytest installation timed out",
                timed_out=True,
                passed=False,
                summary="pytest installation timed out.",
                command=[],
            )
        except subprocess.CalledProcessError as exc:
            return ExecutionResult(
                exit_code=exc.returncode,
                stdout=exc.stdout or "",
                stderr=exc.stderr or "Failed to install pytest",
                timed_out=False,
                passed=False,
                summary="Failed to install pytest in virtual environment.",
                command=[],
            )

        # Write code and test files
        (workspace / "solution.py").write_text(code, encoding="utf-8")
        (workspace / "test_solution.py").write_text(tests, encoding="utf-8")

        # Run pytest
        command = [
            str(python_path),
            "-m",
            "pytest",
            "test_solution.py",
            "-p",
            "no:cacheprovider",
            "-q",
            "--tb=short",
        ]
        
        log.info("Running pytest in virtual environment %s", name)
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=cfg.timeout_seconds,
                cwd=str(workspace),
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

        summary = _summarize(exit_code, stdout, stderr, timed_out)
        passed = (not timed_out) and exit_code == 0
        log.info("venv sandbox end %s passed=%s exit=%s", name, passed, exit_code)
        
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
    """Summarize test execution results."""
    if timed_out:
        return "Execution timed out and the process was killed."
    text = "\n".join(part for part in (stdout, stderr) if part).strip()
    for line in reversed(text.splitlines()):
        if "passed" in line or "failed" in line or "error" in line:
            return line.strip()
    if exit_code == 0:
        return "Tests passed."
    return f"Tests failed with exit code {exit_code}."
