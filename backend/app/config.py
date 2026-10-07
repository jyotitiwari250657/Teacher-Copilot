"""Application configuration.

All settings are read from the environment (optionally seeded from a local
`.env` file). No secrets live in code -- see `.env.example`.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")


def _bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


class Settings:
    """Immutable-ish settings object resolved once at import time."""

    def __init__(self) -> None:
        # --- LLM provider -------------------------------------------------
        self.llm_api_key: str = os.getenv("LLM_API_KEY", "").strip()
        self.llm_base_url: str = os.getenv(
            "LLM_BASE_URL", "https://api.deepseek.com"
        ).strip().rstrip("/")
        self.llm_model: str = os.getenv("LLM_MODEL", "deepseek-chat").strip()
        self.mock_llm: bool = _bool("MOCK_LLM", False)
        self.llm_timeout_seconds: int = _int("LLM_TIMEOUT_SECONDS", 90)
        self.llm_max_retries: int = _int("LLM_MAX_RETRIES", 3)
        self.llm_json_repair_retries: int = _int("LLM_JSON_REPAIR_RETRIES", 2)

        # --- App -----------------------------------------------------------
        self.secret_key: str = os.getenv(
            "SECRET_KEY", "dev-secret-change-me"
        )
        self.access_token_expire_minutes: int = _int(
            "ACCESS_TOKEN_EXPIRE_MINUTES", 720
        )
        self.app_name: str = "TeacherCopilot"

        # --- Database ------------------------------------------------------
        self.database_url: str = os.getenv(
            "DATABASE_URL", f"sqlite:///{BACKEND_DIR / 'teachercopilot.db'}"
        )

        # --- Messaging -----------------------------------------------------
        self.messaging_mode: str = os.getenv("MESSAGING_MODE", "simulated").strip()
        self.smtp_host: str = os.getenv("SMTP_HOST", "").strip()
        self.smtp_port: int = _int("SMTP_PORT", 587)
        self.smtp_user: str = os.getenv("SMTP_USER", "").strip()
        self.smtp_password: str = os.getenv("SMTP_PASSWORD", "").strip()
        self.smtp_from: str = os.getenv("SMTP_FROM", "teacher@school.edu").strip()
        self.smtp_use_tls: bool = _bool("SMTP_USE_TLS", True)
        self.whatsapp_account_sid: str = os.getenv(
            "WHATSAPP_ACCOUNT_SID", ""
        ).strip()
        self.whatsapp_auth_token: str = os.getenv(
            "WHATSAPP_AUTH_TOKEN", ""
        ).strip()
        self.whatsapp_from: str = os.getenv(
            "WHATSAPP_FROM", "whatsapp:+14155238886"
        ).strip()

        # --- Seeding -------------------------------------------------------
        self.seed_demo: bool = _bool("SEED_DEMO", True)
        self.demo_teacher_email: str = os.getenv(
            "DEMO_TEACHER_EMAIL", "demo@teachercopilot.app"
        )
        self.demo_teacher_password: str = os.getenv(
            "DEMO_TEACHER_PASSWORD", "demo1234"
        )

        # --- Rate limiting (LLM-backed endpoints) --------------------------
        self.rate_limit_max_calls: int = _int("RATE_LIMIT_MAX_CALLS", 40)
        self.rate_limit_window_seconds: int = _int("RATE_LIMIT_WINDOW_SECONDS", 60)

        # --- Time-saved estimates (minutes) --------------------------------
        self.minutes_lesson_plan = _int("MINUTES_LESSON_PLAN", 45)
        self.minutes_grading_per_paper = _int("MINUTES_GRADING_PER_PAPER", 3)
        self.minutes_differentiated_worksheets = _int(
            "MINUTES_DIFFERENTIATED_WORKSHEETS", 60
        )
        self.minutes_parent_message = _int("MINUTES_PARENT_MESSAGE", 5)

    @property
    def llm_is_mock(self) -> bool:
        """Mock mode is on when forced, or when no API key is configured."""
        return self.mock_llm or not self.llm_api_key


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
