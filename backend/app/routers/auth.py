"""Authentication endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from ..config import settings
from ..db import get_session
from ..dependencies import get_current_teacher
from ..llm import provider_info
from ..models import Teacher
from ..schemas import LoginRequest, TeacherOut, TeacherUpdate, TokenResponse
from ..security import create_access_token, verify_password
from ..services import messaging

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, session: Session = Depends(get_session)) -> TokenResponse:
    teacher = session.exec(
        select(Teacher).where(Teacher.email == payload.email.strip().lower())
    ).first()
    if teacher is None or not verify_password(payload.password, teacher.hashed_password):
        # Same message either way - do not leak which part was wrong.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
        )
    token = create_access_token(
        teacher.id, extra={"email": teacher.email, "name": teacher.name}
    )
    return TokenResponse(access_token=token, teacher=TeacherOut.model_validate(teacher))


@router.get("/me", response_model=TeacherOut)
def me(teacher: Teacher = Depends(get_current_teacher)) -> TeacherOut:
    return TeacherOut.model_validate(teacher)


@router.patch("/me", response_model=TeacherOut)
def update_me(
    payload: TeacherUpdate,
    teacher: Teacher = Depends(get_current_teacher),
    session: Session = Depends(get_session),
) -> TeacherOut:
    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(teacher, field, value)
    session.add(teacher)
    session.commit()
    session.refresh(teacher)
    return TeacherOut.model_validate(teacher)


@router.get("/config")
def public_config(teacher: Teacher = Depends(get_current_teacher)) -> dict:
    """Non-secret runtime config, for the Settings page and the demo banner."""
    return {
        "llm": provider_info(),
        "messaging": messaging.provider_summary(),
        "app_name": settings.app_name,
        "time_saved_estimates": {
            "lesson_plan_minutes": settings.minutes_lesson_plan,
            "grading_minutes_per_paper": settings.minutes_grading_per_paper,
            "differentiation_minutes": settings.minutes_differentiated_worksheets,
            "parent_message_minutes": settings.minutes_parent_message,
        },
        "rate_limit": {
            "max_calls": settings.rate_limit_max_calls,
            "window_seconds": settings.rate_limit_window_seconds,
        },
    }