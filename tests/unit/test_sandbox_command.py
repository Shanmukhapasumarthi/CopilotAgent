"""Sandbox command construction. Does not start Docker."""

from pathlib import Path

from app.sandbox.docker_runner import build_docker_command, host_env_for_docker_cli
from app.sandbox.limits import SandboxLimits


def _limits() -> SandboxLimits:
    return SandboxLimits(
        image="codepilot-sandbox:latest",
        timeout_seconds=15,
        memory="256m",
        cpus="0.5",
        pids=64,
    )


def test_docker_command_is_isolated() -> None:
    command = build_docker_command(Path("C:/tmp/workspace"), "codepilot-abc", _limits())
    joined = " ".join(command)
    assert "--network none" in joined
    assert "--read-only" in joined
    assert "--cap-drop ALL" in joined
    assert "no-new-privileges" in joined
    assert "--memory 256m" in joined
    assert "docker.sock" not in joined
    assert "GROQ_API_KEY" not in joined
    assert command[:2] == ["docker", "run"]
    assert "pytest" in command


def test_host_env_drops_secrets() -> None:
    env = host_env_for_docker_cli(
        {
            "PATH": "C:\\Windows",
            "GROQ_API_KEY": "gsk_secret",
            "MY_API_KEY": "nope",
            "AWS_SECRET_ACCESS_KEY": "nope",
            "DOCKER_HOST": "npipe:////./pipe/docker_engine",
        }
    )
    assert env["PATH"] == "C:\\Windows"
    assert env["DOCKER_HOST"] == "npipe:////./pipe/docker_engine"
    assert "GROQ_API_KEY" not in env
    assert "MY_API_KEY" not in env
    assert "AWS_SECRET_ACCESS_KEY" not in env
