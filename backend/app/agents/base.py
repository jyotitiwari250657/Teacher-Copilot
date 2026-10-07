"""Base class shared by every specialist agent.

An agent is: a name, a system prompt, a Pydantic input schema, a Pydantic
output schema, a temperature, and a ``run`` method. The base class handles
input validation, the LLM round-trip (with JSON repair), post-run sanity rules,
and telemetry logging, so a concrete agent only declares *what* it does.
"""
from __future__ import annotations

import time
from typing import Any, ClassVar, Generic, Optional, Type, TypeVar

from pydantic import BaseModel, ValidationError
from sqlmodel import Session

from ..llm import LLMError, llm_complete_json

I = TypeVar("I", bound=BaseModel)
O = TypeVar("O", bound=BaseModel)


class AgentError(RuntimeError):
    """Raised when an agent cannot produce a usable result."""

    def __init__(self, message: str, *, agent: str = "", attempts: int = 0):
        super().__init__(message)
        self.agent = agent
        self.attempts = attempts


class BaseAgent(Generic[I, O]):
    """A specialist AI worker."""

    name: ClassVar[str] = "base"
    system_prompt: ClassVar[str] = ""
    input_model: ClassVar[Type[BaseModel]] = BaseModel
    output_model: ClassVar[Type[BaseModel]] = BaseModel
    temperature: ClassVar[float] = 0.3
    max_tokens: ClassVar[int] = 4000
    description: ClassVar[str] = ""

    # ---- mock mode ------------------------------------------------------
    def build_mock(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Offline canned response. Must satisfy ``output_model``."""
        raise NotImplementedError

    # ---- prompt construction -------------------------------------------
    def build_user_prompt(self, data: BaseModel) -> str:
        return (
            f"Input:\n{_pretty(data.model_dump())}\n\n"
            "Return ONLY the JSON object described in your instructions."
        )

    # ---- post-processing / invariants ----------------------------------
    def postprocess(self, output: O, data: I) -> O:
        """Optional hook for enforcing hard rules after validation."""
        return output

    # ---- main entry point ----------------------------------------------
    def run(
        self,
        raw_input: dict[str, Any] | BaseModel,
        *,
        session: Optional[Session] = None,
        run_id: Optional[int] = None,
        teacher_id: Optional[int] = None,
    ) -> O:
        """Validate input, call the model, validate output, log the turn."""
        # 1. Validate the input payload.
        payload = (
            raw_input.model_dump()
            if isinstance(raw_input, BaseModel)
            else dict(raw_input)
        )
        try:
            data: I = self.input_model.model_validate(payload)  # type: ignore[assignment]
        except ValidationError as exc:
            raise AgentError(
                f"{self.name} received invalid input: {exc.error_count()} problem(s) "
                f"- {_first_error(exc)}",
                agent=self.name,
            ) from exc

        # 2. Call the model (mock or real) with JSON repair.
        started = time.perf_counter()
        try:
            output, usage, attempts = llm_complete_json(
                agent=self.name,
                system_prompt=self.system_prompt,
                user_prompt=self.build_user_prompt(data),
                input_payload=data.model_dump(),
                output_model=self.output_model,
                mock_builder=self.build_mock,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
        except LLMError as exc:
            self._log(
                session=session,
                run_id=run_id,
                teacher_id=teacher_id,
                action="run",
                input_summary=_summary(payload),
                output_summary="",
                duration_ms=int((time.perf_counter() - started) * 1000),
                success=False,
                error=str(exc),
            )
            raise AgentError(str(exc), agent=self.name, attempts=exc.attempts) from exc

        # 3. Enforce domain rules the schema alone cannot express.
        try:
            output = self.postprocess(output, data)
        except AgentError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise AgentError(
                f"{self.name} produced output that failed post-processing: {exc}",
                agent=self.name,
                attempts=attempts,
            ) from exc

        # 4. Telemetry.
        self._log(
            session=session,
            run_id=run_id,
            teacher_id=teacher_id,
            action="run",
            input_summary=_summary(payload),
            output_summary=_summary(output.model_dump()),
            duration_ms=int((time.perf_counter() - started) * 1000),
            tokens=usage.total or None,
            success=True,
        )
        return output

    # ---- logging --------------------------------------------------------
    def _log(
        self,
        *,
        session: Optional[Session],
        run_id: Optional[int],
        teacher_id: Optional[int],
        action: str,
        input_summary: str,
        output_summary: str,
        duration_ms: int,
        tokens: Optional[int] = None,
        success: bool = True,
        error: str = "",
    ) -> None:
        if session is None:
            return
        try:
            from ..models import AgentLog

            session.add(
                AgentLog(
                    run_id=run_id,
                    teacher_id=teacher_id,
                    agent=self.name,
                    action=action,
                    input_summary=input_summary[:2000],
                    output_summary=output_summary[:2000],
                    duration_ms=duration_ms,
                    tokens=tokens,
                    success=success,
                    error=error[:1000],
                )
            )
            session.commit()
        except Exception:  # noqa: BLE001 - logging must never break a run
            pass


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _pretty(data: Any) -> str:
    import json

    return json.dumps(data, ensure_ascii=False, indent=2)


def _summary(data: Any) -> str:
    """Compact, log-safe summary of a payload."""
    import json

    try:
        return json.dumps(data, ensure_ascii=False)[:2000]
    except (TypeError, ValueError):
        return str(data)[:2000]


def _first_error(exc: ValidationError) -> str:
    errors = exc.errors()
    if not errors:
        return "unknown validation error"
    first = errors[0]
    loc = ".".join(str(p) for p in first.get("loc", ())) or "(root)"
    return f"{loc}: {first.get('msg', '')}"
