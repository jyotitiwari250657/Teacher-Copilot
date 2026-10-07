"""Time-saved accounting and dashboard aggregation."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlmodel import Session, select

from ..config import settings
from ..models import (
    DifferentiatedMaterial,
    GradeResult,
    LessonPlan,
    ParentMessage,
    SchoolClass,
    Student,
    TimeSavedLog,
)

TASK_LABELS = {
    "lesson_plan": "Lesson plans",
    "grading": "Grading",
    "differentiation": "Differentiated worksheets",
    "parent_message": "Parent messages",
}


def log_time_saved(
    session: Session,
    *,
    teacher_id: int,
    task_type: str,
    count: int = 1,
    minutes: Optional[int] = None,
) -> TimeSavedLog:
    """Record minutes a task saved the teacher."""
    if minutes is None:
        minutes = _minutes_for(task_type) * max(1, count)
    entry = TimeSavedLog(
        teacher_id=teacher_id,
        task_type=task_type,
        task_count=count,
        minutes_saved=minutes,
    )
    session.add(entry)
    session.commit()
    session.refresh(entry)
    return entry


def _minutes_for(task_type: str) -> int:
    return {
        "lesson_plan": settings.minutes_lesson_plan,
        "grading": settings.minutes_grading_per_paper,
        "differentiation": settings.minutes_differentiated_worksheets,
        "parent_message": settings.minutes_parent_message,
    }.get(task_type, 0)


def _start_of_week(reference: datetime) -> datetime:
    """Monday 00:00 UTC of the week containing ``reference``."""
    midnight = reference.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight - timedelta(days=midnight.weekday())


def weekly_time_saved(session: Session, teacher_id: int, weeks: int = 6) -> list[dict[str, Any]]:
    """Minutes saved per week, oldest first, with empty weeks filled in."""
    now = datetime.now(timezone.utc)
    this_week = _start_of_week(now)
    start = this_week - timedelta(weeks=weeks - 1)

    rows = session.exec(
        select(TimeSavedLog).where(
            TimeSavedLog.teacher_id == teacher_id,
            TimeSavedLog.created_at >= start,
        )
    ).all()

    buckets: dict[str, int] = {}
    for row in rows:
        key = _start_of_week(row.created_at).strftime("%Y-%m-%d")
        buckets[key] = buckets.get(key, 0) + row.minutes_saved

    points: list[dict[str, Any]] = []
    for i in range(weeks):
        day = start + timedelta(weeks=i)
        label_day = day.strftime("%d %b")
        points.append(
            {
                "week": f"{label_day}",
                "week_start": day.strftime("%Y-%m-%d"),
                "minutes": buckets.get(day.strftime("%Y-%m-%d"), 0),
                "is_current": i == weeks - 1,
            }
        )
    return points


def minutes_this_week(session: Session, teacher_id: int) -> int:
    start = _start_of_week(datetime.now(timezone.utc))
    rows = session.exec(
        select(TimeSavedLog).where(
            TimeSavedLog.teacher_id == teacher_id,
            TimeSavedLog.created_at >= start,
        )
    ).all()
    return sum(r.minutes_saved for r in rows)


def minutes_all_time(session: Session, teacher_id: int) -> int:
    rows = session.exec(
        select(TimeSavedLog).where(TimeSavedLog.teacher_id == teacher_id)
    ).all()
    return sum(r.minutes_saved for r in rows)


def class_performance(session: Session, teacher_id: int) -> list[dict[str, Any]]:
    """Average score per class, for the dashboard overview."""
    classes = session.exec(
        select(SchoolClass).where(SchoolClass.teacher_id == teacher_id)
    ).all()

    overview: list[dict[str, Any]] = []
    for school_class in classes:
        student_ids = list(
            session.exec(select(Student.id).where(Student.class_id == school_class.id)).all()
        )
        results = (
            session.exec(
                select(GradeResult).where(
                    GradeResult.teacher_id == teacher_id,
                    GradeResult.approved.is_(True),
                    GradeResult.student_id.in_(student_ids),
                )
            ).all()
            if student_ids
            else []
        )
        average = (
            round(sum(r.percentage for r in results) / len(results), 1)
            if results
            else 0.0
        )
        overview.append(
            {
                "class_id": school_class.id,
                "name": school_class.name,
                "subject": school_class.subject,
                "student_count": len(student_ids),
                "graded_students": len(results),
                "average_percentage": average,
                "lesson_plans": len(
                    session.exec(
                        select(LessonPlan).where(LessonPlan.class_id == school_class.id)
                    ).all()
                ),
                "messages_sent": len(
                    session.exec(
                        select(ParentMessage).where(
                            ParentMessage.class_id == school_class.id,
                            ParentMessage.status.in_(["sent", "simulated_sent"]),
                        )
                    ).all()
                ),
            }
        )
    return overview


def dashboard_summary(session: Session, teacher_id: int) -> dict[str, Any]:
    """Everything the dashboard needs, in one query pass."""
    lesson_plans = session.exec(
        select(LessonPlan).where(LessonPlan.teacher_id == teacher_id)
    ).all()
    grade_results = session.exec(
        select(GradeResult).where(GradeResult.teacher_id == teacher_id)
    ).all()
    approved_grades = [g for g in grade_results if g.approved]
    materials = session.exec(
        select(DifferentiatedMaterial).where(DifferentiatedMaterial.teacher_id == teacher_id)
    ).all()
    messages = session.exec(
        select(ParentMessage).where(ParentMessage.teacher_id == teacher_id)
    ).all()
    sent = [m for m in messages if m.status in ("sent", "simulated_sent")]
    pending = [m for m in messages if m.status in ("draft", "needs_review", "approved")]

    # Papers graded = distinct assessments that have at least one result.
    papers_graded = len({g.assessment_id for g in grade_results if g.assessment_id})

    by_task: dict[str, int] = {}
    for row in session.exec(
        select(TimeSavedLog).where(TimeSavedLog.teacher_id == teacher_id)
    ).all():
        by_task[row.task_type] = by_task.get(row.task_type, 0) + row.minutes_saved

    return {
        "lesson_plans_created": len(lesson_plans),
        "lesson_plans_approved": len([p for p in lesson_plans if p.status == "approved"]),
        "papers_graded": papers_graded,
        "students_graded": len(approved_grades),
        "results_needing_review": len([g for g in grade_results if g.needs_teacher_review and not g.approved]),
        "messages_sent": len(sent),
        "messages_pending": len(pending),
        "worksheets_created": len(materials),
        "time_saved_this_week_minutes": minutes_this_week(session, teacher_id),
        "time_saved_all_time_minutes": minutes_all_time(session, teacher_id),
        "time_saved_by_task": by_task,
        "weekly_time_saved": weekly_time_saved(session, teacher_id),
        "class_overview": class_performance(session, teacher_id),
        "recent_activity": _recent_activity(session, teacher_id),
        "approval_inbox_count": _inbox_count(session, teacher_id),
    }


def _inbox_count(session: Session, teacher_id: int) -> int:
    """Items waiting for the teacher's explicit approval."""
    messages = session.exec(
        select(ParentMessage).where(ParentMessage.teacher_id == teacher_id)
    ).all()
    messages_pending = len([m for m in messages if m.status in ("draft", "needs_review")])
    plans_pending = len(
        session.exec(
            select(LessonPlan).where(
                LessonPlan.teacher_id == teacher_id, LessonPlan.status == "draft"
            )
        ).all()
    )
    grades_pending = len(
        session.exec(
            select(GradeResult).where(
                GradeResult.teacher_id == teacher_id, GradeResult.approved.is_(False)
            )
        ).all()
    )
    return messages_pending + plans_pending + grades_pending


def _recent_activity(session: Session, teacher_id: int, limit: int = 8) -> list[dict[str, Any]]:
    from ..models import WorkflowRun

    events: list[dict[str, Any]] = []

    for row in session.exec(
        select(TimeSavedLog)
        .where(TimeSavedLog.teacher_id == teacher_id)
        .order_by(TimeSavedLog.created_at.desc())
        .limit(limit)
    ).all():
        events.append(
            {
                "kind": "time_saved",
                "label": TASK_LABELS.get(row.task_type, row.task_type),
                "detail": f"Saved about {row.minutes_saved // 60}h {row.minutes_saved % 60}m",
                "at": row.created_at.isoformat(),
            }
        )

    for row in session.exec(
        select(ParentMessage)
        .where(ParentMessage.teacher_id == teacher_id)
        .order_by(ParentMessage.created_at.desc())
        .limit(limit)
    ).all():
        events.append(
            {
                "kind": "message",
                "label": "Parent message",
                "detail": f"{row.channel} - {row.status.replace('_', ' ')}",
                "at": row.created_at.isoformat(),
            }
        )

    for row in session.exec(
        select(WorkflowRun)
        .where(WorkflowRun.teacher_id == teacher_id)
        .order_by(WorkflowRun.created_at.desc())
        .limit(limit)
    ).all():
        events.append(
            {
                "kind": "workflow",
                "label": "Weekly workflow",
                "detail": f"{row.topic} - {row.status.replace('_', ' ')}",
                "at": (row.finished_at or row.started_at or row.created_at).isoformat(),
            }
        )

    events.sort(key=lambda e: e["at"], reverse=True)
    return events[:limit]


def humanise_minutes(minutes: int) -> str:
    """'3h 20m' / '45m' - used by the API and the UI."""
    minutes = int(minutes or 0)
    if minutes < 60:
        return f"{minutes}m"
    hours, remainder = divmod(minutes, 60)
    return f"{hours}h" if remainder == 0 else f"{hours}h {remainder}m"