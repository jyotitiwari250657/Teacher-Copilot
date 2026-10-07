"""Parent Update Agent.

Writes a short, warm, personalised message for a parent about their own child.
Safety rules are enforced in code, not just requested in the prompt:

* The body may only ever mention the one student (templated with
  ``{{student_name}}``, filled in locally after generation).
* WhatsApp bodies are capped at 120 words.
* No comparison to other students, no diagnosis of any learning condition.
* Very low scores or long absence raise ``needs_teacher_review`` so a human
  reads the message before it can be approved.
"""
from __future__ import annotations

import re
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, model_validator

from .base import AgentError, BaseAgent

WHATSAPP_WORD_LIMIT = 120
LOW_SCORE_THRESHOLD = 35.0
LOW_ATTENDANCE_THRESHOLD = 70.0

# Words that would make a message read like a diagnosis. Never emitted.
FORBIDDEN_DIAGNOSTIC = re.compile(
    r"\b(dyslexi\w*|adhd|autis\w*|dyspraxi\w*|depress\w*|retard\w*|"
    r"disabled|disabilit\w*|slow learner|weak student|dull)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class ParentUpdateInput(BaseModel):
    student_ref: str = "S01"
    # Recent results: [{"topic": "Photosynthesis", "percentage": 42.0}, ...]
    recent_scores: list[dict[str, Any]] = Field(default_factory=list)
    overall_percentage: Optional[float] = None
    attendance_pct: float = 100.0
    subject: str = ""
    teacher_notes: str = ""
    tone: Literal["warm", "formal"] = "warm"
    language: Literal["English", "Hindi"] = "English"
    channel: Literal["whatsapp", "email"] = "whatsapp"
    teacher_name: str = ""
    school_name: str = ""
    topic: str = ""


class ParentUpdateOutput(BaseModel):
    student_ref: str = "S01"
    subject_line: str = ""  # email only
    body: str = ""
    word_count: int = 0
    positive_observation: str = ""
    area_to_improve: str = ""
    home_step: str = ""
    # Set locally when the case is sensitive. The model is told to leave these
    # alone, but the code is what actually enforces them.
    needs_teacher_review: bool = False
    review_reasons: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _compute_counts(self) -> "ParentUpdateOutput":
        object.__setattr__(self, "word_count", len(self.body.split()))
        return self


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """\
You are the Parent Update Agent for TeacherCopilot. You write the short message
a teacher sends home about ONE student. You are writing to a parent who loves
their child and is busy - respect their time.

## What you produce
A single JSON object:

{
  "student_ref": string,                 // echo the pseudonymous id given to you
  "subject_line": string,                // EMAIL ONLY, under 8 words; "" for WhatsApp
  "body": string,                       // the message itself, see length rules
  "positive_observation": string,        // ONE concrete thing the child did well
  "area_to_improve": string,            // ONE concrete, gentle thing to work on
  "home_step": string,                  // ONE thing the parent can do at home, 15 minutes or less
  "needs_teacher_review": false,        // leave false; the system sets this
  "review_reasons": []                  // leave empty; the system sets this
}

## Length rules
- channel "whatsapp": body is PLAIN TEXT, no markdown, no bullet points, and
  at most 120 words. Write it as you would type it in a chat to a parent.
- channel "email": body may be 3-5 short sentences plus a greeting and sign-off,
  and subject_line is required.

## Hard rules
1. Reply with ONLY the JSON object. No markdown fences, no commentary.
2. The message MUST contain all three of: one positive observation, one area to
   improve, and one concrete step the parent can take at home.
3. NEVER mention another student, another family, or compare this child to
   anyone. "Other students are doing better" is forbidden.
4. NEVER diagnose or label. Do not use words like dyslexia, ADHD, slow learner,
   weak, stupid, careless, or lazy. Describe the WORK, not the child.
5. Refer to the child as "{{student_name}}" - this exact placeholder. The system
   replaces it with the real name afterwards. Never write a real name; you are
   not given one and must not invent one.
6. Address the parent as the parent (for example "Dear Parent" or the
   placeholder "{{parent_name}}"). Sign off as "{{teacher_name}}" or "{{school_name}}".
7. Tone: "warm" is encouraging and conversational. "formal" is polite and brief.
8. Write in the requested language (English or Hindi). For Hindi use natural
   Devanagari a parent will understand; keep it plain, not literary.

## Few-shot example
Input: student_ref "S03", overall 78%, attendance 92%, subject Science,
tone warm, language English, channel whatsapp.
Output:
{
  "student_ref": "S03",
  "subject_line": "",
  "body": "Dear Parent, {{student_name}} has been working hard in Science this week and scored 78 percent, which is a real improvement. The area to work on is writing full answers in the subjective questions, where a few marks are lost for short responses. At home, please ask {{student_name}} to explain one Science question in their own words for five minutes each evening. Thank you for your support. - {{school_name}}",
  "positive_observation": "Scored 78 percent, an improvement on the last paper.",
  "area_to_improve": "Writing longer, more complete answers to subjective questions.",
  "home_step": "Ask the child to explain one Science question aloud for five minutes each evening.",
  "needs_teacher_review": false,
  "review_reasons": []
}
"""


def _words(text: str) -> int:
    return len((text or "").split())


def _truncate_words(text: str, limit: int) -> str:
    parts = text.split()
    if len(parts) <= limit:
        return text
    # Cut on a sentence boundary if one is close to the limit.
    for end in range(len(parts), 0, -1):
        candidate = " ".join(parts[:end])
        if _words(candidate) <= limit and candidate.rstrip().endswith((".", "!", "?")):
            return candidate
    return " ".join(parts[: max(1, limit - 1)]) + "."


def flag_sensitive(
    overall: Optional[float], attendance: float
) -> tuple[bool, list[str]]:
    """Deterministic safeguarding check - the model cannot skip this."""
    reasons: list[str] = []
    if overall is not None and overall < LOW_SCORE_THRESHOLD:
        reasons.append(
            f"Overall score is {overall:g}% - below {LOW_SCORE_THRESHOLD:g}%. "
            "Please review the wording before sending."
        )
    if attendance < LOW_ATTENDANCE_THRESHOLD:
        reasons.append(
            f"Attendance is {attendance:g}% - below {LOW_ATTENDANCE_THRESHOLD:g}%. "
            "Please check the message is appropriate given the absence."
        )
    return bool(reasons), reasons


def sanitize(body: str) -> str:
    """Replace diagnostic or comparative language with neutral wording."""
    replacements = {
        r"\bslow learner\b": "student who needs more time",
        r"\bweak student\b": "student who needs more practice",
        r"\bdull\b": "quiet",
        r"\bstupid\b": "",
        r"\blazy\b": "needs reminders",
        r"\bcareless\b": "forgetful",
        r"\bdyslexi\w*": "",
        r"\badhd\b": "",
        r"\bautis\w*": "",
        r"\bdepress\w*": "",
        r"\bdisabilit\w*": "",
    }
    text = body
    # Fix the copula form first so "is careless" -> "forgets some details".
    for copula, adjective, good in (
        ("is|are", "careless", "forgets some details"),
        ("is|are", "lazy", "needs reminders"),
        ("is|are", "dull", "works quietly"),
    ):
        text = re.sub(
            rf"\b(?:{copula})\s+{adjective}\b", good, text, flags=re.IGNORECASE
        )
    for pattern, replacement in replacements.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    # Remove "other students ..." clauses outright.
    text = re.sub(
        r"[^.]*\bother students?\b[^.]*\.", "", text, flags=re.IGNORECASE
    )
    text = re.sub(r"\s{2,}", " ", text).strip()
    return text


class ParentUpdateAgent(BaseAgent[ParentUpdateInput, ParentUpdateOutput]):
    name = "parent_update"
    system_prompt = SYSTEM_PROMPT
    input_model = ParentUpdateInput
    output_model = ParentUpdateOutput
    temperature = 0.5
    max_tokens = 1500
    description = "Writes short, safe, personalised parent messages awaiting approval."

    # ---- mock -----------------------------------------------------------
    def build_mock(self, payload: dict[str, Any]) -> dict[str, Any]:
        subject = payload.get("subject") or "their studies"
        lang = payload.get("language", "English")
        tone = payload.get("tone", "warm")
        channel = payload.get("channel", "whatsapp")
        ref = payload.get("student_ref", "S01")
        attendance = float(payload.get("attendance_pct", 100.0) or 100.0)
        scores = payload.get("recent_scores") or []
        overall = payload.get("overall_percentage")
        if overall is None and scores:
            try:
                overall = sum(float(s.get("percentage", 0)) for s in scores) / len(scores)
            except (TypeError, ValueError):
                overall = None
        if overall is None:
            overall = 0.0
        overall = float(overall)
        notes = (payload.get("teacher_notes") or "").strip()

        positive, improve, step = _three_things(
            subject, overall, attendance, scores, notes, lang, tone
        )

        if channel == "email":
            subject_line = _subject_line(subject, overall, lang)
            body = _email_body(positive, improve, step, lang, tone, subject)
        else:
            subject_line = ""
            body = _whatsapp_body(positive, improve, step, lang, tone, subject)

        return {
            "student_ref": ref,
            "subject_line": subject_line,
            "body": body,
            "positive_observation": positive,
            "area_to_improve": improve,
            "home_step": step,
            "needs_teacher_review": False,  # set by postprocess
            "review_reasons": [],
        }

    def postprocess(
        self, output: ParentUpdateOutput, data: ParentUpdateInput
    ) -> ParentUpdateOutput:
        # 1. Never ship diagnostic or comparative wording.
        output.body = sanitize(output.body)
        output.area_to_improve = sanitize(output.area_to_improve)

        # 2. WhatsApp length cap.
        if data.channel == "whatsapp" and _words(output.body) > WHATSAPP_WORD_LIMIT:
            output.body = _truncate_words(output.body, WHATSAPP_WORD_LIMIT)

        # 3. Email must have a subject line.
        if data.channel == "email" and not output.subject_line.strip():
            output.subject_line = f"Update on {data.student_ref}'s progress"

        # 4. The three required elements must be present.
        missing = [
            label
            for label, value in (
                ("a positive observation", output.positive_observation),
                ("an area to improve", output.area_to_improve),
                ("a home step", output.home_step),
            )
            if not value.strip()
        ]
        if missing:
            raise AgentError(
                f"The parent update is missing {', '.join(missing)}. Please regenerate.",
                agent=self.name,
            )

        # 5. Safeguarding flags - decided by code, never by the model.
        needs_review, reasons = flag_sensitive(data.overall_percentage, data.attendance_pct)
        if FORBIDDEN_DIAGNOSTIC.search(output.body):
            reasons.append("Message contained wording that could label the child; rewritten.")
        output.needs_teacher_review = needs_review or bool(reasons)
        output.review_reasons = reasons

        output.word_count = _words(output.body)
        return output


# ---------------------------------------------------------------------------
# Mock copy
# ---------------------------------------------------------------------------
def _three_things(
    subject: str,
    overall: float,
    attendance: float,
    scores: list[dict[str, Any]],
    notes: str,
    lang: str,
    tone: str,
) -> tuple[str, str, str]:
    if lang == "Hindi":
        if overall >= 70:
            positive = f"{subject} में अंक अच्छे हैं ({overall:g}%) और समझझ दिख रही है"
        elif overall >= 40:
            positive = f"{subject} में निरंतर मेहनत की है और आधार समझ बन रही है"
        else:
            positive = f"{subject} के पाठ में उन्होंने हर प्रश्न का उत्तर लिखने का प्रयास किया"
        improve = "उत्तर थोड़े विस्तार से लिखने की आवश्यकता है ताकि सभी अंक मिल सकें"
        step = "कृपया प्रत्येक दिन पाँच मिनट घर पर पिछले दिन का पाठ दोहरवाएँ"
        if notes:
            improve = notes[:120]
        return positive, improve, step

    if overall >= 70:
        positive = (
            f"has been working well in {subject} and scored {overall:g} percent this term"
        )
    elif overall >= 40:
        positive = (
            f"keeps putting in steady effort in {subject} and understands the basics"
        )
    else:
        positive = (
            f"attends every class carefully in {subject} and attempts each question"
        )
    improve = (
        "writing longer, more complete answers in the subjective questions, where "
        "a few marks are lost for short replies"
    )
    step = (
        f"ask {{{{student_name}}}} to explain one {subject} question out loud for five "
        "minutes each evening"
    )
    if notes:
        improve = notes[:160]
    if tone == "formal":
        step = step.replace("ask", "please ask")
    return positive, improve, step


def _whatsapp_body(
    positive: str, improve: str, step: str, lang: str, tone: str, subject: str
) -> str:
    if lang == "Hindi":
        return (
            f"नमस्ते, {{{{student_name}}}} {subject} में अच्छा कर रहा/रही है - {positive}। "
            f"सुधारने की बात: {improve}। "
            f"घर पर आप यह कर सकते हैं: {step}। "
            "आपके सहयोग के लिए धन्यवाद। धन्यवाद, {{school_name}}"
        )
    greeting = "Dear Parent," if tone == "formal" else "Hello,"
    return (
        f"{greeting} {{{{student_name}}}} {positive}. "
        f"One thing to work on: {improve}. "
        f"At home, you could {step}. "
        f"Thank you for your support. - {{{{school_name}}}}"
    )


def _email_body(
    positive: str, improve: str, step: str, lang: str, tone: str, subject: str
) -> str:
    if lang == "Hindi":
        return (
            f"प्रिय अभिभावक,\n\n"
            f"मैं आपको {{{{student_name}}}} की प्रगति के बारे में सूचित करना चाहती हूँ। "
            f"सकारात्मक बात: {positive}।\n\n"
            f"सुधारने का क्षेत्र: {improve}।\n\n"
            f"घर पर आप कदम: {step}। यह लगभग पाँच मिनट का काम है।\n\n"
            f"कृपया किसी भी प्रश्न के लिए मुझसे संपर्क करें।\n\n"
            f"सादर,\n{{{{teacher_name}}}}\n{{{{school_name}}}}"
        )
    greeting = "Dear Parent," if tone == "formal" else "Dear Parent,"
    return (
        f"{greeting}\n\n"
        f"I am writing to share how {{{{student_name}}}} is getting on.\n\n"
        f"A positive observation: {positive}.\n\n"
        f"An area to work on: {improve}.\n\n"
        f"A step you could take at home: {step}. It takes about five minutes a day.\n\n"
        f"Please do feel free to contact me if you would like to talk.\n\n"
        f"Kind regards,\n{{{{teacher_name}}}}\n{{{{school_name}}}}"
    )


def _subject_line(subject: str, overall: float, lang: str) -> str:
    if lang == "Hindi":
        return f"{subject} में प्रगति की जानकारी"
    return f"Progress update - {subject} ({overall:g}%)"


agent = ParentUpdateAgent()
