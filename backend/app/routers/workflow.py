"""Weekly workflow: run the whole agent pipeline and stream its progress."""
from __future__ import annotations

import asyncio
import json
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select

from ..db import get_session
from ..dependencies import get_current_teacher, rate_limit
from ..models import (
    AgentLog,
    DifferentiatedMaterial,
    GradeResult,
    LessonPlan,
    ParentMessage,
    Teacher,
    WorkflowRun,
    WorkflowStep,
)
from ..orchestrator import STEPS, Orchestrator, rerun_step, start_workflow
from ..routers.classes import get_owned_class
from ..schemas import WorkflowRequest

router = APIRouter(prefix="/workflow", tags=["workflow"])


def _owned_run(run_id: int, teacher: Teacher, session: Session) -> WorkflowRun:
    run = session.get(WorkflowRun, run_id)
    if run is None or run.teacher_id != teacher.id:
        raise HTTPException(status_code=404, detail="Workflow run not found.")
    return run


def _run_out(run: WorkflowRun, session: Session, *, with_logs: bool = True) -> dict[str, Any]:
    steps = session.exec(
        select(WorkflowStep)
        .where(WorkflowStep.run_id == run.id)
        .order_by(WorkflowStep.id)
    ).all()

    payloads: list[dict[str, Any]] = []
    for step in steps:
        payloads.append(
            {
                "id": step.id,
                "step_number": step.step_number,
                "step_key": step.step_key,
                "title": step.title,
                "agent": step.agent,
                "status": step.status,
                "detail": step.detail,
                "output": step.output or {},
                "duration_ms": step.duration_ms,
                "started_at": step.started_at.isoformat() if step.started_at else None,
                "finished_at": step.finished_at.isoformat() if step.finished_at else None,
            }
        )

    logs: list[dict[str, Any]] = []
    if with_logs:
        for log in session.exec(
            select(AgentLog)
            .where(AgentLog.run_id == run.id)
            .order_by(AgentLog.id)
        ).all():
            logs.append(
                {
                    "id": log.id,
                    "agent": log.agent,
                    "action": log.action,
                    "input_summary": log.input_summary[:400],
                    "output_summary": log.output_summary[:400],
                    "duration_ms": log.duration_ms,
                    "tokens": log.tokens,
                    "success": log.success,
                    "error": log.error,
                    "created_at": log.created_at.isoformat() if log.created_at else None,
                }
            )

    return {
        "id": run.id,
        "class_id": run.class_id,
        "topic": run.topic,
        "subject": run.subject,
        "language": run.language,
        "status": run.status,
        "error": run.error,
        "lesson_plan_id": run.lesson_plan_id,
        "assessment_id": run.assessment_id,
        "material_id": run.material_id,
        "context": run.context or {},
        "steps": payloads,
        "logs": logs,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
    }


def _inbox(session: Session, teacher: Teacher, run: WorkflowRun) -> dict[str, Any]:
    """Everything this run produced that still needs the teacher."""
    messages = session.exec(
        select(ParentMessage).where(
            ParentMessage.workflow_run_id == run.id,
            ParentMessage.status.in_(["draft", "needs_review", "approved"]),
        )
    ).all()
    grades = session.exec(
        select(GradeResult).where(
            GradeResult.assessment_id == run.assessment_id,
            GradeResult.approved.is_(False),
        )
    ).all() if run.assessment_id else []

    items: list[dict[str, Any]] = []

    from ..models import Student

    for message in messages:
        student = session.get(Student, message.student_id) if message.student_id else None
        items.append(
            {
                "kind": "parent_message",
                "id": message.id,
                "title": f"Message to {student.parent_name if student else 'parent'}",
                "subtitle": f"About {student.name if student else 'a student'} - {message.channel}",
                "status": message.status,
                "needs_review": message.needs_teacher_review,
                "reasons": message.review_reasons or [],
                "preview": message.body[:240],
            }
        )
    for grade in grades:
        student = session.get(Student, grade.student_id) if grade.student_id else None
        items.append(
            {
                "kind": "grade",
                "id": grade.id,
                "title": f"Marks for {student.name if student else 'a student'}",
                "subtitle": f"{grade.total:g} of {grade.max_total:g} "
                f"({grade.percentage:g}%) - not yet approved",
                "status": "needs_review" if grade.needs_teacher_review else "draft",
                "needs_review": grade.needs_teacher_review,
                "reasons": ["Teacher approval required before marks are final."]
                if not grade.needs_teacher_review
                else ["The grader was unsure about at least one answer."],
                "preview": "",
            }
        )
    if run.lesson_plan_id:
        plan = session.get(LessonPlan, run.lesson_plan_id)
        if plan and plan.status == "draft":
            items.append(
                {
                    "kind": "lesson_plan",
                    "id": plan.id,
                    "title": f"Lesson plan: {plan.title}",
                    "subtitle": "Draft - approve before you teach from it",
                    "status": "draft",
                    "needs_review": False,
                    "reasons": [],
                    "preview": "",
                }
            )
    if run.material_id:
        material = session.get(DifferentiatedMaterial, run.material_id)
        if material:
            items.append(
                {
                    "kind": "material",
                    "id": material.id,
                    "title": f"Three-level material: {material.topic}",
                    "subtitle": "Support / Core / Extension - check the groupings",
                    "status": material.status,
                    "needs_review": False,
                    "reasons": [],
                    "preview": "",
                }
            )

    return {
        "count": len(items),
        "needs_attention": len([i for i in items if i["needs_review"]]),
        "items": items,
    }


@router.post("/run")
def run_workflow(
    payload: WorkflowRequest,
    teacher: Teacher = Depends(rate_limit(max_calls=10, window=60)),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Run the full five-step pipeline. Returns the finished run."""
    get_owned_class(payload.class_id, teacher, session)

    params = {
        "duration_minutes": payload.duration_minutes,
        "board": payload.board,
        "strictness": payload.strictness,
        "tone": payload.tone,
        "channel": payload.channel,
        "use_sample_answers": payload.use_sample_answers,
    }

    if payload.duration_seconds:
        # Optional pacing so the live timeline is watchable in a demo.
        import time

        time.sleep(payload.duration_seconds)

    run = start_workflow(
        session,
        teacher,
        class_id=payload.class_id,
        topic=payload.topic,
        subject=payload.subject,
        language=payload.language,
        params=params,
    )
    result = _run_out(run, session)
    result["inbox"] = _inbox(session, teacher, run)
    return result


@router.get("/steps/definition")
def step_definitions(teacher: Teacher = Depends(get_current_teacher)) -> list[dict[str, Any]]:
    """The fixed pipeline, so the UI can render it before a run starts.

    Declared before the ``/{run_id}`` routes because ``"steps"`` is not a
    valid run id and FastAPI would reject it before trying them.
    """
    # ``step_key`` (not ``key``) so the payload matches WorkflowStep, which the
    # UI renders and re-runs by.
    return [
        {"number": index, "step_key": meta["key"], **meta}
        for index, meta in enumerate(STEPS, 1)
    ]


@router.get("/{run_id}/status")
def run_status(
    run_id: int,
    teacher: Teacher = Depends(get_current_teacher),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    run = _owned_run(run_id, teacher, session)
    return _run_out(run, session)


@router.get("/{run_id}/stream")
async def stream_run(
    run_id: int,
    teacher: Teacher = Depends(get_current_teacher),
    session: Session = Depends(get_session),
) -> StreamingResponse:
    """Server-Sent Events view of a run, for a live timeline.

    Emits a snapshot whenever the run's state changes, then closes once the
    run reaches a terminal state. (The UI also polls ``/status`` as a fallback.)
    """
    _owned_run(run_id, teacher, session)

    async def event_source():
        last_signature = ""
        for _ in range(600):  # ~5 minutes at 0.5s
            run = session.get(WorkflowRun, run_id)
            if run is None:
                break
            payload = _run_out(run, session, with_logs=False)
            signature = f"{run.status}:{len(payload['steps'])}:" + ",".join(
                f"{s['step_key']}={s['status']}" for s in payload["steps"]
            )
            if signature != last_signature:
                last_signature = signature
                yield f"event: progress\ndata: {json.dumps(payload, default=str)}\n\n"
            if run.status in ("done", "done_with_errors", "failed", "cancelled"):
                final = _run_out(run, session)
                final["inbox"] = _inbox(session, teacher, run)
                yield f"event: complete\ndata: {json.dumps(final, default=str)}\n\n"
                break
            await asyncio.sleep(0.5)
        yield "event: end\ndata: {}\n\n"

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("")
def list_runs(
    class_id: Optional[int] = None,
    teacher: Teacher = Depends(get_current_teacher),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    statement = select(WorkflowRun).where(WorkflowRun.teacher_id == teacher.id)
    if class_id is not None:
        statement = statement.where(WorkflowRun.class_id == class_id)
    runs = session.exec(statement.order_by(WorkflowRun.created_at.desc()).limit(20)).all()
    return [
        {
            "id": r.id,
            "class_id": r.class_id,
            "topic": r.topic,
            "subject": r.subject,
            "language": r.language,
            "status": r.status,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "finished_at": r.finished_at.isoformat() if r.finished_at else None,
        }
        for r in runs
    ]


@router.post("/{run_id}/steps/{step_key}/rerun")
def rerun(
    run_id: int,
    step_key: str,
    teacher: Teacher = Depends(rate_limit(max_calls=15, window=60)),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Re-run one step without touching the others."""
    run = _owned_run(run_id, teacher, session)
    valid = {meta["key"] for meta in STEPS}
    if step_key not in valid:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown step '{step_key}'. Valid steps: {', '.join(sorted(valid))}.",
        )
    step = rerun_step(session, teacher, run, step_key)
    result = _run_out(run, session)
    result["rerun_step"] = step.step_key
    result["inbox"] = _inbox(session, teacher, run)
    return result


@router.get("/{run_id}/inbox")
def run_inbox(
    run_id: int,
    teacher: Teacher = Depends(get_current_teacher),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    run = _owned_run(run_id, teacher, session)
    return _inbox(session, teacher, run)