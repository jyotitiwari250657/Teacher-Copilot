"""Lesson plan generation and approval."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlmodel import Session, select

from ..agents.base import AgentError
from ..agents.lesson_planner import agent as lesson_agent
from ..db import get_session
from ..dependencies import get_current_teacher, rate_limit
from ..models import LessonPlan, SchoolClass, Teacher
from ..schemas import LessonPlanRequest, LessonPlanUpdate
from ..services.analytics import log_time_saved

router = APIRouter(prefix="/lessons", tags=["lessons"])


def _owned_plan(plan_id: int, teacher: Teacher, session: Session) -> LessonPlan:
    plan = session.get(LessonPlan, plan_id)
    if plan is None or plan.teacher_id != teacher.id:
        raise HTTPException(status_code=404, detail="Lesson plan not found.")
    return plan


def _grade_for(plan: LessonPlan, session: Session) -> str:
    if plan.class_id:
        school_class = session.get(SchoolClass, plan.class_id)
        if school_class and school_class.grade:
            return school_class.grade
    return plan.grade


def _plan_out(plan: LessonPlan) -> dict[str, Any]:
    return {
        "id": plan.id,
        "teacher_id": plan.teacher_id,
        "class_id": plan.class_id,
        "title": plan.title,
        "subject": plan.subject,
        "grade": plan.grade,
        "topic": plan.topic,
        "board": plan.board,
        "language": plan.language,
        "duration_minutes": plan.duration_minutes,
        "content": plan.content,
        "status": plan.status,
        "created_at": plan.created_at.isoformat() if plan.created_at else None,
        "approved_at": plan.approved_at.isoformat() if plan.approved_at else None,
        "ai_generated": True,
    }


@router.post("/generate")
def generate_lesson(
    payload: LessonPlanRequest,
    teacher: Teacher = Depends(rate_limit()),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Run the Lesson Planner agent and store the result as a draft."""
    grade = payload.grade
    if payload.class_id:
        school_class = session.get(SchoolClass, payload.class_id)
        if school_class is None or school_class.teacher_id != teacher.id:
            raise HTTPException(status_code=404, detail="Class not found.")
        grade = grade or school_class.grade

    try:
        output = lesson_agent.run(
            {
                "subject": payload.subject,
                "grade": grade,
                "topic": payload.topic,
                "duration_minutes": payload.duration_minutes,
                "board": payload.board,
                "language": payload.language,
                "learning_objectives": payload.learning_objectives,
                "class_level_notes": payload.class_level_notes,
            },
            session=session,
            teacher_id=teacher.id,
        )
    except AgentError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    content = output.model_dump()
    plan = LessonPlan(
        teacher_id=teacher.id,
        class_id=payload.class_id,
        title=output.title,
        subject=payload.subject,
        grade=grade,
        topic=payload.topic,
        board=payload.board,
        language=payload.language,
        duration_minutes=payload.duration_minutes,
        content=content,
        status="draft",
    )
    session.add(plan)
    session.commit()
    session.refresh(plan)

    log_time_saved(
        session, teacher_id=teacher.id, task_type="lesson_plan", count=1
    )
    return _plan_out(plan)


@router.get("")
def list_lessons(
    class_id: Optional[int] = None,
    teacher: Teacher = Depends(get_current_teacher),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    statement = select(LessonPlan).where(LessonPlan.teacher_id == teacher.id)
    if class_id is not None:
        statement = statement.where(LessonPlan.class_id == class_id)
    plans = session.exec(statement.order_by(LessonPlan.created_at.desc())).all()
    return [_plan_out(p) for p in plans]


@router.get("/{plan_id}")
def get_lesson(
    plan_id: int,
    teacher: Teacher = Depends(get_current_teacher),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return _plan_out(_owned_plan(plan_id, teacher, session))


@router.patch("/{plan_id}")
def update_lesson(
    plan_id: int,
    payload: LessonPlanUpdate,
    teacher: Teacher = Depends(get_current_teacher),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    plan = _owned_plan(plan_id, teacher, session)
    data = payload.model_dump(exclude_unset=True)
    if "content" in data and data["content"]:
        plan.content = data["content"]
        plan.title = data["content"].get("title", plan.title)
    if data.get("title"):
        plan.title = data["title"]
    if "status" in data and data["status"]:
        plan.status = data["status"]
        plan.approved_at = (
            datetime.now(timezone.utc) if plan.status == "approved" else None
        )
    session.add(plan)
    session.commit()
    session.refresh(plan)
    return _plan_out(plan)


@router.post("/{plan_id}/approve")
def approve_lesson(
    plan_id: int,
    teacher: Teacher = Depends(get_current_teacher),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Teacher sign-off. Until this is called the plan is a draft."""
    plan = _owned_plan(plan_id, teacher, session)
    plan.status = "approved"
    plan.approved_at = datetime.now(timezone.utc)
    session.add(plan)
    session.commit()
    session.refresh(plan)
    return _plan_out(plan)


@router.post("/{plan_id}/regenerate")
def regenerate_lesson(
    plan_id: int,
    teacher: Teacher = Depends(rate_limit()),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Re-run the agent on the same inputs and replace the draft content."""
    plan = _owned_plan(plan_id, teacher, session)
    grade = _grade_for(plan, session)
    try:
        output = lesson_agent.run(
            {
                "subject": plan.subject,
                "grade": grade,
                "topic": plan.topic,
                "duration_minutes": plan.duration_minutes,
                "board": plan.board,
                "language": plan.language,
                "learning_objectives": plan.content.get("learning_objectives", []),
                "class_level_notes": "",
            },
            session=session,
            teacher_id=teacher.id,
        )
    except AgentError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    plan.content = output.model_dump()
    plan.title = output.title
    plan.status = "draft"
    plan.approved_at = None
    session.add(plan)
    session.commit()
    session.refresh(plan)
    return _plan_out(plan)