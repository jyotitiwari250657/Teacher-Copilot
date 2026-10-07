"""Shared pytest fixtures.

Every test runs in **mock mode**, so the suite needs no API key and no network.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

# Force mock mode and an isolated database *before* app.config is imported.
os.environ["MOCK_LLM"] = "true"
os.environ.pop("LLM_API_KEY", None)
os.environ["DATABASE_URL"] = "sqlite:///./_test_teachercopilot.db"
os.environ["SECRET_KEY"] = "test-secret-key-not-for-production"
os.environ["SEED_DEMO"] = "true"

from fastapi.testclient import TestClient  # noqa: E402

from app.db import Session, create_db_and_tables, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.services.seed import seed_demo_data  # noqa: E402

DEMO_EMAIL = "demo@teachercopilot.app"
DEMO_PASSWORD = "demo1234"


@pytest.fixture(autouse=True)
def reset_rate_limits():
    """The rate limiter is process-global; clear it so tests stay independent."""
    from app.dependencies import reset_rate_limits as _reset

    _reset()
    yield
    _reset()


@pytest.fixture(scope="function")
def db_session():
    """A clean database for each test."""
    _drop_all()
    create_db_and_tables()
    with Session(engine) as session:
        seed_demo_data(session)
        yield session


def _drop_all() -> None:
    from sqlmodel import SQLModel

    SQLModel.metadata.drop_all(engine)


@pytest.fixture(scope="function")
def client(db_session):
    """Authenticated TestClient against a freshly seeded database."""
    with TestClient(app) as test_client:
        response = test_client.post(
            "/auth/login", json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD}
        )
        assert response.status_code == 200, response.text
        token = response.json()["access_token"]
        test_client.headers["Authorization"] = f"Bearer {token}"
        yield test_client


@pytest.fixture(scope="function")
def anon_client(db_session):
    """Unauthenticated TestClient."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def seed_info(db_session):
    """Ids of the seeded objects."""
    from sqlmodel import select

    from app.models import Assessment, SchoolClass, Teacher

    teacher = db_session.exec(select(Teacher).where(Teacher.email == DEMO_EMAIL)).first()
    school_class = db_session.exec(select(SchoolClass)).first()
    assessment = db_session.exec(select(Assessment)).first()
    return {
        "teacher_id": teacher.id,
        "class_id": school_class.id,
        "assessment_id": assessment.id,
    }


@pytest.fixture
def llm_calls(monkeypatch):
    """Force live mode with a scripted ``_chat``, to test repair/retry.

    Returns ``(calls, responses)``. Pop a raw string from ``responses`` for
    each turn; the last one is reused once the list is empty.
    """
    import app.llm as llm_module

    calls: list[dict] = []
    responses: list[str] = []

    def fake_chat(system_prompt, user_prompt, *, temperature, max_tokens):
        calls.append(
            {
                "system": system_prompt,
                "user": user_prompt,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
        )
        text = responses.pop(0) if len(responses) > 1 else (responses[0] if responses else "{}")
        return text, llm_module.LLMUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30)

    class LiveSettings:
        """A settings stub that reports 'not mock', without a real API key."""

        llm_is_mock = False
        llm_api_key = "test-key"
        llm_base_url = "https://example.invalid"
        llm_model = "test-model"
        llm_timeout_seconds = 5
        llm_max_retries = 1
        llm_json_repair_retries = 2

    monkeypatch.setattr(llm_module, "settings", LiveSettings())
    monkeypatch.setattr(llm_module, "_chat", fake_chat)
    return calls, responses