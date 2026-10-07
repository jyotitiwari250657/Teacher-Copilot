"""Demo data.

Seeds one teacher, one class with twelve students across a realistic spread of
ability, a ten-question Photosynthesis paper, and sample answers so the whole
weekly workflow can be demonstrated end to end without typing anything.
"""
from __future__ import annotations

import logging
import random
from typing import Any

from sqlmodel import Session, select

from ..config import settings
from ..models import Assessment, SchoolClass, Student, Submission, Teacher
from ..security import hash_password

logger = logging.getLogger("teachercopilot.seed")

# ---------------------------------------------------------------------------
# Question paper: 6 MCQ (1 mark) + 4 subjective (10 marks) = 16 total
# ---------------------------------------------------------------------------
PHOTOSYNTHESIS_QUESTIONS: list[dict[str, Any]] = [
    {
        "id": "Q1",
        "question": "Which pigment gives leaves their green colour?",
        "marks": 1,
        "type": "mcq",
        "options": ["Haemoglobin", "Chlorophyll", "Melanin", "Keratin"],
        "answer_key": "Chlorophyll",
    },
    {
        "id": "Q2",
        "question": "Which gas do plants take in from the air for photosynthesis?",
        "marks": 1,
        "type": "mcq",
        "options": ["Oxygen", "Nitrogen", "Carbon dioxide", "Hydrogen"],
        "answer_key": "Carbon dioxide",
    },
    {
        "id": "Q3",
        "question": "The tiny openings on the surface of a leaf are called ____.",
        "marks": 1,
        "type": "mcq",
        "options": ["Veins", "Stomata", "Sepals", "Petals"],
        "answer_key": "Stomata",
    },
    {
        "id": "Q4",
        "question": "Where does photosynthesis take place inside the cell?",
        "marks": 1,
        "type": "mcq",
        "options": ["Nucleus", "Chloroplast", "Vacuole", "Cell wall"],
        "answer_key": "Chloroplast",
    },
    {
        "id": "Q5",
        "question": "Which of these is the food made by a plant during photosynthesis?",
        "marks": 1,
        "type": "mcq",
        "options": ["Protein", "Glucose", "Cellulose", "Fat"],
        "answer_key": "Glucose",
    },
    {
        "id": "Q6",
        "question": "Sunlight is stored as energy in the glucose molecule produced by photosynthesis.",
        "marks": 1,
        "type": "true_false",
        "options": ["True", "False"],
        "answer_key": "True",
    },
    {
        "id": "Q7",
        "question": "Write the word equation for photosynthesis.",
        "marks": 2,
        "type": "short",
        "model_answer": (
            "Carbon dioxide plus water, in the presence of sunlight and chlorophyll, "
            "gives glucose plus oxygen."
        ),
    },
    {
        "id": "Q8",
        "question": "Explain how water reaches the leaves of a tall plant.",
        "marks": 3,
        "type": "long",
        "model_answer": (
            "Water is absorbed by the root hairs from the soil. It moves up the xylem "
            "vessels through the stem to the leaves. This upward movement is called the "
            "transpiration pull, and it is helped by evaporation of water from the "
            "leaves."
        ),
    },
    {
        "id": "Q9",
        "question": "Why do we say plants 'make their own food'?",
        "marks": 2,
        "type": "short",
        "model_answer": (
            "Plants make glucose from simple substances like carbon dioxide and water "
            "using sunlight, instead of taking ready-made food from other organisms."
        ),
    },
    {
        "id": "Q10",
        "question": "A plant is kept in a dark cupboard for three days and its leaves turn yellow. Explain why.",
        "marks": 3,
        "type": "long",
        "model_answer": (
            "Without light there is no photosynthesis, so chlorophyll is not made and "
            "the existing chlorophyll breaks down. The green colour disappears and the "
            "yellow pigments already present in the leaf become visible. Food stored in "
            "the leaf is also used up in respiration."
        ),
    },
]

# ---------------------------------------------------------------------------
# Sample answers, in three quality tiers so grading produces a real spread
# ---------------------------------------------------------------------------
_ANSWERS = {
    "strong": {
        "Q1": "Chlorophyll",
        "Q2": "Carbon dioxide",
        "Q3": "Stomata",
        "Q4": "Chloroplast",
        "Q5": "Glucose",
        "Q6": "True",
        "Q7": "Carbon dioxide + water --(sunlight, chlorophyll)--> glucose + oxygen",
        "Q8": (
            "Water is absorbed from the soil by the root hairs. It then travels upward "
            "through the xylem vessels in the stem and reaches the leaves. This upward "
            "pull happens because water evaporates from the leaf surface, which is "
            "called transpiration pull."
        ),
        "Q9": (
            "Because plants manufacture their own glucose from carbon dioxide and water "
            "using sunlight, rather than taking food that is already made by other "
            "living things."
        ),
        "Q10": (
            "In the dark there is no sunlight, so photosynthesis stops and chlorophyll "
            "is not produced. The chlorophyll already in the leaf breaks down, the "
            "green colour disappears, and the yellow pigments that were hidden become "
            "visible. The stored food is also used up in respiration."
        ),
    },
    "average": {
        "Q1": "Chlorophyll",
        "Q2": "Carbon dioxide",
        "Q3": "Stomata",
        "Q4": "Chloroplast",
        "Q5": "Glucose",
        "Q6": "True",
        "Q7": "Carbon dioxide + water gives glucose + oxygen",
        "Q8": (
            "Water goes into the root hairs from the soil. Then it goes up the stem "
            "through the xylem and reaches the leaves."
        ),
        "Q9": "Plants make glucose themselves using sunlight instead of eating food.",
        "Q10": (
            "The plant did not get sunlight so it could not make food, and the green "
            "colour went away."
        ),
    },
    "weak": {
        "Q1": "Chlorophyll",
        "Q2": "Oxygen",
        "Q3": "Veins",
        "Q4": "Chloroplast",
        "Q5": "Glucose",
        "Q6": "True",
        "Q7": "plants make food",
        "Q8": "The roots take the water and it goes to the leaves.",
        "Q9": "Because plants have leaves.",
        "Q10": "It became old.",
    },
}

# name, roll, parent, phone, email, language, attendance, tier
_STUDENTS: list[tuple[str, str, str, str, str, str, float, str, str]] = [
    ("Aarav Sharma", "1", "Mr. Rajesh Sharma", "+919810001001", "rajesh.sharma@example.com",
     "English", 94.0, "strong", ""),
    ("Diya Patel", "2", "Mrs. Meera Patel", "+919810001002", "meera.patel@example.com",
     "English", 88.0, "average", "Shy in oral work; encourage to speak up."),
    ("Ishaan Verma", "3", "Mr. Sunil Verma", "+919810001003", "sunil.verma@example.com",
     "Hindi", 61.0, "weak", "Missed two weeks in September."),
    ("Ananya Iyer", "4", "Mrs. Kavitha Iyer", "+919810001004", "kavitha.iyer@example.com",
     "English", 97.0, "average", ""),
    ("Vihaan Reddy", "5", "Mr. Ravi Reddy", "+919810001005", "ravi.reddy@example.com",
     "Hindi", 85.0, "average", ""),
    ("Zoya Khan", "6", "Mrs. Ayesha Khan", "+919810001006", "ayesha.khan@example.com",
     "Hindi", 92.0, "strong", ""),
    ("Arjun Nair", "7", "Mr. Biju Nair", "+919810001007", "biju.nair@example.com",
     "English", 99.0, "strong", "Leads the science club."),
    ("Meera Joshi", "8", "Mr. Hari Joshi", "+919810001008", "hari.joshi@example.com",
     "Hindi", 58.0, "weak", "Family is going through a difficult time; be sensitive."),
    ("Kabir Singh", "9", "Mr. Amar Singh", "+919810001009", "amar.singh@example.com",
     "English", 90.0, "average", ""),
    ("Saanvi Gupta", "10", "Mrs. Neha Gupta", "+919810001010", "neha.gupta@example.com",
     "English", 96.0, "strong", ""),
    ("Reyansh Das", "11", "Mr. Pradip Das", "+919810001011", "pradip.das@example.com",
     "Hindi", 73.0, "average", ""),
    ("Ira Menon", "12", "Mrs. Latha Menon", "+910000000012", "latha.menon@example.com",
     "English", 95.0, "strong", ""),
]


def seed_demo_data(session: Session, *, force: bool = False) -> dict[str, Any]:
    """Create the demo teacher, class, students, paper and sample submissions.

    Idempotent: calling it again does nothing unless ``force`` is set.
    """
    existing = session.exec(
        select(Teacher).where(Teacher.email == settings.demo_teacher_email)
    ).first()
    if existing and not force:
        return {"created": False, "teacher_id": existing.id}

    if existing and force:
        session.delete(existing)
        session.commit()

    teacher = Teacher(
        name="Priya Sharma",
        email=settings.demo_teacher_email,
        hashed_password=hash_password(settings.demo_teacher_password),
        school_name="Delhi Public School",
        subject="Science",
        preferred_language="English",
        default_tone="warm",
    )
    session.add(teacher)
    session.commit()
    session.refresh(teacher)

    school_class = SchoolClass(
        name="Class 8-B",
        grade="8",
        section="B",
        subject="Science",
        teacher_id=teacher.id,
    )
    session.add(school_class)
    session.commit()
    session.refresh(school_class)

    students: list[Student] = []
    for name, roll, parent, phone, email, lang, attendance, tier, notes in _STUDENTS:
        student = Student(
            name=name,
            roll_no=roll,
            class_id=school_class.id,
            parent_name=parent,
            parent_phone=phone,
            parent_email=email,
            preferred_language=lang,
            attendance_pct=attendance,
            teacher_notes=notes,
        )
        session.add(student)
        students.append(student)
    session.commit()
    for student in students:
        session.refresh(student)

    assessment = Assessment(
        teacher_id=teacher.id,
        class_id=school_class.id,
        title="Photosynthesis - Unit Test 1",
        subject="Science",
        topic="Photosynthesis",
        questions=PHOTOSYNTHESIS_QUESTIONS,
        total_marks=float(sum(q["marks"] for q in PHOTOSYNTHESIS_QUESTIONS)),
    )
    session.add(assessment)
    session.commit()
    session.refresh(assessment)

    rng = random.Random(20240501)
    for student, spec in zip(students, _STUDENTS):
        tier = spec[7]
        answers = dict(_ANSWERS[tier])
        # Small natural variation so no two scripts are byte-identical.
        if tier == "average" and rng.random() < 0.5:
            answers["Q6"] = "True"
        session.add(
            Submission(
                assessment_id=assessment.id,
                student_id=student.id,
                answers=answers,
                source="typed",
                raw_text="",
            )
        )
    session.commit()

    logger.info("Seeded demo teacher %s with class %s", teacher.email, school_class.name)
    return {
        "created": True,
        "teacher_id": teacher.id,
        "class_id": school_class.id,
        "assessment_id": assessment.id,
        "student_count": len(students),
    }


def sample_answers_for(assessment: Assessment, tier: str = "average") -> dict[str, str]:
    """Helper used by the orchestrator's demo mode."""
    return dict(_ANSWERS.get(tier, _ANSWERS["average"]))


# Maps a student index to the answer tier used when seeding, so the
# orchestrator's demo mode reproduces the same spread of results.
_TIER_CYCLE = ["strong", "average", "weak", "average", "strong"]


def tier_for_index(index: int) -> str:
    """Spread a class evenly across the three answer tiers."""
    return _TIER_CYCLE[index % len(_TIER_CYCLE)]


def seed_time_saved_backfill(session: Session) -> None:
    """Optional helper used by the dashboard to demo the weekly chart."""
    from datetime import datetime, timedelta, timezone

    from ..models import TimeSavedLog

    if session.exec(select(TimeSavedLog)).first():
        return
    now = datetime.now(timezone.utc)
    pattern = [
        ("lesson_plan", 2, settings.minutes_lesson_plan),
        ("grading", 6, settings.minutes_grading_per_paper),
        ("differentiation", 1, settings.minutes_differentiated_worksheets),
        ("parent_message", 4, settings.minutes_parent_message),
    ]
    for weeks_ago in range(5, -1, -1):
        for task_type, count, minutes in pattern:
            session.add(
                TimeSavedLog(
                    teacher_id=1,
                    task_type=task_type,
                    task_count=count,
                    minutes_saved=count * minutes,
                    created_at=now - timedelta(weeks=weeks_ago),
                )
            )
    session.commit()