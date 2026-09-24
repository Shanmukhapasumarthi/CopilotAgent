"""Unit tests for the LLM adapter using a fake chat model."""

from typing import Any

import pytest
from langchain_core.messages import AIMessage
from pydantic import BaseModel

from app.config import Settings
from app.llm.provider import LLMError, LLMProvider, extract_json_object
from app.schemas import AgentAction, AgentDecision


class FakeChatModel:
    """Minimal LangChain-like model for unit tests. No network."""

    def __init__(self, complete_content: str = "ok", structured_results: list[Any] | None = None):
        self.complete_content = complete_content
        self.structured_results = list(structured_results or [])
        self.invoke_calls = 0

    def invoke(self, _messages: list[Any]) -> AIMessage:
        self.invoke_calls += 1
        return AIMessage(content=self.complete_content)

    def with_structured_output(self, schema: type[BaseModel]) -> "FakeStructuredModel":
        return FakeStructuredModel(schema, self)


class FakeStructuredModel:
    def __init__(self, schema: type[BaseModel], parent: FakeChatModel) -> None:
        self.schema = schema
        self.parent = parent

    def invoke(self, _messages: list[Any]) -> Any:
        self.parent.invoke_calls += 1
        if not self.parent.structured_results:
            raise ValueError("no structured result configured")
        return self.parent.structured_results.pop(0)


def test_complete_returns_text() -> None:
    provider = LLMProvider(FakeChatModel("hello"), Settings(_env_file=None))
    assert provider.complete("ping") == "hello"


def test_complete_rejects_empty_response() -> None:
    provider = LLMProvider(FakeChatModel("   "), Settings(_env_file=None))
    with pytest.raises(LLMError, match="empty"):
        provider.complete("ping")


def test_complete_structured_validates_pydantic_model() -> None:
    decision = AgentDecision(
        action=AgentAction.WRITE_CODE,
        reasoning_summary="No implementation exists yet.",
        target_tool="code_writer",
        reason="Need an initial Python module.",
    )
    provider = LLMProvider(
        FakeChatModel(structured_results=[decision]),
        Settings(_env_file=None),
    )
    result = provider.complete_structured("decide", AgentDecision)
    assert result.action is AgentAction.WRITE_CODE


def test_complete_structured_retries_then_succeeds() -> None:
    good = AgentDecision(
        action=AgentAction.VERIFY,
        reasoning_summary="Tests passed; independent checks remain.",
        target_tool="verifier",
        reason="Need verification before finish.",
    )
    provider = LLMProvider(
        FakeChatModel(structured_results=[{"bad": True}, good]),
        Settings(_env_file=None),
    )
    result = provider.complete_structured("decide", AgentDecision, retries=1)
    assert result.action is AgentAction.VERIFY


def test_complete_structured_fails_after_retries() -> None:
    provider = LLMProvider(
        FakeChatModel(structured_results=[{"bad": True}, {"also": "bad"}]),
        Settings(_env_file=None),
    )
    with pytest.raises(LLMError, match="AgentDecision"):
        provider.complete_structured("decide", AgentDecision, retries=1)


def test_extract_json_object_from_fenced_block() -> None:
    text = 'prefix\n```json\n{"action": "WRITE_CODE"}\n```\n'
    assert extract_json_object(text)["action"] == "WRITE_CODE"


def test_extract_json_object_rejects_non_object() -> None:
    with pytest.raises(LLMError):
        extract_json_object("not json")
