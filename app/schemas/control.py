"""Control-plane models. The LLM must fill these; Python validates them."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator


class TaskType(str, Enum):
    BUILD = "build"
    FIX = "fix"
    UNKNOWN = "unknown"


class AgentAction(str, Enum):
    WRITE_CODE = "WRITE_CODE"
    WRITE_TESTS = "WRITE_TESTS"
    RUN_TESTS = "RUN_TESTS"
    INSPECT_ERROR = "INSPECT_ERROR"
    MODIFY_CODE = "MODIFY_CODE"
    REPLAN = "REPLAN"
    VERIFY = "VERIFY"
    FINISH = "FINISH"
    FAIL = "FAIL"


class FailureKind(str, Enum):
    RECOVERABLE = "recoverable"
    TERMINAL = "terminal"


class AgentStatus(str, Enum):
    NEW = "new"
    ANALYZED = "analyzed"
    PLANNED = "planned"
    AWAITING_CODE = "awaiting_code"
    CODE_READY = "code_ready"
    TESTS_READY = "tests_ready"
    AWAITING_EXECUTION = "awaiting_execution"
    EXECUTED = "executed"
    DIAGNOSED = "diagnosed"
    MODIFIED = "modified"
    FAILED = "failed"
    VERIFIED = "verified"


class TaskAnalysis(BaseModel):
    task_type: TaskType
    requirements: list[str] = Field(min_length=1)
    constraints: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(min_length=1)
    edge_cases: list[str] = Field(default_factory=list)

    @field_validator("requirements", "acceptance_criteria", "constraints", "edge_cases")
    @classmethod
    def strip_nonempty_items(cls, items: list[str]) -> list[str]:
        cleaned = [item.strip() for item in items if item and item.strip()]
        return cleaned

    @model_validator(mode="after")
    def require_core_lists(self) -> TaskAnalysis:
        if not self.requirements:
            raise ValueError("requirements must contain at least one non-empty item")
        if not self.acceptance_criteria:
            raise ValueError("acceptance_criteria must contain at least one non-empty item")
        return self


class PlanStep(BaseModel):
    id: int = Field(ge=1)
    description: str = Field(min_length=1)
    required_tools: list[str] = Field(default_factory=list)


class Plan(BaseModel):
    steps: list[PlanStep] = Field(min_length=1)
    success_criteria: list[str] = Field(min_length=1)


class AgentDecision(BaseModel):
    action: AgentAction
    reasoning_summary: str = Field(
        min_length=1,
        description="Short user-visible explanation. No hidden chain-of-thought.",
    )
    target_tool: str | None = None
    reason: str = Field(min_length=1)


class ErrorAnalysis(BaseModel):
    error_type: str = Field(min_length=1)
    root_cause: str = Field(min_length=1)
    affected_test: str | None = None
    evidence: str = Field(min_length=1)
    recommended_action: AgentAction
    failure_kind: FailureKind = FailureKind.RECOVERABLE


class VerificationResult(BaseModel):
    passed: bool
    requirements_met: bool
    tests_passed: bool
    issues: list[str] = Field(default_factory=list)
    explanation: str = Field(min_length=1)


class TraceEvent(BaseModel):
    timestamp: str
    iteration: int
    selected_action: str | None = None
    tool: str | None = None
    tool_input_summary: str = ""
    tool_result_summary: str = ""
    error: str | None = None
    next_action: str | None = None
    summary: str = Field(min_length=1)


class GeneratedModule(BaseModel):
    filename: str = Field(default="solution.py")
    source: str = Field(min_length=1)
    entrypoint: str | None = None
    explanation: str = Field(min_length=1)


class GeneratedTests(BaseModel):
    filename: str = Field(default="test_solution.py")
    source: str = Field(min_length=1)
    explanation: str = Field(min_length=1)


class ExecutionResult(BaseModel):
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    passed: bool = False
    summary: str = Field(min_length=1)
    command: list[str] = Field(default_factory=list)
