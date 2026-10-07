"""Pydantic request/response schemas for the REST API."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

Language = Literal["English", "Hindi"]
Tone = Literal["warm", "formal"]
Channel = Literal["whatsapp", "email"]
Board = Literal["CBSE", "ICSE", "State", "Other"]
Strictness = Literal["lenient", "standard", "strict"]
Level = Literal["support", "core", "extension"]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    teacher: "TeacherOut"


class TeacherOut(ORMModel):
    id: int
    name: str
    email: str
    school_name: str = ""
    subject: str = ""
    preferred_language: str = "English"
    default_tone: str = "warm"


class TeacherUpdate(BaseModel):
    name: Optional[str] = None
    school_name: Optional[str] = None
    subject: Optional[str] = None
    preferred_language: Optional[Language] = None
    default_tone: Optional[Tone] = None


# ---------------------------------------------------------------------------
# Classes & students
# ---------------------------------------------------------------------------
class ClassCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    grade: str = ""
    section: str = ""
    subject: str = ""


class ClassUpdate(BaseModel):
    name: Optional[str] = None
    grade: Optional[str] = None
    section: Optional[str] = None
    subject: Optional[str] = None


class StudentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    roll_no: str = ""
    parent_name: str = ""
    parent_phone: str = ""
    parent_email: str = ""
    preferred_language: Language = "English"
    attendance_pct: float = Field(default=100.0, ge=0, le=100)
    teacher_notes: str = ""


class StudentUpdate(BaseModel):
    name: Optional[str] = None
    roll_no: Optional[str] = None
    parent_name: Optional[str] = None
    parent_phone: Optional[str] = None
    parent_email: Optional[str] = None
    preferred_language: Optional[Language] = None
    attendance_pct: Optional[float] = Field(default=None, ge=0, le=100)
    teacher_notes: Optional[str] = None


class StudentOut(ORMModel):
    id: int
    name: str
    roll_no: str
    class_id: Optional[int] = None
    parent_name: str = ""
    parent_phone: str = ""
    parent_email: str = ""
    preferred_language: str = "English"
    attendance_pct: float = 100.0
    teacher_notes: str = ""


class ClassOut(ORMModel):
    id: int
    name: str
    grade: str = ""
    section: str = ""
    subject: str = ""
    teacher_id: Optional[int] = None
    student_count: int = 0


# ---------------------------------------------------------------------------
# Lesson plans
# ---------------------------------------------------------------------------
class LessonPlanRequest(BaseModel):
    subject: str = Field(min_length=1)
    class_id: Optional[int] = None
    grade: str = ""
    topic: str = Field(min_length=1)
    duration_minutes: int = Field(default=40, ge=5, le=300)
    board: Board = "CBSE"
    language: Language = "English"
    learning_objectives: list[str] = Field(default_factory=list)
    class_level_notes: str = ""

    @field_validator("learning_objectives")
    @classmethod
    def _limit_objectives(cls, v: list[str]) -> list[str]:
        return [o.strip() for o in v if o and o.strip()][:8]


class LessonPlanUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[dict[str, Any]] = None
    status: Optional[Literal["draft", "approved"]] = None


# ---------------------------------------------------------------------------
# Assessments & grading
# ---------------------------------------------------------------------------
class QuestionIn(BaseModel):
    id: str = ""
    question: str = Field(min_length=1)
    marks: float = Field(default=1.0, gt=0, le=100)
    type: Literal["mcq", "short", "long", "numeric", "true_false"] = "short"
    options: list[str] = Field(default_factory=list)
    answer_key: Optional[str] = None
    model_answer: str = ""


class AssessmentCreate(BaseModel):
    title: str = ""
    class_id: Optional[int] = None
    subject: str = ""
    topic: str = ""
    questions: list[QuestionIn] = Field(min_length=1, max_length=100)


class AssessmentOut(ORMModel):
    id: int
    title: str
    subject: str = ""
    topic: str = ""
    class_id: Optional[int] = None
    questions: list[dict[str, Any]] = Field(default_factory=list)
    total_marks: float = 0
    created_at: datetime


class GradeRequest(BaseModel):
    assessment_id: int
    student_id: int
    answers: dict[str, str] = Field(default_factory=dict)
    raw_text: str = ""
    strictness: Strictness = "standard"
    rubric: str = ""


class GradeBulkRequest(BaseModel):
    assessment_id: int
    strictness: Strictness = "standard"
    rubric: str = ""
    submissions: list["SubmissionIn"] = Field(default_factory=list)

    @field_validator("submissions")
    @classmethod
    def _non_empty(cls, v: list["SubmissionIn"]) -> list["SubmissionIn"]:
        if not v:
            raise ValueError("At least one submission is required for bulk grading.")
        return v


class SubmissionIn(BaseModel):
    student_id: int
    answers: dict[str, str] = Field(default_factory=dict)
    raw_text: str = ""


class OverrideMark(BaseModel):
    question_id: str
    marks_awarded: float = Field(ge=0)
    feedback: str = ""


class OverrideRequest(BaseModel):
    overrides: list[OverrideMark] = Field(default_factory=list)


class BulkCsvRow(BaseModel):
    student_id: Optional[int] = None
    roll_no: Optional[str] = None
    name: Optional[str] = None
    answers: dict[str, str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Differentiation
# ---------------------------------------------------------------------------
class DifferentiateRequest(BaseModel):
    topic: str = Field(min_length=1)
    lesson_plan_id: Optional[int] = None
    class_id: Optional[int] = None
    language: Language = "English"
    # Optional: let the teacher assign levels explicitly instead of
    # deriving them from grading data.
    manual_levels: dict[int, Level] = Field(default_factory=dict)
    notes: str = ""


# ---------------------------------------------------------------------------
# Parent updates
# ---------------------------------------------------------------------------
class ParentUpdateRequest(BaseModel):
    class_id: int
    student_ids: list[int] = Field(default_factory=list)
    language: Optional[Language] = None
    tone: Tone = "warm"
    channel: Channel = "whatsapp"
    topic: str = ""
    teacher_note: str = ""


class ParentMessageUpdate(BaseModel):
    body: Optional[str] = None
    subject: Optional[str] = None
    language: Optional[Language] = None


class SendRequest(BaseModel):
    message_ids: list[int] = Field(default_factory=list)
    send_all: bool = False


# ---------------------------------------------------------------------------
# Workflow
# ---------------------------------------------------------------------------
class WorkflowRequest(BaseModel):
    class_id: int
    topic: str = Field(min_length=1)
    subject: str = ""
    language: Language = "English"
    duration_minutes: int = Field(default=40, ge=5, le=300)
    board: Board = "CBSE"
    strictness: Strictness = "standard"
    tone: Tone = "warm"
    channel: Channel = "whatsapp"
    # Use the seeded demo answers so the whole pipeline can be demonstrated
    # in one click; otherwise the grading step waits for teacher input.
    use_sample_answers: bool = True
    duration_seconds: int = Field(default=0, ge=0, le=120)  # demo pacing


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
class TimeSavedPoint(BaseModel):
    week: str
    minutes: int


class DashboardSummary(BaseModel):
    lesson_plans_created: int
    papers_graded: int
    students_graded: int
    messages_sent: int
    messages_pending: int
    worksheets_created: int
    time_saved_this_week_minutes: int
    time_saved_all_time_minutes: int
    time_saved_by_task: dict[str, int]
    weekly_time_saved: list[TimeSavedPoint]
    class_overview: list[dict[str, Any]]
    recent_activity: list[dict[str, Any]]
    approval_inbox_count: int


GradeRequest.model_rebuild()
GradeBulkRequest.model_rebuild()
TokenResponse.model_rebuild()
