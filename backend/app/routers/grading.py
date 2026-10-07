"""Grading: single, bulk, CSV import, teacher overrides, approval, class analysis."""
from __future__ import annotations

import csv
import io
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlmodel import Session, select

from ..agents.base import AgentError
from ..agents.grader import CONFIDENCE_THRESHOLD, agent as grader_agent
from ..db import get_session
from ..dependencies import get_current_teacher, rate_limit
from ..models import (
    Assessment,
    GradeResult,
    SchoolClass,
    Student,
    Submission,
    Teacher,
)
from ..routers.classes import get_owned_class
from ..schemas import (
    AssessmentCreate,
    AssessmentOut,
    GradeBulkRequest,
    GradeRequest,
    OverrideRequest,
    SubmissionIn,
)
from ..services.analytics import log_time_saved
from ..services.privacy import make_refs, ref_to_student_id

router = APIRouter(prefix="/grading", tags=["grading"])


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _owned_assessment(
    assessment_id: int, teacher: Teacher, session: Session
) -> Assessment:
    assessment = session.get(Assessment, assessment_id)
    if assessment is None or assessment.teacher_id != teacher.id:
        raise HTTPException(status_code=404, detail="Assessment not found.")
    return assessment


def _class_students(class_id: int, session: Session) -> list[Student]:
    return list(session.exec(select(Student).where(Student.class_id == class_id)).all())


def _apply_overrides(result: GradeResult) -> dict[str, Any]:
    """Merge teacher overrides over the AI marks and recompute the totals."""
    merged = dict(result.result or {})
    per_question = [dict(m) for m in (merged.get("per_question_marks") or [])]
    overrides = result.teacher_overrides or {}

    for mark in per_question:
        override = overrides.get(str(mark.get("question_id")))
        if override:
            mark["marks_awarded"] = float(override.get("marks", mark.get("marks_awarded", 0)))
            if override.get("feedback"):
                mark["feedback"] = override["feedback"]
            mark["overridden"] = True
            # A teacher decision is certainty; confidence is no longer the AI's.
            mark["confidence"] = 1.0

    merged["per_question_marks"] = per_question
    merged["total"] = round(
        sum(float(m.get("marks_awarded", 0)) for m in per_question), 2
    )
    merged["max_total"] = round(sum(float(m.get("max_marks", 0)) for m in per_question), 2)
    merged["percentage"] = (
        round(merged["total"] / merged["max_total"] * 100, 1) if merged["max_total"] else 0.0
    )
    return merged


def _result_out(
    result: GradeResult, session: Session, refs: dict[int, str] | None = None
) -> dict[str, Any]:
    student = session.get(Student, result.student_id) if result.student_id else None
    merged = _apply_overrides(result)
    return {
        "id": result.id,
        "assessment_id": result.assessment_id,
        "student_id": result.student_id,
        "student_name": student.name if student else None,
        "student_ref": refs.get(result.student_id) if refs else merged.get("student_ref"),
        "result": merged,
        "teacher_overrides": result.teacher_overrides or {},
        "total": merged.get("total", result.total),
        "max_total": merged.get("max_total", result.max_total),
        "percentage": merged.get("percentage", result.percentage),
        "needs_teacher_review": result.needs_teacher_review,
        "approved": result.approved,
        "created_at": result.created_at.isoformat() if result.created_at else None,
        "approved_at": result.approved_at.isoformat() if result.approved_at else None,
        "low_confidence_questions": [
            m["question_id"]
            for m in merged.get("per_question_marks", [])
            if float(m.get("confidence", 1)) < CONFIDENCE_THRESHOLD
        ],
        "ai_generated": True,
    }


def _upsert_submission(
    session: Session,
    *,
    assessment_id: int,
    student_id: int,
    answers: dict[str, str],
    source: str,
    raw_text: str = "",
) -> Submission:
    """One submission row per (assessment, student); re-grading updates it."""
    existing = session.exec(
        select(Submission).where(
            Submission.assessment_id == assessment_id,
            Submission.student_id == student_id,
        )
    ).first()
    if existing:
        existing.answers = answers
        existing.raw_text = raw_text or existing.raw_text
        existing.source = source
        record = existing
    else:
        record = Submission(
            assessment_id=assessment_id,
            student_id=student_id,
            answers=answers,
            source=source,
            raw_text=raw_text,
        )
    session.add(record)
    session.commit()
    return record


def _grade_one(
    *,
    assessment: Assessment,
    student: Student,
    answers: dict[str, str],
    strictness: str,
    rubric: str,
    session: Session,
    teacher_id: int,
    refs: dict[int, str],
) -> GradeResult:
    ref = refs.get(student.id, "S00")
    try:
        output = grader_agent.run(
            {
                "questions": assessment.questions,
                "answers": answers,
                "student_ref": ref,
                "strictness": strictness,
                "rubric": rubric,
            },
            session=session,
            teacher_id=teacher_id,
        )
    except AgentError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    payload = output.model_dump()

    existing = session.exec(
        select(GradeResult).where(
            GradeResult.assessment_id == assessment.id,
            GradeResult.student_id == student.id,
        )
    ).first()

    if existing:
        # Re-grading replaces the AI draft but keeps any teacher overrides.
        kept = dict(existing.teacher_overrides or {})
        existing.result = payload
        existing.total = payload["total"]
        existing.max_total = payload["max_total"]
        existing.percentage = payload["percentage"]
        existing.needs_teacher_review = payload["needs_teacher_review"]
        existing.approved = False
        existing.approved_at = None
        if kept:
            existing.teacher_overrides = kept
        record = existing
    else:
        record = GradeResult(
            teacher_id=teacher_id,
            assessment_id=assessment.id,
            student_id=student.id,
            result=payload,
            teacher_overrides={},
            total=payload["total"],
            max_total=payload["max_total"],
            percentage=payload["percentage"],
            needs_teacher_review=payload["needs_teacher_review"],
            approved=False,
        )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


# ---------------------------------------------------------------------------
# Assessments
# ---------------------------------------------------------------------------
@router.post("/assessments", response_model=AssessmentOut, status_code=201)
def create_assessment(
    payload: AssessmentCreate,
    teacher: Teacher = Depends(get_current_teacher),
    session: Session = Depends(get_session),
) -> AssessmentOut:
    if payload.class_id:
        get_owned_class(payload.class_id, teacher, session)
    questions = []
    for index, question in enumerate(payload.questions, 1):
        data = question.model_dump()
        data["id"] = data.get("id") or f"Q{index}"
        questions.append(data)
    assessment = Assessment(
        teacher_id=teacher.id,
        class_id=payload.class_id,
        title=payload.title or f"{payload.topic or 'Assessment'} paper",
        subject=payload.subject,
        topic=payload.topic,
        questions=questions,
        total_marks=float(sum(q["marks"] for q in questions)),
    )
    session.add(assessment)
    session.commit()
    session.refresh(assessment)
    return AssessmentOut.model_validate(assessment)


@router.get("/assessments")
def list_assessments(
    class_id: Optional[int] = None,
    teacher: Teacher = Depends(get_current_teacher),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    statement = select(Assessment).where(Assessment.teacher_id == teacher.id)
    if class_id is not None:
        statement = statement.where(Assessment.class_id == class_id)
    rows = session.exec(statement.order_by(Assessment.created_at.desc())).all()
    return [
        {
            "id": a.id,
            "class_id": a.class_id,
            "title": a.title,
            "subject": a.subject,
            "topic": a.topic,
            "question_count": len(a.questions),
            "total_marks": a.total_marks,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in rows
    ]


@router.get("/assessments/{assessment_id}", response_model=AssessmentOut)
def get_assessment(
    assessment_id: int,
    teacher: Teacher = Depends(get_current_teacher),
    session: Session = Depends(get_session),
) -> AssessmentOut:
    return AssessmentOut.model_validate(
        _owned_assessment(assessment_id, teacher, session)
    )


# ---------------------------------------------------------------------------
# Grading
# ---------------------------------------------------------------------------
@router.post("/grade")
def grade_one(
    payload: GradeRequest,
    teacher: Teacher = Depends(rate_limit()),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Grade one student's answers. The result is a DRAFT until approved."""
    assessment = _owned_assessment(payload.assessment_id, teacher, session)
    if assessment.class_id is None:
        raise HTTPException(status_code=400, detail="This assessment has no class.")
    student = session.get(Student, payload.student_id)
    if student is None or student.class_id != assessment.class_id:
        raise HTTPException(status_code=404, detail="Student not found in this class.")

    refs = make_refs(_class_students(assessment.class_id, session))

    # Persist the submission so it can be re-graded later.
    _upsert_submission(
        session,
        assessment_id=assessment.id,
        student_id=student.id,
        answers=payload.answers,
        source="typed",
        raw_text=payload.raw_text,
    )

    record = _grade_one(
        assessment=assessment,
        student=student,
        answers=payload.answers,
        strictness=payload.strictness,
        rubric=payload.rubric,
        session=session,
        teacher_id=teacher.id,
        refs=refs,
    )
    log_time_saved(session, teacher_id=teacher.id, task_type="grading", count=1)
    return _result_out(record, session, refs)


@router.post("/bulk")
def grade_bulk(
    payload: GradeBulkRequest,
    teacher: Teacher = Depends(rate_limit()),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Grade a whole class at once."""
    assessment = _owned_assessment(payload.assessment_id, teacher, session)
    if assessment.class_id is None:
        raise HTTPException(status_code=400, detail="This assessment has no class.")
    students = _class_students(assessment.class_id, session)
    refs = make_refs(students)
    by_id = {s.id: s for s in students}

    results, failures = [], []
    for submission in payload.submissions:
        student = by_id.get(submission.student_id)
        if student is None:
            failures.append(
                {"student_id": submission.student_id, "error": "Student not found in this class."}
            )
            continue
        _upsert_submission(
            session,
            assessment_id=assessment.id,
            student_id=student.id,
            answers=submission.answers,
            source="typed",
            raw_text=submission.raw_text,
        )
        try:
            record = _grade_one(
                assessment=assessment,
                student=student,
                answers=submission.answers,
                strictness=payload.strictness,
                rubric=payload.rubric,
                session=session,
                teacher_id=teacher.id,
                refs=refs,
            )
        except HTTPException as exc:
            failures.append({"student_id": student.id, "error": str(exc.detail)})
            continue
        results.append(_result_out(record, session, refs))

    log_time_saved(session, teacher_id=teacher.id, task_type="grading", count=len(results))
    return {
        "assessment_id": assessment.id,
        "graded": len(results),
        "failed": len(failures),
        "failures": failures,
        "results": results,
    }


@router.post("/bulk-csv")
async def grade_bulk_csv(
    assessment_id: int,
    strictness: str = "standard",
    file: UploadFile = File(...),
    teacher: Teacher = Depends(rate_limit()),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Bulk-grade from a CSV of student answers.

    Expected columns: ``student_id`` OR ``roll_no`` OR ``name``, then one
    column per question id (Q1, Q2, ...).
    """
    assessment = _owned_assessment(assessment_id, teacher, session)
    if assessment.class_id is None:
        raise HTTPException(status_code=400, detail="This assessment has no class.")
    students = _class_students(assessment.class_id, session)
    refs = make_refs(students)

    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="CSV must be UTF-8 encoded.")

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise HTTPException(status_code=400, detail="The CSV looks empty.")

    columns = {name.strip().lower(): name for name in reader.fieldnames if name}
    question_ids = [str(q.get("id")) for q in assessment.questions]
    question_columns = {qid: columns[qid.lower()] for qid in question_ids if qid.lower() in columns}

    if not question_columns:
        raise HTTPException(
            status_code=400,
            detail=(
                "No question columns found. Include one column per question id "
                f"({', '.join(question_ids[:6])}, ...) plus one of "
                "student_id / roll_no / name."
            ),
        )

    by_roll = {str(s.roll_no).strip(): s for s in students if s.roll_no}
    by_name = {s.name.strip().lower(): s for s in students}

    results, skipped = [], []
    for row_number, row in enumerate(reader, start=2):
        def cell(key: str) -> str:
            column = columns.get(key)
            return (row.get(column) or "").strip() if column else ""

        student = None
        if cell("student_id").isdigit():
            student = next((s for s in students if s.id == int(cell("student_id"))), None)
        if student is None and cell("roll_no"):
            student = by_roll.get(cell("roll_no"))
        if student is None and cell("name"):
            student = by_name.get(cell("name").lower())
        if student is None:
            skipped.append({"row": row_number, "reason": "student not matched"})
            continue

        answers = {
            qid: (row.get(column) or "").strip()
            for qid, column in question_columns.items()
        }
        _upsert_submission(
            session,
            assessment_id=assessment.id,
            student_id=student.id,
            answers=answers,
            source="csv",
            raw_text=f"Imported from CSV row {row_number}",
        )
        record = _grade_one(
            assessment=assessment,
            student=student,
            answers=answers,
            strictness=strictness,
            rubric="",
            session=session,
            teacher_id=teacher.id,
            refs=refs,
        )
        results.append(_result_out(record, session, refs))

    log_time_saved(session, teacher_id=teacher.id, task_type="grading", count=len(results))
    return {
        "assessment_id": assessment.id,
        "graded": len(results),
        "skipped": skipped,
        "results": results,
    }


@router.get("/results")
def list_results(
    assessment_id: int,
    teacher: Teacher = Depends(get_current_teacher),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    assessment = _owned_assessment(assessment_id, teacher, session)
    refs = make_refs(_class_students(assessment.class_id, session)) if assessment.class_id else {}
    rows = session.exec(
        select(GradeResult).where(GradeResult.assessment_id == assessment_id)
    ).all()
    return {
        "assessment_id": assessment_id,
        "count": len(rows),
        "results": [_result_out(r, session, refs) for r in rows],
    }


@router.post("/results/{result_id}/overrides")
def save_overrides(
    result_id: int,
    payload: OverrideRequest,
    teacher: Teacher = Depends(get_current_teacher),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Teacher corrections always win over the AI marks, and are remembered."""
    record = session.get(GradeResult, result_id)
    if record is None or record.teacher_id != teacher.id:
        raise HTTPException(status_code=404, detail="Result not found.")

    overrides = dict(record.teacher_overrides or {})
    for override in payload.overrides:
        overrides[override.question_id] = {
            "marks": float(override.marks_awarded),
            "feedback": override.feedback,
            "overridden_at": None,
        }
    record.teacher_overrides = overrides

    merged = _apply_overrides(record)
    record.total = merged["total"]
    record.max_total = merged["max_total"]
    record.percentage = merged["percentage"]

    # Re-check the review flag after the teacher has spoken.
    still_unsure = [
        m
        for m in merged["per_question_marks"]
        if float(m.get("confidence", 1)) < CONFIDENCE_THRESHOLD
        and str(m.get("question_id")) not in overrides
    ]
    record.needs_teacher_review = bool(still_unsure)

    session.add(record)
    session.commit()
    session.refresh(record)

    refs = {}
    if record.student_id:
        student = session.get(Student, record.student_id)
        if student and student.class_id:
            refs = make_refs(_class_students(student.class_id, session))
    return _result_out(record, session, refs)


@router.post("/results/{result_id}/approve")
def approve_result(
    result_id: int,
    teacher: Teacher = Depends(get_current_teacher),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    record = session.get(GradeResult, result_id)
    if record is None or record.teacher_id != teacher.id:
        raise HTTPException(status_code=404, detail="Result not found.")
    record.approved = True
    record.needs_teacher_review = False
    from datetime import datetime, timezone

    record.approved_at = datetime.now(timezone.utc)
    session.add(record)
    session.commit()
    session.refresh(record)
    student = session.get(Student, record.student_id) if record.student_id else None
    refs = (
        make_refs(_class_students(student.class_id, session))
        if student and student.class_id
        else {}
    )
    return _result_out(record, session, refs)


@router.post("/results/approve-all")
def approve_all(
    assessment_id: int,
    teacher: Teacher = Depends(get_current_teacher),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    from datetime import datetime, timezone

    _owned_assessment(assessment_id, teacher, session)
    rows = session.exec(
        select(GradeResult).where(GradeResult.assessment_id == assessment_id)
    ).all()
    now = datetime.now(timezone.utc)
    for row in rows:
        row.approved = True
        row.needs_teacher_review = False
        row.approved_at = now
        session.add(row)
    session.commit()
    return {"approved": len(rows)}


@router.get("/submissions/{assessment_id}")
def list_submissions(
    assessment_id: int,
    teacher: Teacher = Depends(get_current_teacher),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    _owned_assessment(assessment_id, teacher, session)
    rows = session.exec(
        select(Submission).where(Submission.assessment_id == assessment_id)
    ).all()
    out = []
    for row in rows:
        student = session.get(Student, row.student_id) if row.student_id else None
        out.append(
            {
                "id": row.id,
                "student_id": row.student_id,
                "student_name": student.name if student else None,
                "answers": row.answers,
                "source": row.source,
            }
        )
    return out


# ---------------------------------------------------------------------------
# Class analysis
# ---------------------------------------------------------------------------
@router.get("/analysis/{assessment_id}")
def class_analysis(
    assessment_id: int,
    teacher: Teacher = Depends(get_current_teacher),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Average, highest/lowest, hardest questions and common mistakes."""
    assessment = _owned_assessment(assessment_id, teacher, session)
    rows = session.exec(
        select(GradeResult).where(GradeResult.assessment_id == assessment_id)
    ).all()
    if not rows:
        return {
            "assessment_id": assessment_id,
            "graded": 0,
            "average_percentage": 0.0,
            "median_percentage": 0.0,
            "highest": None,
            "lowest": None,
            "questions": [],
            "hardest_questions": [],
            "common_mistakes": [],
            "band_distribution": [],
        }

    refs = make_refs(_class_students(assessment.class_id, session)) if assessment.class_id else {}

    students: list[dict[str, Any]] = []
    per_question: dict[str, dict[str, Any]] = {}

    for record in rows:
        merged = _apply_overrides(record)
        student = session.get(Student, record.student_id) if record.student_id else None
        entry = {
            "student_id": record.student_id,
            "student_name": student.name if student else "Unknown",
            "roll_no": student.roll_no if student else "",
            "percentage": merged.get("percentage", 0.0),
            "total": merged.get("total", 0.0),
            "needs_teacher_review": record.needs_teacher_review,
            "approved": record.approved,
            "weaknesses": merged.get("weaknesses", []),
        }
        students.append(entry)

        for mark in merged.get("per_question_marks", []):
            qid = str(mark.get("question_id"))
            bucket = per_question.setdefault(
                qid,
                {
                    "question_id": qid,
                    "max_marks": float(mark.get("max_marks", 0)),
                    "awarded_total": 0.0,
                    "attempts": 0,
                    "zero_count": 0,
                    "full_count": 0,
                },
            )
            awarded = float(mark.get("marks_awarded", 0))
            bucket["awarded_total"] += awarded
            bucket["attempts"] += 1
            if mark.get("max_marks") and awarded <= 0:
                bucket["zero_count"] += 1
            if mark.get("max_marks") and awarded >= float(mark["max_marks"]) - 1e-9:
                bucket["full_count"] += 1

    question_text = {str(q.get("id")): str(q.get("question", "")) for q in assessment.questions}
    questions: list[dict[str, Any]] = []
    for qid, bucket in per_question.items():
        attempts = bucket["attempts"] or 1
        questions.append(
            {
                **bucket,
                "question": question_text.get(qid, ""),
                "average_marks": round(bucket["awarded_total"] / attempts, 2),
                "average_percentage": round(
                    bucket["awarded_total"] / attempts / bucket["max_marks"] * 100, 1
                )
                if bucket["max_marks"]
                else 0.0,
                "zero_rate": round(bucket["zero_count"] / attempts * 100, 1),
                "full_mark_rate": round(bucket["full_count"] / attempts * 100, 1),
            }
        )
    questions.sort(key=lambda q: q["average_percentage"])

    percentages = sorted(s["percentage"] for s in students)
    middle = len(percentages) // 2
    median = (
        percentages[middle]
        if len(percentages) % 2
        else round((percentages[middle - 1] + percentages[middle]) / 2, 1)
    )

    highest = max(students, key=lambda s: s["percentage"])
    lowest = min(students, key=lambda s: s["percentage"])

    bands = [
        {"band": "90-100", "count": sum(1 for p in percentages if p >= 90)},
        {"band": "75-89", "count": sum(1 for p in percentages if 75 <= p < 90)},
        {"band": "50-74", "count": sum(1 for p in percentages if 50 <= p < 75)},
        {"band": "25-49", "count": sum(1 for p in percentages if 25 <= p < 50)},
        {"band": "0-24", "count": sum(1 for p in percentages if p < 25)},
    ]

    mistake_counts: dict[str, int] = {}
    for record in rows:
        merged = _apply_overrides(record)
        for weakness in merged.get("weaknesses", []):
            mistake_counts[weakness] = mistake_counts.get(weakness, 0) + 1

    return {
        "assessment_id": assessment_id,
        "assessment_title": assessment.title,
        "graded": len(students),
        "average_percentage": round(sum(percentages) / len(percentages), 1),
        "median_percentage": median,
        "highest": highest,
        "lowest": lowest,
        "students": sorted(students, key=lambda s: s["percentage"], reverse=True),
        "questions": questions,
        "hardest_questions": questions[:3],
        "common_mistakes": [
            {"issue": issue, "count": count}
            for issue, count in sorted(mistake_counts.items(), key=lambda kv: -kv[1])[:6]
        ],
        "band_distribution": bands,
    }