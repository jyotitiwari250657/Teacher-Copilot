"""Differentiation: three levels of material plus student groupings."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..agents.base import AgentError
from ..agents.differentiation import agent as diff_agent
from ..db import get_session
from ..dependencies import get_current_teacher, rate_limit
from ..models import (
    DifferentiatedMaterial,
    GradeResult,
    LessonPlan,
    SchoolClass,
    Student,
    Teacher,
)
from ..routers.classes import get_owned_class
from ..schemas import DifferentiateRequest
from ..services.analytics import log_time_saved
from ..services.privacy import make_refs, ref_to_student_id

router = APIRouter(prefix="/differentiate", tags=["differentiation"])


def _class_performance(
    class_id: Optional[int], session: Session
) -> list[dict[str, Any]]:
    """Latest approved grade per student, expressed as a percentage."""
    if class_id is None:
        return []
    results = session.exec(
        select(GradeResult)
        .where(GradeResult.student_id.in_(
            list(session.exec(select(Student.id).where(Student.class_id == class_id)).all())
        ))
        .order_by(GradeResult.created_at.desc())
    ).all()

    seen: dict[int, dict[str, Any]] = {}
    for result in results:
        if result.student_id in seen:
            continue
        seen[result.student_id] = {"student_id": result.student_id, "percentage": result.percentage}
    return list(seen.values())


def _material_out(material: DifferentiatedMaterial, session: Session) -> dict[str, Any]:
    refs = (
        make_refs(list(session.exec(select(Student).where(Student.class_id == material.class_id)).all()))
        if material.class_id
        else {}
    )
    # Map the agent's pseudonymous refs back to real names, locally.
    groupings = []
    for level, student_refs in (material.groupings or {}).items():
        students: list[dict[str, Any]] = []
        for ref in student_refs or []:
            student_id = ref_to_student_id(refs, ref)
            student = session.get(Student, student_id) if student_id else None
            students.append(
                {
                    "ref": ref,
                    "student_id": student_id,
                    "name": student.name if student else ref,
                    "roll_no": student.roll_no if student else "",
                }
            )
        groupings.append({"level": level, "students": students})

    content = material.content or {}
    return {
        "id": material.id,
        "class_id": material.class_id,
        "lesson_plan_id": material.lesson_plan_id,
        "topic": material.topic,
        "language": material.language,
        "content": content,
        "support": content.get("support", {}),
        "core": content.get("core", {}),
        "extension": content.get("extension", {}),
        "groupings": groupings,
        "grouping_rationale": content.get("grouping_rationale", ""),
        "status": material.status,
        "created_at": material.created_at.isoformat() if material.created_at else None,
        "ai_generated": True,
    }


@router.post("")
def differentiate(
    payload: DifferentiateRequest,
    teacher: Teacher = Depends(rate_limit()),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Build Support / Core / Extension material and suggest groupings."""
    if payload.class_id:
        get_owned_class(payload.class_id, teacher, session)

    lesson_plan: dict[str, Any] = {}
    if payload.lesson_plan_id:
        plan = session.get(LessonPlan, payload.lesson_plan_id)
        if plan is None or plan.teacher_id != teacher.id:
            raise HTTPException(status_code=404, detail="Lesson plan not found.")
        lesson_plan = plan.content or {}
        payload.topic = payload.topic or plan.topic
        payload.language = payload.language if payload.language else plan.language

    performance = _class_performance(payload.class_id, session)
    refs = (
        make_refs(list(session.exec(select(Student).where(Student.class_id == payload.class_id)).all()))
        if payload.class_id
        else {}
    )
    # Send only pseudonymous refs to the model.
    performance_for_llm = [
        {
            "student_ref": refs.get(entry["student_id"], "S00"),
            "percentage": entry["percentage"],
        }
        for entry in performance
    ]
    manual = {refs[sid]: level for sid, level in payload.manual_levels.items() if sid in refs}

    grade = ""
    if payload.class_id:
        school_class = session.get(SchoolClass, payload.class_id)
        grade = school_class.grade if school_class else ""

    try:
        output = diff_agent.run(
            {
                "topic": payload.topic,
                "lesson_plan": lesson_plan,
                "language": payload.language,
                "performance": performance_for_llm,
                "manual_levels": manual,
                "grade": grade,
                "notes": payload.notes,
            },
            session=session,
            teacher_id=teacher.id,
        )
    except AgentError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    data = output.model_dump()
    material = DifferentiatedMaterial(
        teacher_id=teacher.id,
        class_id=payload.class_id,
        lesson_plan_id=payload.lesson_plan_id,
        topic=payload.topic,
        language=payload.language,
        content=data,
        groupings={
            grouping.level: grouping.student_refs for grouping in output.groupings
        },
        status="draft",
    )
    session.add(material)
    session.commit()
    session.refresh(material)

    log_time_saved(
        session, teacher_id=teacher.id, task_type="differentiation", count=1
    )
    return _material_out(material, session)


@router.get("")
def list_materials(
    class_id: Optional[int] = None,
    teacher: Teacher = Depends(get_current_teacher),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    statement = select(DifferentiatedMaterial).where(
        DifferentiatedMaterial.teacher_id == teacher.id
    )
    if class_id is not None:
        statement = statement.where(DifferentiatedMaterial.class_id == class_id)
    rows = session.exec(
        statement.order_by(DifferentiatedMaterial.created_at.desc())
    ).all()
    return [
        {
            "id": m.id,
            "class_id": m.class_id,
            "topic": m.topic,
            "language": m.language,
            "status": m.status,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in rows
    ]


@router.get("/{material_id}")
def get_material(
    material_id: int,
    teacher: Teacher = Depends(get_current_teacher),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    material = session.get(DifferentiatedMaterial, material_id)
    if material is None or material.teacher_id != teacher.id:
        raise HTTPException(status_code=404, detail="Material not found.")
    return _material_out(material, session)