"""llm.py: JSON extraction, repair, retries and mock mode."""
from __future__ import annotations

import json

import pytest

from app.llm import (
    LLMError,
    extract_json_object,
    llm_complete_json,
    strip_code_fences,
)


# ---------------------------------------------------------------------------
# JSON extraction
# ---------------------------------------------------------------------------
class TestJsonExtraction:
    def test_plain_json(self):
        assert extract_json_object('{"a": 1}') == {"a": 1}

    def test_markdown_fences(self):
        assert extract_json_object('```json\n{"a": 1}\n```') == {"a": 1}

    def test_fences_without_language(self):
        assert extract_json_object('```\n{"a": 1}\n```') == {"a": 1}

    def test_prose_around_json(self):
        text = 'Here is your lesson plan:\n{"title": "X"}\nLet me know if you need changes.'
        assert extract_json_object(text) == {"title": "X"}

    def test_trailing_comma_is_repaired(self):
        assert extract_json_object('{"a": 1, "b": 2,}') == {"a": 1, "b": 2}

    def test_braces_inside_strings_do_not_break_the_scan(self):
        payload = {"feedback": "the answer was {wrong} but close"}
        assert extract_json_object(f'prefix {json.dumps(payload)} suffix') == payload

    def test_empty_response_raises(self):
        with pytest.raises(ValueError):
            extract_json_object("   ")

    def test_no_json_raises(self):
        with pytest.raises(ValueError):
            extract_json_object("I am sorry, I cannot help with that.")

    def test_strip_code_fences_is_idempotent(self):
        once = strip_code_fences('```json\n{"a": 1}\n```')
        assert strip_code_fences(once) == once


# ---------------------------------------------------------------------------
# Mock mode
# ---------------------------------------------------------------------------
class TestMockMode:
    def test_mock_returns_validated_output(self):
        from pydantic import BaseModel

        class Out(BaseModel):
            value: int

        out, usage, attempts = llm_complete_json(
            agent="test",
            system_prompt="s",
            user_prompt="u",
            input_payload={"n": 7},
            output_model=Out,
            mock_builder=lambda payload: {"value": payload["n"] * 2},
        )
        assert out.value == 14
        assert attempts == 1

    def test_mock_builder_receives_the_input_payload(self):
        from pydantic import BaseModel

        class Out(BaseModel):
            seen: list

        out, _, _ = llm_complete_json(
            agent="test",
            system_prompt="s",
            user_prompt="u",
            input_payload={"topic": "Photosynthesis"},
            output_model=Out,
            mock_builder=lambda payload: {"seen": [payload["topic"]]},
        )
        assert out.seen == ["Photosynthesis"]

    def test_mock_that_violates_the_schema_raises(self):
        from pydantic import BaseModel

        class Out(BaseModel):
            value: int

        with pytest.raises(LLMError):
            llm_complete_json(
                agent="test",
                system_prompt="s",
                user_prompt="u",
                input_payload={},
                output_model=Out,
                mock_builder=lambda payload: {"wrong_key": 1},
            )


# ---------------------------------------------------------------------------
# Retry / repair
# ---------------------------------------------------------------------------
class TestRepairAndRetry:
    def _run(self, monkeypatch, responses, max_repairs=2):
        """Drive llm_complete_json in live mode with scripted responses."""
        import app.llm as llm_module
        from pydantic import BaseModel

        class Out(BaseModel):
            title: str
            minutes: int = 0

        class LiveSettings:
            llm_is_mock = False
            llm_api_key = "k"
            llm_base_url = "https://example.invalid"
            llm_model = "m"
            llm_timeout_seconds = 5
            llm_max_retries = 1
            llm_json_repair_retries = max_repairs

        calls: list[dict] = []
        queue = list(responses)

        def fake_chat(system_prompt, user_prompt, *, temperature, max_tokens):
            calls.append({"user": user_prompt})
            text = queue.pop(0) if len(queue) > 1 else queue[0]
            return text, llm_module.LLMUsage()

        monkeypatch.setattr(llm_module, "settings", LiveSettings())
        monkeypatch.setattr(llm_module, "_chat", fake_chat)

        out, usage, attempts = llm_complete_json(
            agent="test",
            system_prompt="s",
            user_prompt="original question",
            input_payload={},
            output_model=Out,
            mock_builder=lambda payload: {},
        )
        return out, calls, attempts

    def test_valid_json_on_the_first_try(self, monkeypatch):
        out, calls, attempts = self._run(monkeypatch, ['{"title": "Good"}'])
        assert out.title == "Good"
        assert attempts == 1
        assert len(calls) == 1

    def test_markdown_fenced_output_is_accepted(self, monkeypatch):
        out, calls, attempts = self._run(
            monkeypatch, ['```json\n{"title": "Fenced"}\n```']
        )
        assert out.title == "Fenced"
        assert attempts == 1

    def test_schema_violation_triggers_a_repair_turn(self, monkeypatch):
        out, calls, attempts = self._run(
            monkeypatch, ['{"wrong": 1}', '{"title": "Fixed"}']
        )
        assert out.title == "Fixed"
        assert attempts == 2
        assert len(calls) == 2
        # The repair turn must tell the model exactly what was wrong:
        # the required 'title' field was missing, plus the expected fields.
        assert "CORRECTION REQUIRED" in calls[1]["user"]
        assert "title" in calls[1]["user"]
        assert "Field required" in calls[1]["user"]

    def test_unparseable_output_triggers_a_repair_turn(self, monkeypatch):
        out, calls, attempts = self._run(
            monkeypatch, ["sorry, I cannot do that", '{"title": "Recovered"}']
        )
        assert out.title == "Recovered"
        assert attempts == 2
        assert "could not be parsed" in calls[1]["user"]

    def test_repairs_are_bounded_then_raise(self, monkeypatch):
        with pytest.raises(LLMError) as excinfo:
            self._run(monkeypatch, ["not json at all"], max_repairs=2)
        assert excinfo.value.attempts == 3  # 1 initial + 2 repairs
        assert "did not return valid JSON" in str(excinfo.value)

    def test_successful_repair_uses_fewer_attempts_than_the_limit(self, monkeypatch):
        _, calls, attempts = self._run(
            monkeypatch, ["garbage", '{"title": "Second try"}'], max_repairs=2
        )
        assert attempts == 2
        assert len(calls) == 2