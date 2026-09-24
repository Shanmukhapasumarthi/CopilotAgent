"""Groq LLM provider with validated structured outputs."""

from __future__ import annotations

import json
import re
from typing import Any, TypeVar

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from pydantic import BaseModel, ValidationError

from app.config import Settings, get_settings
from app.logging_config import get_logger

T = TypeVar("T", bound=BaseModel)

SYSTEM_STRUCTURED = (
    "You are CodePilot, a software engineering agent. "
    "Return only a JSON object that matches the requested schema. "
    "Do not invent fields. Keep reasoning_summary short and user-safe."
)

_JSON_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


class LLMError(RuntimeError):
    """Raised when the LLM call or schema validation fails."""


class LLMProvider:
    """Thin adapter around one chat model. No routing, no tools."""

    def __init__(self, model: BaseChatModel, settings: Settings | None = None) -> None:
        self._model = model
        self._settings = settings or get_settings()
        self._log = get_logger("llm")

    def complete(self, prompt: str, *, system: str | None = None) -> str:
        messages = []
        if system:
            messages.append(SystemMessage(content=system))
        messages.append(HumanMessage(content=prompt))
        self._log.info("LLM complete model=%s", self._settings.llm_model)
        try:
            response = self._model.invoke(messages)
        except Exception as exc:
            raise LLMError(f"LLM complete failed: {exc}") from exc
        content = _message_text(response.content)
        if not content.strip():
            raise LLMError("LLM returned an empty response")
        return content

    def complete_structured(
        self,
        prompt: str,
        schema: type[T],
        *,
        system: str = SYSTEM_STRUCTURED,
        retries: int = 1,
    ) -> T:
        """Ask the model for a Pydantic object. Retry once on validation failure."""
        last_error: Exception | None = None
        attempts = retries + 1
        repair_note = ""
        for attempt in range(1, attempts + 1):
            self._log.info(
                "LLM structured schema=%s attempt=%s/%s model=%s",
                schema.__name__,
                attempt,
                attempts,
                self._settings.llm_model,
            )
            try:
                return self._structured_once(prompt, schema, system, repair_note)
            except (ValidationError, LLMError, TypeError, ValueError, json.JSONDecodeError) as exc:
                last_error = exc
                self._log.warning(
                    "Structured output invalid for %s: %s",
                    schema.__name__,
                    exc,
                )
                repair_note = (
                    f"The previous response did not match the schema. "
                    f"Validation error: {exc}. Return valid JSON only."
                )
        raise LLMError(
            f"Could not produce a valid {schema.__name__}: {last_error}"
        ) from last_error

    def _structured_once(
        self,
        prompt: str,
        schema: type[T],
        system: str,
        repair_note: str,
    ) -> T:
        schema_text = json.dumps(schema.model_json_schema(), indent=2)
        full_prompt = (
            f"{prompt}\n\n"
            f"{repair_note}\n\n".replace("\n\n\n", "\n\n")
            + f"JSON schema:\n{schema_text}\n"
            "Respond with a single JSON object. No markdown."
        )
        try:
            structured = self._model.with_structured_output(schema)
            result = structured.invoke(
                [
                    SystemMessage(content=system),
                    HumanMessage(content=full_prompt),
                ]
            )
            if isinstance(result, schema):
                return result
            return schema.model_validate(result)
        except (ValidationError, TypeError, ValueError, json.JSONDecodeError):
            raise
        except Exception as structured_exc:
            self._log.info(
                "with_structured_output unavailable or failed (%s); using JSON parse",
                type(structured_exc).__name__,
            )
            text = self.complete(full_prompt, system=system)
            payload = extract_json_object(text)
            return schema.model_validate(payload)


def get_llm_provider(settings: Settings | None = None) -> LLMProvider:
    cfg = settings or get_settings()
    cfg.require_llm_credentials()
    model = ChatGroq(
        model=cfg.llm_model,
        api_key=cfg.groq_api_key,
        temperature=cfg.llm_temperature,
    )
    return LLMProvider(model=model, settings=cfg)


def extract_json_object(text: str) -> dict[str, Any]:
    fenced = _JSON_FENCE.search(text)
    candidate = fenced.group(1) if fenced else text
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start < 0 or end < 0 or end <= start:
        raise LLMError("LLM did not return a JSON object")
    try:
        data = json.loads(candidate[start : end + 1])
    except json.JSONDecodeError as exc:
        raise LLMError(f"LLM JSON parse failed: {exc}") from exc
    if not isinstance(data, dict):
        raise LLMError("LLM JSON was not an object")
    return data


def _message_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and "text" in item:
                parts.append(str(item["text"]))
        return "".join(parts)
    return str(content)
