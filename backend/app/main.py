"""TeacherCopilot API entry point.

Run with:
    uvicorn app.main:app --reload --port 8000
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import settings
from .db import Session, create_db_and_tables, engine
from .llm import provider_info
from .routers import (
    auth,
    classes,
    dashboard,
    differentiation,
    export,
    grading,
    lessons,
    parent_updates,
    students,
    workflow,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("teachercopilot")


def bootstrap() -> dict:
    """Create tables and seed the demo dataset on first run."""
    create_db_and_tables()
    result: dict = {"seeded": None}
    if settings.seed_demo:
        from .services.seed import seed_demo_data

        with Session(engine) as session:
            result["seeded"] = seed_demo_data(session)
    return result


@asynccontextmanager
async def lifespan(app: FastAPI):
    info = bootstrap()
    provider = provider_info()
    logger.info("TeacherCopilot API starting")
    logger.info("  LLM: %s (%s) | mock=%s", provider["model"], provider["base_url"], provider["mock_mode"])
    logger.info("  Messaging mode: %s", settings.messaging_mode)
    logger.info("  Seed: %s", info.get("seeded"))
    if not info.get("seeded", {}).get("created") and settings.seed_demo:
        logger.info("  Demo login: %s / %s", settings.demo_teacher_email, settings.demo_teacher_password)
    yield


app = FastAPI(
    title="TeacherCopilot API",
    version="1.0.0",
    description=(
        "Agentic AI assistant for school teachers. Four specialist agents "
        "(lesson planner, grader, differentiator, parent-update writer) run "
        "under a central orchestrator. **Every AI output is a draft until a "
        "teacher approves it, and nothing is ever sent to a parent without "
        "explicit approval.**"
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Error handling - friendly, never a bare stack trace
# ---------------------------------------------------------------------------
@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    problems = []
    for error in exc.errors():
        location = ".".join(str(p) for p in error.get("loc", ()) if p != "body")
        problems.append(f"{location or 'request'}: {error.get('msg', 'invalid value')}")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={
            "detail": "Please check the highlighted fields.",
            "problems": problems[:10],
        },
    )


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": str(exc)},
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
for router in (
    auth.router,
    classes.router,
    students.router,
    lessons.router,
    grading.router,
    differentiation.router,
    parent_updates.router,
    dashboard.router,
    workflow.router,
    export.router,
):
    app.include_router(router)


@app.get("/api/health", tags=["meta"])
def health() -> dict:
    """Liveness + configuration summary (no secrets)."""
    return {
        "status": "ok",
        "app": settings.app_name,
        "llm": provider_info(),
        "messaging_mode": settings.messaging_mode,
        "database": "sqlite" if settings.database_url.startswith("sqlite") else "other",
    }


@app.get("/", include_in_schema=False)
def root() -> dict:
    return {
        "name": "TeacherCopilot",
        "docs": "/docs",
        "health": "/api/health",
        "note": "AI outputs are drafts. Teacher approval is required before "
        "anything is final or sent to a parent.",
    }