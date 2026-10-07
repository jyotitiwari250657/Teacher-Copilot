"""SQLModel tables for TeacherCopilot."""
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import JSON, Column, Text
from sqlmodel import Field, Relationship, SQLModel

# NOTE: this module deliberately does NOT use `from __future__ import
# annotations`. Stringified annotations confuse SQLModel's relationship
# resolver, so the annotations below are evaluated at runtime instead.


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# People
# ---------------------------------------------------------------------------
class Teacher(SQLModel, table=True):
    __tablename__ = "teachers"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    email: str = Field(unique=True, index=True)
    hashed_password: str
    school_name: str = ""
    subject: str = "General"
    # Teacher-level defaults used by the agents.
    preferred_language: str = Field(default="English")
    default_tone: str = Field(default="warm")
    created_at: datetime = Field(default_factory=utcnow)

    classes: list["SchoolClass"] = Relationship(back_populates="teacher")


class SchoolClass(SQLModel, table=True):
    __tablename__ = "school_classes"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    grade: str = ""
    section: str = ""
    subject: str = ""
    teacher_id: Optional[int] = Field(default=None, foreign_key="teachers.id")
    created_at: datetime = Field(default_factory=utcnow)

    teacher: Optional[Teacher] = Relationship(back_populates="classes")
    students: list["Student"] = Relationship(
        back_populates="school_class", cascade_delete=True
    )


class Student(SQLModel, table=True):
    __tablename__ = "students"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    roll_no: str = ""
    class_id: Optional[int] = Field(default=None, foreign_key="school_classes.id")
    parent_name: str = ""
    parent_phone: str = ""
    parent_email: str = ""
    preferred_language: str = Field(default="English")
    attendance_pct: float = Field(default=100.0)
    teacher_notes: str = Field(default="", sa_column=Column(Text, default=""))
    created_at: datetime = Field(default_factory=utcnow)

    school_class: Optional["SchoolClass"] = Relationship(back_populates="students")


# ---------------------------------------------------------------------------
# Agent artefacts
# ---------------------------------------------------------------------------
class LessonPlan(SQLModel, table=True):
    __tablename__ = "lesson_plans"

    id: Optional[int] = Field(default=None, primary_key=True)
    teacher_id: Optional[int] = Field(default=None, foreign_key="teachers.id")
    class_id: Optional[int] = Field(default=None, foreign_key="school_classes.id")

    title: str = ""
    subject: str = ""
    grade: str = ""
    topic: str = ""
    board: str = "CBSE"
    language: str = "English"
    duration_minutes: int = 40

    # The full agent output, stored verbatim.
    content: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    status: str = Field(default="draft")  # draft | approved
    created_at: datetime = Field(default_factory=utcnow)
    approved_at: Optional[datetime] = None


class Assessment(SQLModel, table=True):
    __tablename__ = "assessments"

    id: Optional[int] = Field(default=None, primary_key=True)
    teacher_id: Optional[int] = Field(default=None, foreign_key="teachers.id")
    class_id: Optional[int] = Field(default=None, foreign_key="school_classes.id")

    title: str = ""
    subject: str = ""
    topic: str = ""
    # list of {id, question, marks, type, options, answer_key, model_answer}
    questions: list[dict[str, Any]] = Field(
        default_factory=list, sa_column=Column(JSON)
    )
    total_marks: int = 0
    created_at: datetime = Field(default_factory=utcnow)


class Submission(SQLModel, table=True):
    __tablename__ = "submissions"

    id: Optional[int] = Field(default=None, primary_key=True)
    assessment_id: Optional[int] = Field(default=None, foreign_key="assessments.id")
    student_id: Optional[int] = Field(default=None, foreign_key="students.id")
    # {question_id: answer_text}
    answers: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    raw_text: str = Field(default="", sa_column=Column(Text, default=""))
    source: str = Field(default="typed")  # typed | csv | ocr
    created_at: datetime = Field(default_factory=utcnow)

    student: Optional[Student] = Relationship()


class GradeResult(SQLModel, table=True):
    __tablename__ = "grade_results"

    id: Optional[int] = Field(default=None, primary_key=True)
    teacher_id: Optional[int] = Field(default=None, foreign_key="teachers.id")
    assessment_id: Optional[int] = Field(default=None, foreign_key="assessments.id")
    student_id: Optional[int] = Field(default=None, foreign_key="students.id")

    # Full agent output for this student.
    result: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    # {question_id: {marks, feedback, overridden_at}} - teacher wins.
    teacher_overrides: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSON)
    )
    total: float = 0.0
    max_total: float = 0.0
    percentage: float = 0.0
    needs_teacher_review: bool = False
    approved: bool = False
    created_at: datetime = Field(default_factory=utcnow)
    approved_at: Optional[datetime] = None

    student: Optional[Student] = Relationship()


class DifferentiatedMaterial(SQLModel, table=True):
    __tablename__ = "differentiated_materials"

    id: Optional[int] = Field(default=None, primary_key=True)
    teacher_id: Optional[int] = Field(default=None, foreign_key="teachers.id")
    class_id: Optional[int] = Field(default=None, foreign_key="school_classes.id")
    lesson_plan_id: Optional[int] = Field(default=None, foreign_key="lesson_plans.id")

    topic: str = ""
    language: str = "English"
    # {"support": {...}, "core": {...}, "extension": {...}}
    content: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    # {"support": [...student ids], "core": [...], "extension": [...]}
    groupings: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    status: str = Field(default="draft")
    created_at: datetime = Field(default_factory=utcnow)


class ParentMessage(SQLModel, table=True):
    __tablename__ = "parent_messages"

    id: Optional[int] = Field(default=None, primary_key=True)
    teacher_id: Optional[int] = Field(default=None, foreign_key="teachers.id")
    student_id: Optional[int] = Field(default=None, foreign_key="students.id")
    class_id: Optional[int] = Field(default=None, foreign_key="school_classes.id")
    workflow_run_id: Optional[int] = Field(default=None, foreign_key="workflow_runs.id")

    channel: str = "whatsapp"  # whatsapp | email
    language: str = "English"
    tone: str = "warm"
    subject: str = ""  # email only
    body: str = Field(default="", sa_column=Column(Text, default=""))
    word_count: int = 0

    # draft | needs_review | approved | simulated_sent | sent | failed
    status: str = Field(default="draft")
    needs_teacher_review: bool = False
    review_reasons: list[Any] = Field(default_factory=list, sa_column=Column(JSON))

    sent_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=utcnow)


# ---------------------------------------------------------------------------
# Orchestration + telemetry
# ---------------------------------------------------------------------------
class WorkflowRun(SQLModel, table=True):
    __tablename__ = "workflow_runs"

    id: Optional[int] = Field(default=None, primary_key=True)
    teacher_id: Optional[int] = Field(default=None, foreign_key="teachers.id")
    class_id: Optional[int] = Field(default=None, foreign_key="school_classes.id")
    topic: str = ""
    subject: str = ""
    language: str = "English"

    # pending | running | done | done_with_errors | failed | cancelled
    status: str = Field(default="pending")
    # Shared context passed between agents (never holds raw PII sent to LLM).
    context: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    # Ids of the artefacts each step produced.
    outputs: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    lesson_plan_id: Optional[int] = Field(default=None, foreign_key="lesson_plans.id")
    assessment_id: Optional[int] = Field(default=None, foreign_key="assessments.id")
    material_id: Optional[int] = Field(default=None, foreign_key="differentiated_materials.id")

    error: str = Field(default="", sa_column=Column(Text, default=""))
    created_at: datetime = Field(default_factory=utcnow)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class WorkflowStep(SQLModel, table=True):
    __tablename__ = "workflow_steps"

    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: Optional[int] = Field(default=None, foreign_key="workflow_runs.id")
    step_number: int = 0
    step_key: str = ""
    title: str = ""
    agent: str = ""
    # pending | running | done | needs_review | failed | skipped
    status: str = Field(default="pending")
    detail: str = Field(default="", sa_column=Column(Text, default=""))
    output: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    duration_ms: int = 0
    created_at: datetime = Field(default_factory=utcnow)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class AgentLog(SQLModel, table=True):
    __tablename__ = "agent_logs"

    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: Optional[int] = Field(default=None, foreign_key="workflow_runs.id")
    teacher_id: Optional[int] = Field(default=None, foreign_key="teachers.id")
    agent: str = ""
    action: str = ""
    input_summary: str = Field(default="", sa_column=Column(Text, default=""))
    output_summary: str = Field(default="", sa_column=Column(Text, default=""))
    duration_ms: int = 0
    tokens: Optional[int] = None
    success: bool = True
    error: str = Field(default="", sa_column=Column(Text, default=""))
    created_at: datetime = Field(default_factory=utcnow)


class TimeSavedLog(SQLModel, table=True):
    __tablename__ = "time_saved_logs"

    id: Optional[int] = Field(default=None, primary_key=True)
    teacher_id: Optional[int] = Field(default=None, foreign_key="teachers.id")
    task_type: str = ""  # lesson_plan | grading | differentiation | parent_message
    task_count: int = 1
    minutes_saved: int = 0
    created_at: datetime = Field(default_factory=utcnow)
