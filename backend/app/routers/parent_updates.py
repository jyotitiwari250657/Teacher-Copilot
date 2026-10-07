"""Parent updates: generate, edit, approve, and (only then) send.

The approval gate is enforced here AND again inside ``services.messaging``, so
there is no route through the API that can send a message a teacher has not
approved.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..agents.base import AgentError
from ..agents.parent_update import agent as parent_agent
from ..db import get_session
from ..dependencies import get_current_teacher, rate_limit
from ..models import (
    GradeResult,
    ParentMessage,
    SchoolClass,
    Student,
    Teacher,
    WorkflowRun,
)
from ..routers.classes import get_owned_class
from ..schemas import ParentMessageUpdate, ParentUpdateRequest, SendRequest
from ..services import messaging
from ..services.analytics import log_time_saved
from ..services.privacy import make_refs

router = APIRouter(prefix="/parent-updates", tags=["parent updates"])

# Statuses from which a teacher may still approve.
APPROVABLE = {"draft", "needs_review"}


def _owned_message(
    message_id: int, teacher: Teacher, session: Session
) -> ParentMessage:
    message = session.get(ParentMessage, message_id)
    if message is None or message.teacher_id != teacher.id:
        raise HTTPException(status_code=404, detail="Message not found.")
    return message


def _fill_tokens(body: str, student: Student, teacher: Teacher) -> str:
    """Replace the placeholders the agent was required to leave in place."""
    return (
        body.replace("{{student_name}}", student.name)
        .replace("{{parent_name}}", student.parent_name or "Parent")
        .replace("{{teacher_name}}", teacher.name)
        .replace("{{school_name}}", teacher.school_name or "the school")
        .replace("{{topic}}", "")
    )


def _latest_scores(student_id: int, session: Session) -> list[dict[str, Any]]:
    results = session.exec(
        select(GradeResult)
        .where(GradeResult.student_id == student_id)
        .order_by(GradeResult.created_at.desc())
    ).all()
    seen_assessment = set()
    out: list[dict[str, Any]] = []
    for result in results:
        if result.assessment_id in seen_assessment:
            continue
        seen_assessment.add(result.assessment_id)
        out.append({"topic": result.assessment_id, "percentage": result.percentage})
        if len(out) >= 3:
            break
    return out


def _message_out(message: ParentMessage, session: Session) -> dict[str, Any]:
    student = session.get(Student, message.student_id) if message.student_id else None
    return {
        "id": message.id,
        "student_id": message.student_id,
        "student_name": student.name if student else None,
        "class_id": message.class_id,
        "workflow_run_id": message.workflow_run_id,
        "channel": message.channel,
        "language": message.language,
        "tone": message.tone,
        "subject": message.subject,
        "body": message.body,
        "word_count": message.word_count,
        "status": message.status,
        "needs_teacher_review": message.needs_teacher_review,
        "review_reasons": message.review_reasons or [],
        "sent_at": message.sent_at.isoformat() if message.sent_at else None,
        "created_at": message.created_at.isoformat() if message.created_at else None,
        "parent_name": student.parent_name if student else "",
        "parent_phone": student.parent_phone if student else "",
        "parent_email": student.parent_email if student else "",
        "ai_generated": True,
        "can_send": message.status == "approved",
    }


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------
@router.post("/generate")
def generate_messages(
    payload: ParentUpdateRequest,
    teacher: Teacher = Depends(rate_limit()),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Generate one message per student in the class (or a chosen subset)."""
    school_class = get_owned_class(payload.class_id, teacher, session)
    students = list(
        session.exec(
            select(Student).where(Student.class_id == school_class.id)
        ).all()
    )
    if payload.student_ids:
        wanted = set(payload.student_ids)
        students = [s for s in students if s.id in wanted]
    if not students:
        raise HTTPException(status_code=400, detail="No students to write messages for.")

    refs = make_refs(students)
    language = payload.language or teacher.preferred_language or "English"
    messages, failures = [], []

    for student in students:
        scores = _latest_scores(student.id, session)
        overall = (
            round(sum(s["percentage"] for s in scores) / len(scores), 1) if scores else None
        )
        try:
            output = parent_agent.run(
                {
                    "student_ref": refs.get(student.id, "S00"),
                    "recent_scores": scores,
                    "overall_percentage": overall,
                    "attendance_pct": student.attendance_pct,
                    "subject": school_class.subject or teacher.subject,
                    "teacher_notes": payload.teacher_note or student.teacher_notes,
                    "tone": payload.tone,
                    "language": language,
                    "channel": payload.channel,
                    "teacher_name": teacher.name,
                    "school_name": teacher.school_name,
                    "topic": payload.topic,
                },
                session=session,
                teacher_id=teacher.id,
            )
        except AgentError as exc:
            failures.append({"student": student.name, "error": str(exc)})
            continue

        message = ParentMessage(
            teacher_id=teacher.id,
            student_id=student.id,
            class_id=school_class.id,
            channel=payload.channel,
            language=language,
            tone=payload.tone,
            subject=output.subject_line,
            body=_fill_tokens(output.body, student, teacher),
            word_count=output.word_count,
            status="needs_review" if output.needs_teacher_review else "draft",
            needs_teacher_review=output.needs_teacher_review,
            review_reasons=output.review_reasons,
        )
        session.add(message)
        session.commit()
        session.refresh(message)
        messages.append(_message_out(message, session))

    log_time_saved(
        session, teacher_id=teacher.id, task_type="parent_message", count=len(messages)
    )
    return {
        "class_id": school_class.id,
        "generated": len(messages),
        "failed": len(failures),
        "failures": failures,
        "messages": messages,
        "requires_approval": True,
    }


@router.get("")
def list_messages(
    class_id: Optional[int] = None,
    status: Optional[str] = None,
    teacher: Teacher = Depends(get_current_teacher),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    statement = select(ParentMessage).where(ParentMessage.teacher_id == teacher.id)
    if class_id is not None:
        statement = statement.where(ParentMessage.class_id == class_id)
    if status:
        statement = statement.where(ParentMessage.status == status)
    rows = session.exec(
        statement.order_by(ParentMessage.created_at.desc())
    ).all()
    return [_message_out(m, session) for m in rows]


@router.get("/{message_id}")
def get_message(
    message_id: int,
    teacher: Teacher = Depends(get_current_teacher),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return _message_out(_owned_message(message_id, teacher, session), session)


@router.patch("/{message_id}")
def edit_message(
    message_id: int,
    payload: ParentMessageUpdate,
    teacher: Teacher = Depends(get_current_teacher),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Teacher edits. Editing an approved message revokes approval."""
    message = _owned_message(message_id, teacher, session)
    data = payload.model_dump(exclude_unset=True)

    if data.get("body") is not None:
        message.body = data["body"]
        message.word_count = len(message.body.split())
    if data.get("subject") is not None:
        message.subject = data["subject"]
    if data.get("language"):
        message.language = data["language"]

    if message.status in ("approved", "simulated_sent", "sent"):
        # Changing the text after approval invalidates that approval.
        message.status = "draft"
        message.sent_at = None

    session.add(message)
    session.commit()
    session.refresh(message)
    return _message_out(message, session)


# ---------------------------------------------------------------------------
# Approval + sending
# ---------------------------------------------------------------------------
@router.post("/{message_id}/approve")
def approve_message(
    message_id: int,
    teacher: Teacher = Depends(get_current_teacher),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Explicit teacher approval. This is the ONLY path to ``approved``."""
    message = _owned_message(message_id, teacher, session)
    if message.status not in APPROVABLE:
        raise HTTPException(
            status_code=409,
            detail=f"This message is '{message.status}' and cannot be approved again.",
        )
    if not message.body.strip():
        raise HTTPException(status_code=400, detail="Cannot approve an empty message.")

    message.status = "approved"
    session.add(message)
    session.commit()
    session.refresh(message)
    return _message_out(message, session)


@router.post("/approve-all")
def approve_all(
    class_id: int,
    teacher: Teacher = Depends(get_current_teacher),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Bulk-approve every draft/needs-review message in a class."""
    get_owned_class(class_id, teacher, session)
    rows = session.exec(
        select(ParentMessage).where(
            ParentMessage.class_id == class_id,
            ParentMessage.teacher_id == teacher.id,
            ParentMessage.status.in_(list(APPROVABLE)),
        )
    ).all()
    for message in rows:
        if message.body.strip():
            message.status = "approved"
            session.add(message)
    session.commit()
    return {"approved": len(rows)}


@router.post("/send")
def send_messages(
    payload: SendRequest,
    teacher: Teacher = Depends(get_current_teacher),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Send approved messages. Unapproved ones are refused, loudly."""
    targets: list[ParentMessage] = []

    if payload.send_all:
        # Every approved message for this teacher.
        targets = list(
            session.exec(
                select(ParentMessage).where(
                    ParentMessage.teacher_id == teacher.id,
                    ParentMessage.status == "approved",
                )
            ).all()
        )
    elif payload.message_ids:
        targets = [_owned_message(mid, teacher, session) for mid in payload.message_ids]

    if not targets:
        return {
            "sent": 0,
            "blocked": 0,
            "results": [],
            "detail": "No approved messages to send. Approve messages first.",
        }

    sent, blocked, results = 0, 0, []
    for message in targets:
        student = session.get(Student, message.student_id) if message.student_id else None
        try:
            result = messaging.send_message(
                message,
                to_email=student.parent_email if student else "",
                to_phone=student.parent_phone if student else "",
            )
        except messaging.SendNotAllowed as exc:
            blocked += 1
            results.append(
                {
                    "id": message.id,
                    "sent": False,
                    "status": message.status,
                    "detail": str(exc),
                }
            )
            continue

        message.status = result.status
        if result.ok:
            message.sent_at = datetime.now(timezone.utc)
            sent += 1
        else:
            message.status = "failed"
        session.add(message)
        results.append(
            {
                "id": message.id,
                "sent": result.ok,
                "status": message.status,
                "detail": result.detail,
                "provider": result.provider,
            }
        )

    session.commit()
    return {"sent": sent, "blocked": blocked, "results": results}


@router.get("/inbox/pending")
def approval_inbox(
    class_id: Optional[int] = None,
    teacher: Teacher = Depends(get_current_teacher),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Everything still waiting on the teacher, from every workflow."""
    statements = select(ParentMessage).where(
        ParentMessage.teacher_id == teacher.id,
        ParentMessage.status.in_(list(APPROVABLE)),
    )
    if class_id is not None:
        statements = statements.where(ParentMessage.class_id == class_id)
    messages = session.exec(
        statements.order_by(ParentMessage.needs_teacher_review.desc(), ParentMessage.created_at.desc())
    ).all()

    items: list[dict[str, Any]] = []
    for message in messages:
        student = session.get(Student, message.student_id) if message.student_id else None
        run = (
            session.get(WorkflowRun, message.workflow_run_id)
            if message.workflow_run_id
            else None
        )
        items.append(
            {
                "kind": "parent_message",
                "id": message.id,
                "title": f"Message to {student.parent_name if student else 'parent'}",
                "subtitle": f"About {student.name if student else 'a student'} - {message.channel}",
                "status": message.status,
                "needs_review": message.needs_teacher_review,
                "reasons": message.review_reasons or [],
                "preview": message.body[:220],
                "created_at": message.created_at.isoformat() if message.created_at else None,
                "workflow_run_id": message.workflow_run_id,
                "workflow_topic": run.topic if run else None,
            }
        )
    return {"count": len(items), "items": items}