"""The Orchestrator.

Runs the weekly pipeline across the four specialist agents, passing a shared
context between them:

    1. Lesson Planner      -> a lesson plan
    2. Differentiation     -> Support / Core / Extension material
    3. Grader              -> marks for every student
    4. Differentiation     -> regroup students using the marks
    5. Parent Update      -> one personalised message per student

Design rules
------------
* A shared :class:`WorkflowContext` carries results between steps.
* A failure in one step never aborts the run: the step is marked ``failed``,
  the run continues with whatever context exists, and the teacher can re-run
  that single step later.
* Steps write their state to ``WorkflowStep`` rows so the UI can poll progress.
* Nothing a teacher must see is treated as final - everything lands in the
  approval inbox.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from sqlmodel import Session, select

from .agents.base import AgentError
from .agents.differentiation import agent as diff_agent
from .agents.grader import agent as grader_agent
from .agents.lesson_planner import agent as lesson_agent
from .agents.parent_update import agent as parent_agent
from .models import (
    Assessment,
    DifferentiatedMaterial,
    GradeResult,
    LessonPlan,
    ParentMessage,
    SchoolClass,
    Student,
    Submission,
    Teacher,
    WorkflowRun,
    WorkflowStep,
)
from .services.analytics import log_time_saved
from .services.privacy import make_refs, ref_to_student_id

logger = logging.getLogger("teachercopilot.orchestrator")


# ---------------------------------------------------------------------------
# Shared context passed between agents
# ---------------------------------------------------------------------------
@dataclass
class WorkflowContext:
    """Everything the agents hand to each other."""

    class_id: int
    topic: str
    subject: str
    language: str = "English"
    duration_minutes: int = 40
    board: str = "CBSE"
    strictness: str = "standard"
    tone: str = "warm"
    channel: str = "whatsapp"

    refs: dict[int, str] = field(default_factory=dict)
    students: list[Student] = field(default_factory=list)
    teacher: Optional[Teacher] = None

    lesson_plan_id: Optional[int] = None
    lesson_plan: dict[str, Any] = field(default_factory=dict)
    assessment_id: Optional[int] = None
    questions: list[dict[str, Any]] = field(default_factory=list)
    material_id: Optional[int] = None
    differentiated: dict[str, Any] = field(default_factory=dict)
    performance: list[dict[str, Any]] = field(default_factory=list)
    graded_count: int = 0
    messages_created: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "class_id": self.class_id,
            "topic": self.topic,
            "subject": self.subject,
            "language": self.language,
            "assessment_id": self.assessment_id,
            "lesson_plan_id": self.lesson_plan_id,
            "material_id": self.material_id,
            "graded_count": self.graded_count,
            "messages_created": self.messages_created,
            "performance": self.performance,
            "student_count": len(self.students),
        }


# ---------------------------------------------------------------------------
# Step definitions
# ---------------------------------------------------------------------------
STEPS: list[dict[str, Any]] = [
    {"key": "lesson_plan", "title": "Create lesson plan", "agent": "lesson_planner"},
    {"key": "differentiate", "title": "Build Support/Core/Extension material", "agent": "differentiation"},
    {"key": "grade", "title": "Grade student answers", "agent": "grader"},
    {"key": "regroup", "title": "Regroup students from the marks", "agent": "differentiation"},
    {"key": "parent_messages", "title": "Write parent messages", "agent": "parent_update"},
]


@dataclass
class StepOutcome:
    status: str          # done | needs_review | failed | skipped
    detail: str = ""
    output: dict[str, Any] = field(default_factory=dict)
    duration_ms: int = 0


StepHandler = Callable[["Orchestrator", WorkflowContext], StepOutcome]


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------
class Orchestrator:
    def __init__(self, session: Session, run: WorkflowRun, teacher: Teacher):
        self.session = session
        self.run = run
        self.teacher = teacher

    # ---- context ------------------------------------------------------
    def _build_context(self, params: dict[str, Any]) -> WorkflowContext:
        school_class = self.session.get(SchoolClass, self.run.class_id)
        students = list(
            self.session.exec(select(Student).where(Student.class_id == self.run.class_id)).all()
        )
        return WorkflowContext(
            class_id=self.run.class_id,
            topic=self.run.topic,
            subject=(school_class.subject if school_class else "") or self.teacher.subject,
            language=self.run.language,
            duration_minutes=int(params.get("duration_minutes", 40)),
            board=params.get("board", "CBSE"),
            strictness=params.get("strictness", "standard"),
            tone=params.get("tone", "warm"),
            channel=params.get("channel", "whatsapp"),
            refs=make_refs(students),
            students=students,
            teacher=self.teacher,
        )

    # ---- step registry ------------------------------------------------
    def handler_for(self, key: str) -> StepHandler:
        return {
            "lesson_plan": self._step_lesson_plan,
            "differentiate": self._step_differentiate,
            "grade": self._step_grade,
            "regroup": self._step_regroup,
            "parent_messages": self._step_parent_messages,
        }.get(key, self._step_unknown)

    # ---- individual steps ---------------------------------------------
    def _step_unknown(self, context: WorkflowContext) -> StepOutcome:
        return StepOutcome(status="failed", detail=f"Unknown step '{context.topic}'.")

    def _step_lesson_plan(self, context: WorkflowContext) -> StepOutcome:
        output = lesson_agent.run(
            {
                "subject": context.subject,
                "grade": self._grade(),
                "topic": context.topic,
                "duration_minutes": context.duration_minutes,
                "board": context.board,
                "language": context.language,
                "learning_objectives": [],
                "class_level_notes": "",
            },
            session=self.session,
            run_id=self.run.id,
            teacher_id=self.teacher.id,
        )
        content = output.model_dump()
        plan = LessonPlan(
            teacher_id=self.teacher.id,
            class_id=context.class_id,
            title=output.title,
            subject=context.subject,
            grade=self._grade(),
            topic=context.topic,
            board=context.board,
            language=context.language,
            duration_minutes=context.duration_minutes,
            content=content,
            status="draft",
        )
        self.session.add(plan)
        self.session.commit()
        self.session.refresh(plan)

        context.lesson_plan_id = plan.id
        context.lesson_plan = content
        self.run.lesson_plan_id = plan.id

        log_time_saved(self.session, teacher_id=self.teacher.id, task_type="lesson_plan")
        return StepOutcome(
            status="needs_review",
            detail=f"Lesson plan '{plan.title}' created with "
            f"{len(content.get('lesson_flow', []))} phases totalling "
            f"{sum(i.get('minutes', 0) for i in content.get('lesson_flow', []))} minutes.",
            output={"lesson_plan_id": plan.id, "title": plan.title},
        )

    def _step_differentiate(self, context: WorkflowContext) -> StepOutcome:
        # Grading feeds the grouping; if grading has not run yet this first
        # pass produces material with empty groupings.
        output = diff_agent.run(
            {
                "topic": context.topic,
                "lesson_plan": context.lesson_plan,
                "language": context.language,
                "performance": self._performance_for_llm(context),
                "manual_levels": {},
                "grade": self._grade(),
                "notes": "",
            },
            session=self.session,
            run_id=self.run.id,
            teacher_id=self.teacher.id,
        )
        material = self._store_material(context, output)
        return StepOutcome(
            status="done",
            detail=f"Three levels and three worksheets created "
            f"({len(output.support.worksheet)}/{len(output.core.worksheet)}/"
            f"{len(output.extension.worksheet)} questions).",
            output={"material_id": material.id},
        )

    def _step_grade(self, context: WorkflowContext) -> StepOutcome:
        assessment = self._ensure_assessment(context)
        graded, review_count, failures = 0, 0, []

        for index, student in enumerate(context.students):
            answers = self._answers_for(context, student, index)
            try:
                output = grader_agent.run(
                    {
                        "questions": context.questions,
                        "answers": answers,
                        "student_ref": context.refs.get(student.id, "S00"),
                        "strictness": context.strictness,
                        "rubric": "",
                    },
                    session=self.session,
                    run_id=self.run.id,
                    teacher_id=self.teacher.id,
                )
            except AgentError as exc:
                failures.append({"student": student.name, "error": str(exc)})
                continue

            payload = output.model_dump()
            record = self.session.exec(
                select(GradeResult).where(
                    GradeResult.assessment_id == assessment.id,
                    GradeResult.student_id == student.id,
                )
            ).first()
            if record:
                record.result = payload
                record.total = payload["total"]
                record.max_total = payload["max_total"]
                record.percentage = payload["percentage"]
                record.needs_teacher_review = payload["needs_teacher_review"]
                record.approved = False
            else:
                record = GradeResult(
                    teacher_id=self.teacher.id,
                    assessment_id=assessment.id,
                    student_id=student.id,
                    result=payload,
                    total=payload["total"],
                    max_total=payload["max_total"],
                    percentage=payload["percentage"],
                    needs_teacher_review=payload["needs_teacher_review"],
                    approved=False,
                )
            self.session.add(record)
            self.session.commit()

            # Upsert so re-running the step does not duplicate submissions.
            submission = self.session.exec(
                select(Submission).where(
                    Submission.assessment_id == assessment.id,
                    Submission.student_id == student.id,
                )
            ).first()
            if submission:
                submission.answers = answers
                session_submission = submission
            else:
                session_submission = Submission(
                    assessment_id=assessment.id,
                    student_id=student.id,
                    answers=answers,
                    source="typed",
                )
            self.session.add(session_submission)
            self.session.commit()
            graded += 1
            if payload["needs_teacher_review"]:
                review_count += 1

        context.graded_count = graded
        context.performance = self._collect_performance(assessment.id)
        log_time_saved(
            self.session, teacher_id=self.teacher.id, task_type="grading", count=graded
        )

        detail = f"{graded} of {len(context.students)} students graded."
        if review_count:
            detail += f" {review_count} flagged for your review (low confidence)."
        if failures:
            detail += f" {len(failures)} failed."
        return StepOutcome(
            status="needs_review" if review_count else ("failed" if not graded else "done"),
            detail=detail,
            output={
                "graded": graded,
                "needs_review": review_count,
                "failures": failures,
                "class_average": round(
                    sum(p["percentage"] for p in context.performance) / len(context.performance), 1
                )
                if context.performance
                else 0.0,
            },
        )

    def _step_regroup(self, context: WorkflowContext) -> StepOutcome:
        if not context.performance:
            return StepOutcome(
                status="skipped",
                detail="No graded results yet, so students were not regrouped. "
                "Grade the class first, then re-run this step.",
            )

        output = diff_agent.run(
            {
                "topic": context.topic,
                "lesson_plan": context.lesson_plan,
                "language": context.language,
                "performance": self._performance_for_llm(context),
                "manual_levels": {},
                "grade": self._grade(),
                "notes": "",
            },
            session=self.session,
            run_id=self.run.id,
            teacher_id=self.teacher.id,
        )
        material = self._store_material(context, output)
        sizes = {
            grouping.level: len(grouping.student_refs) for grouping in output.groupings
        }
        return StepOutcome(
            status="needs_review",
            detail="Students grouped from the latest marks: "
            + ", ".join(f"{level} {size}" for level, size in sizes.items())
            + ". Move anyone the teacher disagrees with.",
            output={
                "material_id": material.id,
                "group_sizes": sizes,
                "groupings": [g.model_dump() for g in output.groupings],
            },
        )

    def _step_parent_messages(self, context: WorkflowContext) -> StepOutcome:
        if not context.students:
            return StepOutcome(status="skipped", detail="No students in this class.")

        school_class = self.session.get(SchoolClass, context.class_id)
        created, flagged, failures = 0, 0, []

        for student in context.students:
            scores = [
                {"topic": context.topic, "percentage": entry["percentage"]}
                for entry in context.performance
                if entry["student_id"] == student.id
            ] or [{"topic": context.topic, "percentage": entry["percentage"]} for entry in context.performance]
            overall = (
                round(sum(s["percentage"] for s in scores) / len(scores), 1)
                if scores
                else None
            )
            try:
                output = parent_agent.run(
                    {
                        "student_ref": context.refs.get(student.id, "S00"),
                        "recent_scores": scores[:3],
                        "overall_percentage": overall,
                        "attendance_pct": student.attendance_pct,
                        "subject": (school_class.subject if school_class else "")
                        or context.subject,
                        "teacher_notes": student.teacher_notes,
                        "tone": context.tone,
                        "language": context.language,
                        "channel": context.channel,
                        "teacher_name": self.teacher.name,
                        "school_name": self.teacher.school_name,
                        "topic": context.topic,
                    },
                    session=self.session,
                    run_id=self.run.id,
                    teacher_id=self.teacher.id,
                )
            except AgentError as exc:
                failures.append({"student": student.name, "error": str(exc)})
                continue

            message = ParentMessage(
                teacher_id=self.teacher.id,
                student_id=student.id,
                class_id=context.class_id,
                workflow_run_id=self.run.id,
                channel=context.channel,
                language=context.language,
                tone=context.tone,
                subject=output.subject_line,
                body=(
                    output.body.replace("{{student_name}}", student.name)
                    .replace("{{parent_name}}", student.parent_name or "Parent")
                    .replace("{{teacher_name}}", self.teacher.name)
                    .replace("{{school_name}}", self.teacher.school_name or "the school")
                ),
                word_count=output.word_count,
                status="needs_review" if output.needs_teacher_review else "draft",
                needs_teacher_review=output.needs_teacher_review,
                review_reasons=output.review_reasons,
            )
            self.session.add(message)
            self.session.commit()
            created += 1
            if output.needs_teacher_review:
                flagged += 1

        context.messages_created = created
        log_time_saved(
            self.session,
            teacher_id=self.teacher.id,
            task_type="parent_message",
            count=created,
        )
        detail = f"{created} draft messages created."
        if flagged:
            detail += f" {flagged} flagged for your review before sending."
        if failures:
            detail += f" {len(failures)} failed."
        return StepOutcome(
            status="needs_review" if created else "failed",
            detail=detail + " Nothing is sent until you approve it.",
            output={"created": created, "flagged": flagged, "failures": failures},
        )

    # ---- helpers -------------------------------------------------------
    def _grade(self) -> str:
        school_class = self.session.get(SchoolClass, self.run.class_id)
        return school_class.grade if school_class else ""

    def _store_material(self, context: WorkflowContext, output: Any) -> DifferentiatedMaterial:
        data = output.model_dump()
        material = DifferentiatedMaterial(
            teacher_id=self.teacher.id,
            class_id=context.class_id,
            lesson_plan_id=context.lesson_plan_id,
            topic=context.topic,
            language=context.language,
            content=data,
            groupings={g.level: g.student_refs for g in output.groupings},
            status="draft",
        )
        self.session.add(material)
        self.session.commit()
        self.session.refresh(material)
        context.material_id = material.id
        context.differentiated = data
        self.run.material_id = material.id
        return material

    def _performance_for_llm(self, context: WorkflowContext) -> list[dict[str, Any]]:
        """Pseudonymous performance data - never names."""
        return [
            {
                "student_ref": context.refs.get(entry["student_id"], "S00"),
                "percentage": entry["percentage"],
            }
            for entry in context.performance
        ]

    def _collect_performance(self, assessment_id: int) -> list[dict[str, Any]]:
        rows = self.session.exec(
            select(GradeResult).where(GradeResult.assessment_id == assessment_id)
        ).all()
        return [{"student_id": r.student_id, "percentage": r.percentage} for r in rows]

    def _ensure_assessment(self, context: WorkflowContext) -> Assessment:
        """Find or build the paper that matches this topic."""
        from .services.seed import PHOTOSYNTHESIS_QUESTIONS

        existing = self.session.exec(
            select(Assessment).where(
                Assessment.class_id == context.class_id,
                Assessment.topic == context.topic,
            )
        ).first()
        if existing:
            context.assessment_id = existing.id
            context.questions = existing.questions
            self.run.assessment_id = existing.id
            return existing

        if context.topic.strip().lower() == "photosynthesis":
            questions = [dict(q) for q in PHOTOSYNTHESIS_QUESTIONS]
        else:
            questions = self._questions_from_lesson(context)

        assessment = Assessment(
            teacher_id=self.teacher.id,
            class_id=context.class_id,
            title=f"{context.topic} - quick check",
            subject=context.subject,
            topic=context.topic,
            questions=questions,
            total_marks=float(sum(q.get("marks", 1) for q in questions)),
        )
        self.session.add(assessment)
        self.session.commit()
        self.session.refresh(assessment)
        context.assessment_id = assessment.id
        context.questions = questions
        self.run.assessment_id = assessment.id
        return assessment

    def _questions_from_lesson(self, context: WorkflowContext) -> list[dict[str, Any]]:
        """Derive a short paper from the lesson plan's exit ticket + vocabulary."""
        plan = context.lesson_plan or {}
        questions: list[dict[str, Any]] = []
        exit_ticket = plan.get("exit_ticket") or []
        for index, question in enumerate(exit_ticket[:3], 1):
            questions.append(
                {
                    "id": f"Q{index}",
                    "question": str(question),
                    "marks": 2,
                    "type": "short",
                    "model_answer": "; ".join(plan.get("key_vocabulary", [])[:4]),
                }
            )
        for index, point in enumerate(plan.get("key_points", [])[:3], len(questions) + 1):
            questions.append(
                {
                    "id": f"Q{index}",
                    "question": f"Explain in one line: {point}",
                    "marks": 2,
                    "type": "short",
                    "model_answer": str(point),
                }
            )
        if not questions:
            questions = [
                {
                    "id": "Q1",
                    "question": f"In your own words, what is {context.topic}?",
                    "marks": 5,
                    "type": "long",
                    "model_answer": f"A correct explanation of {context.topic}.",
                }
            ]
        return questions

    def _answers_for(
        self, context: WorkflowContext, student: Student, index: int
    ) -> dict[str, str]:
        """Demo answers: reuse a real submission, else a tier-appropriate set."""
        from .services.seed import _ANSWERS, tier_for_index

        existing = self.session.exec(
            select(Submission)
            .where(Submission.student_id == student.id)
            .order_by(Submission.created_at.desc())
        ).first()
        if existing and existing.answers:
            return existing.answers
        return dict(_ANSWERS.get(tier_for_index(index), _ANSWERS["average"]))

    # ---- execution ------------------------------------------------------
    def run_step(self, key: str, params: dict[str, Any]) -> WorkflowStep:
        """Run a single step and record its status."""
        context = self._build_context(params)
        # Restore shared context so a re-run sees earlier steps' work.
        self._restore_context(context)

        step = self.session.exec(
            select(WorkflowStep).where(
                WorkflowStep.run_id == self.run.id, WorkflowStep.step_key == key
            )
        ).first()
        if step is None:
            meta = next((s for s in STEPS if s["key"] == key), None)
            step = WorkflowStep(
                run_id=self.run.id,
                step_number=(meta or {}).get("number", 0),
                step_key=key,
                title=(meta or {}).get("title", key),
                agent=(meta or {}).get("agent", ""),
            )
        step.status = "running"
        step.started_at = datetime.now(timezone.utc)
        step.detail = ""
        self.session.add(step)
        self.session.commit()

        started = time.perf_counter()
        try:
            outcome = self.handler_for(key)(context)
            step.status = outcome.status
            step.detail = outcome.detail
            step.output = outcome.output
        except AgentError as exc:
            step.status = "failed"
            step.detail = str(exc)
            step.output = {}
            logger.warning("[run %s] step %s failed: %s", self.run.id, key, exc)
        except Exception as exc:  # noqa: BLE001 - a step must never kill the run
            step.status = "failed"
            step.detail = f"Unexpected error in step '{key}': {exc}"
            step.output = {}
            logger.exception("[run %s] step %s crashed", self.run.id, key)

        step.duration_ms = int((time.perf_counter() - started) * 1000)
        step.finished_at = datetime.now(timezone.utc)
        # `detail` carries both the human summary and any error text.

        self.run.context = context.as_dict()
        outputs = dict(self.run.outputs or {})
        outputs[key] = {
            "status": step.status,
            "detail": step.detail,
            "duration_ms": step.duration_ms,
            "output": step.output,
        }
        self.run.outputs = outputs
        self.session.add(self.run)
        self.session.add(step)
        self.session.commit()
        self.session.refresh(step)
        return step

    def _restore_context(self, context: WorkflowContext) -> None:
        """Reload artefacts from earlier steps so a re-run step has inputs."""
        stored = self.run.context or {}
        context.lesson_plan_id = self.run.lesson_plan_id or stored.get("lesson_plan_id")
        context.material_id = self.run.material_id or stored.get("material_id")
        context.assessment_id = self.run.assessment_id or stored.get("assessment_id")

        if context.lesson_plan_id:
            plan = self.session.get(LessonPlan, context.lesson_plan_id)
            if plan:
                context.lesson_plan = plan.content or {}
        if context.assessment_id:
            assessment = self.session.get(Assessment, context.assessment_id)
            if assessment:
                context.questions = assessment.questions
        if context.assessment_id:
            context.performance = self._collect_performance(context.assessment_id)

    def run_all(self, params: dict[str, Any], *, stop_on_failure: bool = False) -> list[WorkflowStep]:
        """Run every step in order, isolating failures."""
        steps: list[WorkflowStep] = []
        for index, meta in enumerate(STEPS, 1):
            step = self.run_step(meta["key"], params)
            step.step_number = index
            step.title = meta["title"]
            step.agent = meta["agent"]
            self.session.add(step)
            self.session.commit()
            steps.append(step)

            if step.status == "failed" and stop_on_failure:
                break
            # A failed step must not cascade: later steps run with whatever
            # context exists and report `skipped` if they need what is missing.
        self._finalise()
        return steps

    def _finalise(self) -> None:
        """Summarise the run.

        ``needs_review`` is a *success* state -- the step produced output that is
        waiting for the teacher. Only a genuinely ``failed`` (or ``skipped``)
        step downgrades the run.
        """
        steps = self.session.exec(
            select(WorkflowStep).where(WorkflowStep.run_id == self.run.id)
        ).all()
        statuses = [s.status for s in steps]
        broken = [s for s in statuses if s in ("failed", "skipped")]
        if not broken:
            self.run.status = "done"
        elif len(broken) < len(statuses):
            self.run.status = "done_with_errors"
        else:
            self.run.status = "failed"
        self.run.finished_at = datetime.now(timezone.utc)
        self.session.add(self.run)
        self.session.commit()


# ---------------------------------------------------------------------------
# Entry point used by the router
# ---------------------------------------------------------------------------
def start_workflow(
    session: Session,
    teacher: Teacher,
    *,
    class_id: int,
    topic: str,
    subject: str = "",
    language: str = "English",
    params: dict[str, Any] | None = None,
) -> WorkflowRun:
    """Create the run, execute every step, return the finished run."""
    params = params or {}
    run = WorkflowRun(
        teacher_id=teacher.id,
        class_id=class_id,
        topic=topic,
        subject=subject,
        language=language,
        status="running",
        started_at=datetime.now(timezone.utc),
    )
    session.add(run)
    session.commit()
    session.refresh(run)

    orchestrator = Orchestrator(session, run, teacher)
    try:
        orchestrator.run_all(params)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Workflow run %s crashed", run.id)
        run.status = "failed"
        run.error = str(exc)
        session.add(run)
        session.commit()
    return run


def rerun_step(
    session: Session, teacher: Teacher, run: WorkflowRun, step_key: str
) -> WorkflowStep:
    """Re-run a single step of an existing run, keeping the rest intact."""
    params = dict(run.context or {})
    orchestrator = Orchestrator(session, run, teacher)
    step = orchestrator.run_step(step_key, params)
    orchestrator._finalise()  # noqa: SLF001 - same module
    return step