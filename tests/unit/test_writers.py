"""Code and test writers with a fake LLM."""

import pytest

from app.config import Settings
from app.llm.provider import LLMProvider
from app.schemas import GeneratedModule, GeneratedTests
from app.tools.code_writer import write_code
from app.tools.test_writer import write_tests
from tests.unit.test_llm_provider import FakeChatModel


def test_write_code_validates_generated_module() -> None:
    module = GeneratedModule(
        filename="solution.py",
        source="def add(a, b):\n    return a + b\n",
        entrypoint="add",
        explanation="Sum two integers.",
    )
    llm = LLMProvider(FakeChatModel(structured_results=[module]), Settings(_env_file=None))
    result = write_code(
        {
            "user_request": "add two integers",
            "requirements": ["add(a, b)"],
            "acceptance_criteria": ["returns the sum"],
        },
        llm=llm,
    )
    assert "def add" in result.source


def test_write_code_rejects_unsafe_source() -> None:
    module = GeneratedModule(
        filename="solution.py",
        source="import socket\n",
        explanation="bad",
    )
    llm = LLMProvider(FakeChatModel(structured_results=[module, module]), Settings(_env_file=None))
    with pytest.raises(ValueError, match="Disallowed import"):
        write_code({"user_request": "hack"}, llm=llm)


def test_write_tests_require_solution_import() -> None:
    tests = GeneratedTests(
        filename="test_solution.py",
        source="def test_add():\n    assert 1 + 1 == 2\n",
        explanation="does not import solution",
    )
    llm = LLMProvider(FakeChatModel(structured_results=[tests, tests]), Settings(_env_file=None))
    with pytest.raises(ValueError, match="solution"):
        write_tests(
            {
                "user_request": "add",
                "code": "def add(a, b): return a + b",
                "requirements": ["add"],
                "acceptance_criteria": ["sum"],
            },
            llm=llm,
        )
