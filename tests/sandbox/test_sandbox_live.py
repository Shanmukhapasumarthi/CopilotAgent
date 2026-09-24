"""Live Docker sandbox checks. Skipped when Docker or the image is missing."""

from __future__ import annotations

import subprocess

import pytest

from app.sandbox.docker_runner import docker_available, run_pytest_in_docker
from app.sandbox.limits import SandboxLimits

IMAGE = "codepilot-sandbox:latest"


def _image_present() -> bool:
    if not docker_available():
        return False
    result = subprocess.run(
        ["docker", "image", "inspect", IMAGE],
        capture_output=True,
        text=True,
        timeout=20,
    )
    return result.returncode == 0


pytestmark = pytest.mark.skipif(
    not _image_present(),
    reason="Docker image codepilot-sandbox:latest is not available",
)

PASSING_CODE = "def add(a, b):\n    return a + b\n"
PASSING_TESTS = (
    "from solution import add\n\n"
    "def test_add():\n"
    "    assert add(2, 3) == 5\n"
)
FAILING_TESTS = (
    "from solution import add\n\n"
    "def test_add():\n"
    "    assert add(2, 3) == 0\n"
)
LOOP_CODE = "def hang():\n    while True:\n        pass\n"
LOOP_TESTS = "from solution import hang\n\ndef test_hang():\n    hang()\n"


def test_passing_tests_in_docker() -> None:
    result = run_pytest_in_docker(PASSING_CODE, PASSING_TESTS)
    assert result.passed is True
    assert result.timed_out is False
    assert result.exit_code == 0


def test_failing_assertion_in_docker() -> None:
    result = run_pytest_in_docker(PASSING_CODE, FAILING_TESTS)
    assert result.passed is False
    assert result.exit_code != 0


def test_timeout_kills_infinite_loop() -> None:
    limits = SandboxLimits(
        image=IMAGE,
        timeout_seconds=3,
        memory="256m",
        cpus="0.5",
        pids=64,
    )
    result = run_pytest_in_docker(LOOP_CODE, LOOP_TESTS, limits=limits)
    assert result.passed is False
    assert result.timed_out is True or result.exit_code != 0
