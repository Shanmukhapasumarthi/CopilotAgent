"""Code modifier with a fake LLM."""

from app.config import Settings
from app.llm.provider import LLMProvider
from app.schemas import GeneratedModule
from app.tools.code_modifier import modify_code
from tests.unit.test_llm_provider import FakeChatModel


def test_modify_code_returns_validated_module() -> None:
    module = GeneratedModule(
        filename="solution.py",
        source="def add(a, b):\n    return a + b\n",
        entrypoint="add",
        explanation="Fixed subtraction bug.",
    )
    llm = LLMProvider(FakeChatModel(structured_results=[module]), Settings(_env_file=None))
    result = modify_code(
        {
            "user_request": "add",
            "code": "def add(a, b):\n    return a - b\n",
            "requirements": ["add"],
            "acceptance_criteria": ["sum"],
            "error_analysis": {
                "error_type": "AssertionError",
                "root_cause": "Used minus",
                "evidence": "assert 0 == 1",
                "affected_test": "test_add",
            },
        },
        llm=llm,
    )
    assert "return a + b" in result.source
