# Security design

CodePilot executes LLM-generated Python. Treat all generated code as hostile.

## Controls that are implemented

| Control | Where |
| --- | --- |
| Docker, not host `exec` | `app/sandbox/docker_runner.py` |
| `--network none` | `build_docker_command` |
| `--cap-drop ALL`, `no-new-privileges`, `--read-only` | same |
| CPU / memory / PID / timeout | `SandboxLimits` |
| No `docker.sock` mount | volume is only a temp workspace |
| Host env allowlist; API keys stripped | `host_env_for_docker_cli` |
| Import and `eval`/`exec`/`open` guards | `app/tools/python_guard.py` |
| Source size cap | `validate_python(..., max_chars=)` |
| Request size cap | `initial_state` + `clip_text` |
| Untrusted-data wrappers in prompts | `wrap_untrusted` |
| Iteration and graph recursion caps | `MAX_ITERATIONS`, `GRAPH_RECURSION_LIMIT` |
| Log redaction | `app/logging_config.py` |

## What this does not guarantee

- Prompt injection can still bias analysis or code. Wrappers reduce, they do not eliminate, that risk.
- Static guards are not a full sandbox. Docker is the execution boundary.
- Hidden tests in evaluation are independent of the agent's self-tests, but a clever implementation can still be wrong on untested cases.
- If Docker Desktop is stopped, tests are not executed; the agent must fail closed rather than run on the host.
