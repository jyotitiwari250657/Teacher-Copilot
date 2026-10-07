"""Grader Agent.

Grades one student's answers against a question paper, marks every claim with
a confidence score, and never presents AI marks as final: any answer the model
is unsure about is flagged ``needs_teacher_review``.

Grading rules enforced here (not just in the prompt):
* MCQ / true-false / numeric answers are marked against the key exactly.
* Subjective answers earn partial credit with a one-line justification.
* Any per-question confidence below 0.6 forces ``needs_teacher_review = true``.
"""
from __future__ import annotations

import re
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, model_validator

from .base import BaseAgent

QuestionType = Literal["mcq", "short", "long", "numeric", "true_false"]
Strictness = Literal["lenient", "standard", "strict"]

CONFIDENCE_THRESHOLD = 0.6

# How much of the earned marks survives, per strictness level.
_STRICTNESS_FACTOR = {"lenient": 1.15, "standard": 1.0, "strict": 0.88}

_STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "of", "in", "on", "to", "and",
    "or", "it", "its", "for", "with", "that", "this", "as", "by", "from", "be",
    "has", "have", "had", "at", "we", "they", "you", "can", "will", "not",
}


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class Question(BaseModel):
    id: str
    question: str
    marks: float = Field(default=1.0, gt=0)
    type: QuestionType = "short"
    options: list[str] = Field(default_factory=list)
    answer_key: Optional[str] = None
    model_answer: str = ""


class GraderInput(BaseModel):
    questions: list[Question] = Field(min_length=1)
    answers: dict[str, str] = Field(default_factory=dict)
    student_ref: str = "S01"
    rubric: str = ""
    strictness: Strictness = "standard"
    # Optional: previous class average, used to tune the encouraging tone.
    class_average_pct: Optional[float] = None


class QuestionMark(BaseModel):
    question_id: str
    marks_awarded: float = Field(ge=0)
    max_marks: float = Field(gt=0)
    feedback: str = ""
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class GraderOutput(BaseModel):
    student_ref: str = "S01"
    per_question_marks: list[QuestionMark] = Field(default_factory=list)
    total: float = 0.0
    max_total: float = 0.0
    percentage: float = 0.0
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    topics_to_revisit: list[str] = Field(default_factory=list)
    overall_feedback: str = ""
    needs_teacher_review: bool = False

    @model_validator(mode="after")
    def _enforce_review_rule(self) -> "GraderOutput":
        """The confidence rule is not optional, whatever the model returned."""
        low = [
            m
            for m in self.per_question_marks
            if m.confidence < CONFIDENCE_THRESHOLD
        ]
        if low:
            object.__setattr__(self, "needs_teacher_review", True)
        return self

    @property
    def low_confidence_questions(self) -> list[str]:
        return [
            m.question_id
            for m in self.per_question_marks
            if m.confidence < CONFIDENCE_THRESHOLD
        ]


# ---------------------------------------------------------------------------
# Deterministic helpers (used by mock mode and by post-processing)
# ---------------------------------------------------------------------------
def _norm(text: Any) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", str(text or "").lower()).strip()


def _tokens(text: str) -> set[str]:
    return {t for t in _norm(text).split() if t and t not in _STOPWORDS}


def _extract_number(text: str) -> Optional[float]:
    match = re.search(r"-?\d+(?:\.\d+)?", str(text or "").replace(",", ""))
    return float(match.group()) if match else None


_TRUE = {"true", "yes", "y", "correct", "1", "सही", "हाँ", "haan"}
_FALSE = {"false", "no", "n", "incorrect", "0", "गलत", "नहीं"}


def grade_objective(question: Question, answer: str) -> tuple[float, float, str]:
    """Exact-match grading. Returns (fraction, confidence, feedback)."""
    key = (question.answer_key or "").strip()
    given = (answer or "").strip()

    if not given:
        return 0.0, 0.98, "No answer was given."

    if question.type == "mcq":
        a, b = _norm(given), _norm(key)
        # Accept "B", "b)", "(B)" and "B. option text".
        a_token = a.split()[0] if a else ""
        exact = a == b or (len(a) <= 2 and a_token == b)
        if exact:
            return 1.0, 0.97, "Correct answer."
        return 0.0, 0.97, f"Incorrect. The correct option is {key}."

    if question.type == "true_false":
        a = _norm(given).split()[0] if _norm(given) else ""
        if a in _TRUE and key.lower() in _TRUE:
            return 1.0, 0.96, "Correct."
        if a in _FALSE and key.lower() in _FALSE:
            return 1.0, 0.96, "Correct."
        return 0.0, 0.96, f"Incorrect. The correct answer is {key}."

    if question.type == "numeric":
        got, want = _extract_number(given), _extract_number(key)
        if got is None:
            return 0.0, 0.75, "No number could be read from the answer."
        if want is None:
            return (1.0, 0.8, "Correct.") if got == 0 else (0.0, 0.8, "Incorrect.")
        if abs(got - want) <= max(0.01, abs(want) * 0.01):
            return 1.0, 0.94, "Correct value."
        return 0.0, 0.94, f"Expected {want:g}, wrote {got:g}."

    # short/long with an explicit key still counts as objective
    if key and _norm(given) == _norm(key):
        return 1.0, 0.9, "Matches the expected answer."
    if key and key.lower() in _norm(given):
        return 1.0, 0.88, "Contains the expected answer."
    return 0.0, 0.88, f"Does not match the expected answer ({key})."


def grade_subjective(
    question: Question, answer: str, strictness: Strictness
) -> tuple[float, float, str]:
    """Partial credit by concept coverage. Returns (fraction, confidence, feedback)."""
    answer = (answer or "").strip()
    if not answer:
        return 0.0, 0.95, "No answer was given."

    model = question.model_answer or ""
    answer_tokens = _tokens(answer)
    if not answer_tokens:
        return 0.0, 0.9, "Answer contains no readable words."

    if model:
        model_tokens = _tokens(model)
        covered = answer_tokens & model_tokens
        coverage = len(covered) / max(1, len(model_tokens))
    else:
        # No model answer: reward substance (length) and cap it.
        coverage = min(1.0, len(answer_tokens) / 25.0)

    # Length sanity: a one-word answer cannot earn much on a long question.
    length_factor = 1.0
    if question.type == "long":
        length_factor = min(1.0, 0.45 + len(answer_tokens) / 30.0)
    elif question.type == "short":
        length_factor = min(1.0, 0.55 + len(answer_tokens) / 15.0)

    fraction = min(1.0, coverage * length_factor)
    factor = _STRICTNESS_FACTOR[strictness]
    fraction = min(1.0, fraction * factor)

    # Confidence: high for long clear answers, low for very short ones.
    if len(answer_tokens) < 4:
        confidence = 0.5
    elif len(answer_tokens) < 8:
        confidence = 0.72
    elif coverage < 0.15:
        confidence = 0.58
    else:
        confidence = 0.9

    if fraction >= 0.85:
        feedback = "Excellent - covers the key points of the expected answer."
    elif fraction >= 0.55:
        feedback = "Partially correct - some key points are missing."
    elif fraction > 0:
        feedback = "Limited progress - the answer is on topic but misses most key points."
    else:
        feedback = "Not yet correct - needs a clearer explanation."

    return fraction, confidence, feedback


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """\
You are the Grader for TeacherCopilot, used by school teachers to mark student
work quickly and fairly. Your marks are ALWAYS a draft: a human teacher reviews
and can override anything you produce.

## What you produce
ONE JSON object for ONE student:

{
  "student_ref": string,                 // echo the pseudonymous id you were given
  "per_question_marks": [                 // one entry per question, in order
    {
      "question_id": string,
      "marks_awarded": number,            // 0 to max_marks, decimals allowed
      "max_marks": number,
      "feedback": string,                 // ONE short sentence
      "confidence": number                // 0.0 to 1.0
    }
  ],
  "total": number,
  "max_total": number,
  "percentage": number,                   // 0-100, one decimal place
  "strengths": [string],                  // 1-3 specific, encouraging
  "weaknesses": [string],                 // 1-3 specific, gentle
  "topics_to_revisit": [string],
  "overall_feedback": string,             // 2-3 sentences, encouraging, addressed to the student
  "needs_teacher_review": boolean
}

## Hard rules
1. Reply with ONLY the JSON object. No markdown fences, no commentary.
2. `student_ref` MUST be the pseudonymous id you were given (for example
   "S03"). Never invent a real name; you were not given any.
3. MCQ, true-false and numeric questions are graded EXACTLY against the answer
   key - no partial credit, confidence 0.95 or above.
4. Subjective answers get partial credit proportional to how many of the key
   ideas in the model answer are present, with a one-sentence justification.
5. `confidence` is your own honest certainty:
     0.9+  you are certain
     0.7-0.89  you had to interpret the answer
     below 0.6  you are guessing - set needs_teacher_review = true
6. If ANY question has confidence below 0.6, set needs_teacher_review = true.
   This is checked automatically, so do not try to hide uncertainty.
7. Mark a blank answer 0 with high confidence (0.95) - that is certain.
8. Marks must be 0 <= marks_awarded <= max_marks, and total must equal the sum
   of per_question_marks.
9. Tone: encouraging and specific. Never sarcastic, never comparative to
   other students, never diagnose a learning difficulty.

## Few-shot example
Questions: Q1 mcq 1 mark key "B"; Q2 short 3 marks model "Leaves make food
using sunlight, water and carbon dioxide."
Student S03 answered: Q1 "B", Q2 "Plants use sunlight to make food."
Output:
{
  "student_ref": "S03",
  "per_question_marks": [
    { "question_id": "Q1", "marks_awarded": 1, "max_marks": 1, "feedback": "Correct answer.", "confidence": 0.97 },
    { "question_id": "Q2", "marks_awarded": 2, "max_marks": 3, "feedback": "Partially correct - correctly says sunlight is needed, but water and carbon dioxide are missing.", "confidence": 0.86 }
  ],
  "total": 3,
  "max_total": 4,
  "percentage": 75.0,
  "strengths": ["Identified the correct option confidently", "Uses the word sunlight correctly"],
  "weaknesses": ["Did not name the other two raw materials", "Answer is shorter than expected for a 3-mark question"],
  "topics_to_revisit": ["Raw materials for photosynthesis", "Structure of the leaf"],
  "overall_feedback": "Good work on the objective question and you have the right central idea. Next time, list every material the plant uses so the answer is complete. Keep going - you are close.",
  "needs_teacher_review": false
}
"""


class GraderAgent(BaseAgent[GraderInput, GraderOutput]):
    name = "grader"
    system_prompt = SYSTEM_PROMPT
    input_model = GraderInput
    output_model = GraderOutput
    temperature = 0.2
    max_tokens = 3000
    description = "Marks student answers with per-question confidence and partial credit."

    def build_mock(self, payload: dict[str, Any]) -> dict[str, Any]:
        questions = [Question.model_validate(q) for q in payload.get("questions", [])]
        answers = payload.get("answers") or {}
        student_ref = payload.get("student_ref", "S01")
        strictness = payload.get("strictness", "standard")

        marks: list[dict[str, Any]] = []
        strengths: list[str] = []
        weaknesses: list[str] = []
        topics: list[str] = []
        total = 0.0
        max_total = 0.0

        for question in questions:
            answer = str(answers.get(question.id, "") or "")
            if question.type in ("mcq", "true_false", "numeric"):
                fraction, confidence, feedback = grade_objective(question, answer)
            else:
                fraction, confidence, feedback = grade_subjective(
                    question, answer, strictness
                )

            awarded = round(fraction * question.marks, 2)
            # Never exceed the maximum, even after the lenient bonus.
            awarded = min(awarded, question.marks)
            total += awarded
            max_total += question.marks
            marks.append(
                {
                    "question_id": question.id,
                    "marks_awarded": awarded,
                    "max_marks": question.marks,
                    "feedback": feedback,
                    "confidence": round(confidence, 2),
                }
            )

            if fraction >= 0.85:
                strengths.append(f"Strong answer on {question.id}")
            elif fraction < 0.4:
                weaknesses.append(f"Needs more work on {question.id}")
                if question.model_answer:
                    topics.append(
                        question.model_answer.split(".")[0][:80] or question.id
                    )

        percentage = round((total / max_total * 100) if max_total else 0.0, 1)

        if percentage >= 75:
            tone = "Excellent work this paper. Keep this consistency."
        elif percentage >= 50:
            tone = "Good effort - you understand the main idea of most answers."
        else:
            tone = "Thank you for attempting every question. We will work through these together."

        return {
            "student_ref": student_ref,
            "per_question_marks": marks,
            "total": round(total, 2),
            "max_total": round(max_total, 2),
            "percentage": percentage,
            "strengths": strengths[:3] or ["Attempted every question"],
            "weaknesses": weaknesses[:3] or ["No major gaps spotted"],
            "topics_to_revisit": list(dict.fromkeys(topics))[:4],
            "overall_feedback": f"{tone} Your teacher will review these marks with you.",
            "needs_teacher_review": any(
                m["confidence"] < CONFIDENCE_THRESHOLD for m in marks
            ),
        }

    def postprocess(self, output: GraderOutput, data: GraderInput) -> GraderOutput:
        """Re-derive totals and make sure no question was silently dropped."""
        by_id = {q.id: q for q in data.questions}
        for mark in output.per_question_marks:
            if mark.question_id in by_id:
                mark.max_marks = by_id[mark.question_id].marks
            mark.marks_awarded = max(0.0, min(mark.marks_awarded, mark.max_marks))

        # Append any question the model forgot rather than losing marks.
        answered = {m.question_id for m in output.per_question_marks}
        for question in data.questions:
            if question.id not in answered:
                answer = str(data.answers.get(question.id, "") or "")
                if question.type in ("mcq", "true_false", "numeric"):
                    fraction, confidence, feedback = grade_objective(question, answer)
                else:
                    fraction, confidence, feedback = grade_subjective(
                        question, answer, data.strictness
                    )
                output.per_question_marks.append(
                    QuestionMark(
                        question_id=question.id,
                        marks_awarded=round(
                            min(fraction * question.marks, question.marks), 2
                        ),
                        max_marks=question.marks,
                        feedback=feedback,
                        confidence=round(confidence, 2),
                    )
                )

        # Preserve the paper's question order.
        order = {q.id: i for i, q in enumerate(data.questions)}
        output.per_question_marks.sort(
            key=lambda m: order.get(m.question_id, 10_000)
        )

        output.total = round(sum(m.marks_awarded for m in output.per_question_marks), 2)
        output.max_total = round(sum(m.max_marks for m in output.per_question_marks), 2)
        output.percentage = (
            round(output.total / output.max_total * 100, 1) if output.max_total else 0.0
        )
        if any(m.confidence < CONFIDENCE_THRESHOLD for m in output.per_question_marks):
            output.needs_teacher_review = True
        return output


agent = GraderAgent()
