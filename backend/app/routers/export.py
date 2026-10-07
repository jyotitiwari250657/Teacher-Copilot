"""PDF / DOCX export endpoints."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlmodel import Session

from ..db import get_session
from ..dependencies import get_current_teacher
from ..models import DifferentiatedMaterial, LessonPlan, Teacher
from ..services.export import (
    lesson_plan_to_docx,
    lesson_plan_to_pdf,
    worksheet_to_docx,
    worksheet_to_pdf,
)

router = APIRouter(prefix="/export", tags=["export"])

MEDIA_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def _safe_filename(text: str, fmt: str) -> str:
    import re

    stem = re.sub(r"[^A-Za-z0-9 _-]+", "", text).strip().replace(" ", "_")[:60]
    return f"{stem or 'teachercopilot'}.{fmt}"


@router.get("/lesson/{plan_id}")
def export_lesson(
    plan_id: int,
    format: Literal["pdf", "docx"] = Query("pdf"),
    teacher: Teacher = Depends(get_current_teacher),
    session: Session = Depends(get_session),
) -> Response:
    plan = session.get(LessonPlan, plan_id)
    if plan is None or plan.teacher_id != teacher.id:
        raise HTTPException(status_code=404, detail="Lesson plan not found.")

    subtitle = f"{plan.subject} | Class {plan.grade or '-'} | {plan.board} | {plan.duration_minutes} min | {plan.language}"
    if format == "pdf":
        content = lesson_plan_to_pdf(plan.content or {}, subtitle=subtitle)
    else:
        content = lesson_plan_to_docx(plan.content or {}, subtitle=subtitle)

    return Response(
        content=content,
        media_type=MEDIA_TYPES[format],
        headers={
            "Content-Disposition": f'attachment; filename="{_safe_filename(plan.title, format)}"'
        },
    )


@router.get("/worksheet/{material_id}")
def export_worksheet(
    material_id: int,
    format: Literal["pdf", "docx"] = Query("pdf"),
    level: Literal["support", "core", "extension"] = Query("core"),
    include_answers: bool = Query(False),
    teacher: Teacher = Depends(get_current_teacher),
    session: Session = Depends(get_session),
) -> Response:
    """Export one level's worksheet. ``include_answers`` adds the answer key."""
    material = session.get(DifferentiatedMaterial, material_id)
    if material is None or material.teacher_id != teacher.id:
        raise HTTPException(status_code=404, detail="Material not found.")

    content = material.content or {}
    level_material = content.get(level)
    if not level_material:
        raise HTTPException(status_code=404, detail=f"No '{level}' material in this set.")

    payload: dict[str, Any] = dict(level_material)
    payload["topic"] = material.topic
    subtitle = f"{material.topic} | Class {material.class_id or '-'} | {level.title()} level"
    label = {"support": "Support", "core": "Core", "extension": "Extension"}[level]

    if format == "pdf":
        data = worksheet_to_pdf(
            level, payload, subtitle=subtitle, include_answers=include_answers
        )
    else:
        data = worksheet_to_docx(
            level, payload, subtitle=subtitle, include_answers=include_answers
        )

    return Response(
        content=data,
        media_type=MEDIA_TYPES[format],
        headers={
            "Content-Disposition": f'attachment; filename="{_safe_filename(f"{material.topic}_{label}_worksheet", format)}"'
        },
    )


@router.get("/lesson/{plan_id}/preview")
def preview_lesson(
    plan_id: int,
    teacher: Teacher = Depends(get_current_teacher),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Plain-text preview so the UI can show what will be exported."""
    plan = session.get(LessonPlan, plan_id)
    if plan is None or plan.teacher_id != teacher.id:
        raise HTTPException(status_code=404, detail="Lesson plan not found.")
    content = plan.content or {}
    return {
        "title": plan.title,
        "sections": [
            {"heading": "Learning objectives", "items": content.get("learning_objectives", [])},
            {"heading": "Materials", "items": content.get("materials", [])},
            {
                "heading": "Lesson flow",
                "items": [
                    f"{item.get('phase', '').title()} ({item.get('minutes', 0)} min): "
                    + "; ".join(item.get("teacher_actions", []))
                    for item in content.get("lesson_flow", [])
                ],
            },
            {"heading": "Homework", "items": [content.get("homework", "")]},
            {"heading": "Exit ticket", "items": content.get("exit_ticket", [])},
        ],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }