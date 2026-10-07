"""The ONE place in the codebase that talks to a language model.

Everything else in TeacherCopilot goes through :func:`llm_complete_json`, so
swapping DeepSeek for any other OpenAI-compatible provider is a `.env` change
(and a provider module) -- no agent needs to know.

Responsibilities
----------------
* Build a chat completion against ``LLM_BASE_URL`` using the ``openai`` client.
* Retry transient network/server failures with exponential backoff.
* Coerce the model's text into a JSON object (strip markdown fences, find the
  outer braces) instead of trusting it to be clean.
* Validate the parsed object against a Pydantic model; on failure, re-prompt the
  model with the exact validation errors and try again (bounded repair loop).
* Fully offline **mock mode**: when no API key is present (or ``MOCK_LLM=true``)
  the call is served by a per-agent canned-response builder, so the entire
  product is demoable with no key and no network.
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Callable, Type, TypeVar

from pydantic import BaseModel, ValidationError

from .config import settings

logger = logging.getLogger("teachercopilot.llm")

T = TypeVar("T", bound=BaseModel)

# A mock builder receives the agent's *already validated* input dict and returns
# a dict that must satisfy the same output schema.
MockBuilder = Callable[[dict[str, Any]], dict[str, Any]]


class LLMError(RuntimeError):
    """Raised when a model call cannot produce schema-valid JSON."""

    def __init__(self, message: str, *, attempts: int = 0, last_error: str = ""):
        super().__init__(message)
        self.attempts = attempts
        self.last_error = last_error


class LLMUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    @property
    def total(self) -> int:
        return self.total_tokens or (self.prompt_tokens + self.completion_tokens)


# ---------------------------------------------------------------------------
# JSON extraction / repair helpers
# ---------------------------------------------------------------------------
_FENCE_RE = re.compile(
    r"^\s*```(?:json|JSON)?\s*|\s*```\s*$", re.MULTILINE
)


def strip_code_fences(text: str) -> str:
    """Remove ```json ... ``` wrappers the model likes to add."""
    cleaned = text.strip()
    if "```" not in cleaned:
        return cleaned
    # Keep only the first fenced block if there is one.
    match = re.search(r"```(?:json|JSON)?\s*(.*?)```", cleaned, re.DOTALL)
    if match:
        return match.group(1).strip()
    return _FENCE_RE.sub("", cleaned).strip()


def extract_json_object(text: str) -> dict[str, Any]:
    """Pull the first balanced top-level ``{...}`` out of arbitrary text.

    Handles the common failure modes: prose before/after the JSON, markdown
    fences, and trailing commas from hand-written JSON.
    """
    cleaned = strip_code_fences(text)
    if not cleaned:
        raise ValueError("model returned an empty response")

    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    # Scan for the first balanced brace group, ignoring braces inside strings.
    start = cleaned.find("{")
    if start == -1:
        raise ValueError("no JSON object found in model response")

    depth = 0
    in_string = False
    escaped = False
    for idx in range(start, len(cleaned)):
        ch = cleaned[idx]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                candidate = cleaned[start : idx + 1]
                try:
                    parsed = json.loads(candidate)
                    if isinstance(parsed, dict):
                        return parsed
                except json.JSONDecodeError:
                    # Try again with trailing commas removed.
                    repaired = re.sub(r",\s*([}\]])", r"\1", candidate)
                    try:
                        parsed = json.loads(repaired)
                        if isinstance(parsed, dict):
                            return parsed
                    except json.JSONDecodeError:
                        pass
                break

    raise ValueError("model response contained malformed JSON")


def _describe_validation_error(err: ValidationError, model: type[BaseModel]) -> str:
    """Turn Pydantic errors into a short, model-readable repair instruction."""
    parts: list[str] = []
    for error in err.errors()[:12]:
        loc = ".".join(str(part) for part in error.get("loc", ())) or "(root)"
        msg = error.get("msg", "invalid value")
        parts.append(f"- {loc}: {msg}")
    fields = ", ".join(sorted(model.model_fields.keys()))
    return (
        "Your JSON did not match the required schema.\n"
        + "\n".join(parts)
        + f"\nRequired top-level fields: {fields}"
    )


# ---------------------------------------------------------------------------
# Provider client
# ---------------------------------------------------------------------------
_client_cache: dict[str, Any] = {}


def _get_client() -> Any:
    """Lazily build (and cache) the OpenAI-compatible client."""
    if "client" not in _client_cache:
        from openai import OpenAI

        _client_cache["client"] = OpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            timeout=float(settings.llm_timeout_seconds),
            max_retries=settings.llm_max_retries,
        )
    return _client_cache["client"]


def _chat(
    system_prompt: str,
    user_prompt: str,
    *,
    temperature: float,
    max_tokens: int,
) -> tuple[str, LLMUsage]:
    """One raw chat completion, with backoff on transient failures."""
    client = _get_client()
    last_exc: Exception | None = None

    for attempt in range(1, settings.llm_max_retries + 1):
        try:
            response = client.chat.completions.create(
                model=settings.llm_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
            )
            text = response.choices[0].message.content or ""
            usage = LLMUsage()
            if getattr(response, "usage", None):
                usage = LLMUsage(
                    prompt_tokens=getattr(response.usage, "prompt_tokens", 0) or 0,
                    completion_tokens=getattr(response.usage, "completion_tokens", 0)
                    or 0,
                    total_tokens=getattr(response.usage, "total_tokens", 0) or 0,
                )
            return text, usage
        except Exception as exc:  # noqa: BLE001 - provider errors vary widely
            last_exc = exc
            logger.warning(
                "LLM call failed (attempt %s/%s): %s",
                attempt,
                settings.llm_max_retries,
                exc,
            )
            if attempt < settings.llm_max_retries:
                time.sleep(min(2 ** (attempt - 1), 8))

    raise LLMError(
        f"Could not reach the language model at {settings.llm_base_url} "
        f"after {settings.llm_max_retries} attempts. "
        f"Set MOCK_LLM=true to run without an API key.",
        last_error=str(last_exc),
    )


# ---------------------------------------------------------------------------
# Public entry point used by every agent
# ---------------------------------------------------------------------------
def llm_complete_json(
    *,
    agent: str,
    system_prompt: str,
    user_prompt: str,
    input_payload: dict[str, Any],
    output_model: Type[T],
    mock_builder: MockBuilder,
    temperature: float = 0.3,
    max_tokens: int = 4000,
) -> tuple[T, LLMUsage, int]:
    """Run one agent turn and return ``(validated_output, usage, attempts)``.

    Parameters
    ----------
    agent:
        Used only for logging and mock dispatch.
    system_prompt / user_prompt:
        The prompt pair; the system prompt is expected to already demand bare
        JSON.
    input_payload:
        The validated agent input, handed to ``mock_builder`` in mock mode.
    output_model:
        Pydantic model the response must satisfy.
    mock_builder:
        Callable producing a schema-valid dict offline.
    """
    # ---------------- mock mode ----------------
    if settings.llm_is_mock:
        started = time.perf_counter()
        try:
            payload = mock_builder(input_payload)
            validated = output_model.model_validate(payload)
        except (ValidationError, ValueError, TypeError, KeyError) as exc:
            raise LLMError(
                f"Mock response for '{agent}' did not match the schema: {exc}",
                attempts=1,
                last_error=str(exc),
            ) from exc
        elapsed = (time.perf_counter() - started) * 1000
        logger.info("[mock] %s produced a validated payload in %.1fms", agent, elapsed)
        # Report a plausible synthetic cost so the UI has something to show.
        return validated, LLMUsage(prompt_tokens=0, completion_tokens=0), 1

    # ---------------- real model ----------------
    repair_instruction: str | None = None
    total_attempts = 0
    last_problem = ""
    usage = LLMUsage()

    max_rounds = 1 + max(0, settings.llm_json_repair_retries)
    for round_index in range(max_rounds):
        total_attempts += 1
        current_user_prompt = user_prompt
        if repair_instruction:
            current_user_prompt = (
                f"{user_prompt}\n\n"
                f"--- CORRECTION REQUIRED ---\n{repair_instruction}\n"
                "Reply with ONLY the corrected JSON object. No markdown, no "
                "explanation, no code fences."
            )

        text, usage = _chat(
            system_prompt, current_user_prompt, temperature=temperature, max_tokens=max_tokens
        )

        try:
            data = extract_json_object(text)
        except ValueError as exc:
            last_problem = f"Response was not parseable JSON: {exc}"
            repair_instruction = (
                "Your previous reply could not be parsed as JSON. "
                "Return ONLY a single valid JSON object, with double-quoted "
                "keys and string values, and nothing before or after it."
            )
            logger.warning("[%s] %s", agent, last_problem)
            continue

        try:
            validated = output_model.model_validate(data)
        except ValidationError as exc:
            last_problem = _describe_validation_error(exc, output_model)
            repair_instruction = last_problem
            logger.warning("[%s] schema validation failed, repairing: %s", agent, last_problem)
            continue

        return validated, usage, total_attempts

    raise LLMError(
        f"The '{agent}' agent did not return valid JSON matching its schema "
        f"after {total_attempts} attempt(s). Last problem: {last_problem}",
        attempts=total_attempts,
        last_error=last_problem,
    )


def provider_info() -> dict[str, Any]:
    """Small payload for the Settings page / health endpoint."""
    return {
        "provider": "DeepSeek" if "deepseek" in settings.llm_base_url.lower() else "Custom",
        "base_url": settings.llm_base_url,
        "model": settings.llm_model,
        "mock_mode": settings.llm_is_mock,
        "api_key_configured": bool(settings.llm_api_key),
    }
