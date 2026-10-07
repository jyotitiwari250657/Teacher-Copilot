"""Differentiation Agent.

Produces three parallel versions of the same material (Support / Core /
Extension) that all teach the SAME learning objective, each with its own
8-10 question worksheet and answer key, plus a suggested grouping of students
derived from real grading data.

Student identities never leave the backend: the agent sees pseudonymous refs
like ``S04`` and the router maps them back to names locally.
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, model_validator

from .base import BaseAgent

Level = Literal["support", "core", "extension"]
QuestionType = Literal["mcq", "short", "long", "numeric", "true_false"]


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class LevelInput(BaseModel):
    topic: str
    lesson_plan: dict[str, Any] = Field(default_factory=dict)
    language: Literal["English", "Hindi"] = "English"
    # [{"student_ref": "S01", "percentage": 82.0}, ...]
    performance: list[dict[str, Any]] = Field(default_factory=list)
    manual_levels: dict[str, str] = Field(default_factory=dict)
    grade: str = ""
    notes: str = ""


class WorksheetQuestion(BaseModel):
    id: str
    question: str
    marks: float = 1.0
    type: QuestionType = "short"
    hint: str = ""


class AnswerKeyItem(BaseModel):
    question_id: str
    answer: str
    marks: float = 1.0


class LevelMaterial(BaseModel):
    level: Level
    what_changed: str = ""
    content: str = ""
    key_points: list[str] = Field(default_factory=list)
    scaffolds: list[str] = Field(default_factory=list)
    worksheet: list[WorksheetQuestion] = Field(default_factory=list)
    answer_key: list[AnswerKeyItem] = Field(default_factory=list)


class Grouping(BaseModel):
    level: Level
    student_refs: list[str] = Field(default_factory=list)
    rationale: str = ""


class DifferentiationOutput(BaseModel):
    topic: str
    learning_objective: str = ""
    support: LevelMaterial
    core: LevelMaterial
    extension: LevelMaterial
    groupings: list[Grouping] = Field(default_factory=list)
    grouping_rationale: str = ""

    @model_validator(mode="after")
    def _check_levels_present(self) -> "DifferentiationOutput":
        for name in ("support", "core", "extension"):
            material = getattr(self, name)
            if material.level != name:
                material.level = name  # type: ignore[assignment]
        return self


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """\
You are the Differentiation Agent for TeacherCopilot. You take one lesson topic
or plan and rewrite it three times so a mixed-ability class can all work on the
SAME learning objective together.

## What you produce
A single JSON object:

{
  "topic": string,
  "learning_objective": string,             // the ONE shared objective
  "support": {                              // below grade level
    "level": "support",
    "what_changed": string,                 // ONE line: what is different here
    "content": string,                       // short, simple explanation
    "key_points": [string],                 // 3-4 very short points
    "scaffolds": [string],                   // hints, sentence starters, visuals described in words
    "worksheet": [                           // 8-10 questions
      { "id": string, "question": string, "marks": number, "type": "mcq"|"short"|"long"|"numeric"|"true_false", "hint": string }
    ],
    "answer_key": [ { "question_id": string, "answer": string, "marks": number } ]
  },
  "core": { ...same shape, "level": "core"... },
  "extension": { ...same shape, "level": "extension"... },
  "groupings": [
    { "level": "support"|"core"|"extension", "student_refs": [string], "rationale": string }
  ],
  "grouping_rationale": string              // how the split was decided
}

## Hard rules
1. Reply with ONLY the JSON object. No markdown fences, no commentary.
2. ALL THREE VERSIONS MUST TEACH THE SAME LEARNING OBJECTIVE. Different
   wording, different scaffolding, different question types - never a
   different topic.
3. `student_refs` are pseudonymous ids like "S03". NEVER invent or use real
   student names; you were not given any, and you must not guess them.
4. Each worksheet has 8-10 questions. Each answer_key entry must match a
   worksheet question id exactly, with the same marks.
5. How the levels differ:
   - support:  simpler words and shorter sentences, one idea at a time,
               sentence starters, a fully worked example, a "what to do"
               checklist, visuals described in words ("draw a circle").
   - core:     the standard explanation a student of this grade would expect.
   - extension: higher-order thinking - 'what if', design, evaluate,
               real-world challenges, open-ended problems with no single
               right answer, and questions that ask students to justify.
6. Every `what_changed` is ONE short line naming the single biggest change.
7. Prose must be in the requested language (English or Hindi).

## Few-shot example
Input: topic="Photosynthesis", learning objective = explain how plants make food.
Output (abbreviated - worksheets elided):
{
  "topic": "Photosynthesis",
  "learning_objective": "Explain how a plant uses sunlight to make food",
  "support": {
    "level": "support",
    "what_changed": "Shorter sentences, a fully worked example, and sentence starters for every answer.",
    "content": "Plants make their own food. They use sunlight, water and air. The food is made in the leaves.",
    "key_points": ["Sunlight gives energy", "Water comes from the roots", "Air gives carbon dioxide"],
    "scaffolds": [
      "Start your answer: 'A plant makes food by ...'",
      "Draw a leaf and label it",
      "If you are stuck, look at the worked example on the board"
    ],
    "worksheet": [ "8 questions, each with a hint" ],
    "answer_key": [ "8 matching entries" ]
  },
  "core": {
    "level": "core",
    "what_changed": "Standard grade-level explanation with labelled steps and a diagram to complete.",
    "content": "Photosynthesis is the process by which green plants make food using sunlight...",
    "key_points": ["Chlorophyll traps light", "Water and CO2 combine", "Glucose and oxygen are produced"],
    "scaffolds": ["Complete the half-drawn diagram", "Use the step list as a checklist"],
    "worksheet": [ "9 questions" ],
    "answer_key": [ "9 matching entries" ]
  },
  "extension": {
    "level": "extension",
    "what_changed": "Open-ended investigation and evaluation questions instead of recall.",
    "content": "Design an experiment to test what happens to photosynthesis when light is removed...",
    "key_points": ["Identify the variables", "Justify the control", "Predict and explain"],
    "scaffolds": ["Consider what a fair test requires"],
    "worksheet": [ "10 open questions" ],
    "answer_key": [ "10 model answers" ]
  },
  "groupings": [
    { "level": "support", "student_refs": ["S01", "S02", "S03"], "rationale": "Scored below 40% and needs a scaffold to start." },
    { "level": "core", "student_refs": ["S04", "S05"], "rationale": "Scored between 40% and 75%." },
    { "level": "extension", "student_refs": ["S06"], "rationale": "Scored above 75%." }
  ],
  "grouping_rationale": "Grouped by the latest paper percentage: below 40%, 40-75%, above 75%."
}
"""


# ---------------------------------------------------------------------------
# Grouping math (deterministic, used in mock mode and by the API)
# ---------------------------------------------------------------------------
def assign_levels(
    performance: list[dict[str, Any]], manual_levels: Optional[dict[str, str]] = None
) -> list[Grouping]:
    """Split students into support/core/extension by score, honouring overrides."""
    manual_levels = manual_levels or {}
    buckets: dict[str, list[str]] = {"support": [], "core": [], "extension": []}
    used_manual: set[str] = set()

    for entry in performance:
        ref = str(entry.get("student_ref", "")).strip()
        if not ref:
            continue
        forced = manual_levels.get(ref)
        if forced in buckets:
            buckets[forced].append(ref)
            used_manual.add(ref)
            continue
        try:
            pct = float(entry.get("percentage", 0.0))
        except (TypeError, ValueError):
            pct = 0.0
        if pct < 40:
            buckets["support"].append(ref)
        elif pct < 75:
            buckets["core"].append(ref)
        else:
            buckets["extension"].append(ref)

    return [
        Grouping(
            level="support",
            student_refs=buckets["support"],
            rationale=(
                "Scored below 40% on the last paper, or placed here by the teacher. "
                "They get the scaffolded version to start from."
            ),
        ),
        Grouping(
            level="core",
            student_refs=buckets["core"],
            rationale="Scored between 40% and 75%; the standard explanation matches their current level.",
        ),
        Grouping(
            level="extension",
            student_refs=buckets["extension"],
            rationale="Scored above 75%; they get open-ended, higher-order tasks.",
        ),
    ]


class DifferentiationAgent(BaseAgent[LevelInput, DifferentiationOutput]):
    name = "differentiation"
    system_prompt = SYSTEM_PROMPT
    input_model = LevelInput
    output_model = DifferentiationOutput
    temperature = 0.7
    max_tokens = 6000
    description = "Rewrites one lesson three ways and groups students by need."

    # ---- mock -----------------------------------------------------------
    def build_mock(self, payload: dict[str, Any]) -> dict[str, Any]:
        topic = payload.get("topic", "the topic")
        lang = payload.get("language", "English")
        grade = payload.get("grade", "")
        performance = payload.get("performance") or []
        manual = payload.get("manual_levels") or {}

        objective = _objective(topic, lang)
        levels = {
            "support": _level_material("support", topic, objective, lang),
            "core": _level_material("core", topic, objective, lang),
            "extension": _level_material("extension", topic, objective, lang),
        }
        groupings = assign_levels(performance, manual)
        return {
            "topic": topic,
            "learning_objective": objective,
            **levels,
            "groupings": [g.model_dump() for g in groupings],
            "grouping_rationale": (
                "Grouped by the percentage on the most recent graded paper: "
                "below 40% = support, 40-75% = core, above 75% = extension. "
                "You can move any student by hand."
            ),
        }

    def postprocess(
        self, output: DifferentiationOutput, data: LevelInput
    ) -> DifferentiationOutput:
        for name in ("support", "core", "extension"):
            material = getattr(output, name)
            _ensure_worksheet(material, data.topic)

        if not output.groupings:
            output.groupings = assign_levels(data.performance, data.manual_levels)
        if not output.learning_objective.strip():
            output.learning_objective = _objective(data.topic, data.language)
        return output


def _ensure_worksheet(material: LevelMaterial, topic: str) -> None:
    """Guarantee 8-10 questions and a matching answer key."""
    if len(material.worksheet) < 8:
        template = {
            "support": ["What is the main idea of {t}?",
                        "Name one part of {t}.",
                        "What do plants need to make food?",
                        "Draw a simple picture of {t}.",
                        "What happens if we change one thing?",
                        "Write one sentence about {t}.",
                        "What did you learn today about {t}?",
                        "Circle the correct word from the word bank."],
            "core": ["Define {t} in your own words.",
                     "Explain the main steps of {t}.",
                     "Give one example of {t} from daily life.",
                     "What would happen if one condition changed? Why?",
                     "Label the diagram of {t} correctly.",
                     "Compare {t} with something you already know.",
                     "List three facts about {t} from the lesson.",
                     "Write a short paragraph about {t}.",
                     "Why is {t} important?"],
            "extension": ["Design an investigation of {t} and list the variables.",
                          "What if the conditions for {t} changed suddenly? Predict and justify.",
                          "Evaluate: is the explanation given for {t} complete? Defend your answer.",
                          "Create a real-world problem about {t} and solve it.",
                          "Compare two different explanations of {t} and choose the stronger one.",
                          "How would {t} affect food production in your village? Argue your case.",
                          "Write a news report about a discovery related to {t}.",
                          "Identify the limits of what we know about {t}.",
                          "Design a model that demonstrates {t}.",
                          "Debate: is {t} more important than the other processes in the unit?"],
        }[material.level]

        for i in range(8 - len(material.worksheet)):
            n = len(material.worksheet) + 1
            material.worksheet.append(
                WorksheetQuestion(
                    id=f"{material.level[0].upper()}{n}",
                    question=template[i % len(template)].format(t=topic),
                    marks=1.0,
                    type="short",
                    hint="Look back at your class notes." if material.level == "support" else "",
                )
            )
    elif len(material.worksheet) > 10:
        material.worksheet = material.worksheet[:10]

    # Rebuild the answer key so ids always match.
    by_id = {q.id: q for q in material.worksheet}
    material.answer_key = [
        AnswerKeyItem(
            question_id=item.question_id,
            answer=item.answer,
            marks=by_id[item.question_id].marks,
        )
        for item in material.answer_key
        if item.question_id in by_id
    ]
    missing = [q for q in material.worksheet if q.id not in {a.question_id for a in material.answer_key}]
    for question in missing:
        material.answer_key.append(
            AnswerKeyItem(
                question_id=question.id,
                answer=_model_answer(material.level, topic, question),
                marks=question.marks,
            )
        )


def _model_answer(level: str, topic: str, question: WorksheetQuestion) -> str:
    if level == "support":
        return f"A simple correct sentence about {topic}, one idea only."
    if level == "core":
        return f"A correct, complete answer about {topic} with the key points from the lesson."
    return f"Any well-justified response about {topic}; credit the reasoning, not one fixed wording."


def _objective(topic: str, lang: str) -> str:
    if lang == "Hindi":
        return f"{topic} को समझना और अपने शब्दों में समझाना"
    return f"Explain {topic.lower()} in your own words and apply it to a new example."


def _level_material(level: str, topic: str, objective: str, lang: str) -> dict[str, Any]:
    """Mock content that genuinely differs across the three levels."""
    hi = lang == "Hindi"

    if level == "support":
        return {
            "level": "support",
            "what_changed": (
                "छोटे वाक्य, पूरा हुआ उदाहरण और हर उत्तर के लिए वाक्य-सूचक।"
                if hi
                else "Shorter sentences, one fully worked example, and a sentence starter for every answer."
            ),
            "content": (
                f"{topic} का सरल अर्थ। हम इसे छोटे-छोटे हिस्सों में समझेंगे। "
                "पहले मुख्य बात, फिर उदाहरण।"
                if hi
                else (
                    f"{topic} is easier than it looks. Here is the whole idea in three steps. "
                    f"Step 1: {topic} starts when something changes. Step 2: the change spreads through the whole thing. "
                    f"Step 3: a new result appears. That is all you need for today. "
                    f"Worked example: if we change step 1, then step 2 and step 3 also change - this is a chain, not a list."
                )
            ),
            "key_points": _tr(
                lang,
                [
                    f"{topic} has a starting point.",
                    "Each step causes the next step.",
                    "Change one thing and the result changes.",
                ],
                [
                    f"{topic} का एक शुरुआती बिंदु है।",
                    "हर चरण अगले चरण का कारण है।",
                    "एक बात बदलें तो परिणाम बदल जाता है।",
                ],
            ),
            "scaffolds": _tr(
                lang,
                [
                    f"Start every answer with: 'The first step of {topic} is ...'",
                    "Copy the three steps into your notebook and tick each one.",
                    "Draw a picture of each step. You do not need good drawing.",
                    "Ask your teacher or your partner before moving on.",
                    "There are three words in the word bank. Circle the one that fits.",
                ],
                [
                    f"हर उत्तर इससे शुरू करें: '{topic} का पहला चरण है ...'",
                    "तीनों चरण नोटबुक में लिखें और टिक करें।",
                    "हर चरण का चित्र बनाएँ।",
                    "आगे बढ़ने से पहले शिक्षक या साथी से पूछें।",
                    "शब्द भंडार में से सही शब्द गोल लगाएँ।",
                ],
            ),
        }

    if level == "core":
        return {
            "level": "core",
            "what_changed": (
                "मानक स्तर का स्पष्ट स्पष्टीकरण, चरणों की सूची और पूरा करने योग्य चित्र।"
                if hi
                else "Standard grade-level explanation with a numbered step list and a diagram to complete."
            ),
            "content": (
                f"{topic} की परिभाषा और उसके चरण। यहाँ पूरी प्रक्रिया क्रम से दी गई है। "
                "प्रत्येक चरण को समझने के बाद ही अगला चरण पढ़ें।"
                if hi
                else (
                    f"{topic} is the process by which the change described in this chapter happens. "
                    f"It can be broken into ordered steps, and each step depends on the one before it. "
                    f"Understanding the order matters more than memorising the words. "
                    f"Below is the full sequence; use it as a checklist while you work."
                )
            ),
            "key_points": _tr(
                lang,
                [
                    f"The definition of {topic} has three key terms.",
                    "The order of the steps is fixed and can be tested.",
                    "Variables let you change one condition at a time.",
                    "Evidence comes from observation, not opinion.",
                ],
                [
                    f"{topic} की परिभाषा में तीन मुख्य शब्द हैं।",
                    "चरणों का क्रम निश्चित है और उसकी जाँच की जा सकती है।",
                    "चर की मदद से एक शर्त बदली जा सकती है।",
                    "प्रमाण निरीक्षण से मिलता है, राय से नहीं।",
                ],
            ),
            "scaffolds": _tr(
                lang,
                [
                    "Tick each step in the list as you complete it.",
                    "Complete the half-drawn diagram and label every part.",
                    "Use the key words from class in your answer to score well.",
                    "Compare your answer with a partner before handing it in.",
                ],
                [
                    "पूरा करने पर प्रत्येक चरण को टिक करें।",
                    "आधा बना चित्र पूरा करें और हर भाग नामांकित करें।",
                    "अच्छे अंक के लिए पाठ के मुख्य शब्दों का प्रयोग करें।",
                    "जमा करने से पहले साथी से उत्तर की तुलना करें।",
                ],
            ),
        }

    return {
        "level": "extension",
        "what_changed": (
            "याद करने की जगह खुले प्रश्न, जाँच-डिजाइन और अपने तर्क का बचाव।"
            if hi
            else "Open-ended investigation, evaluation and argument instead of recall."
        ),
        "content": (
            f"{topic} को केवल याद न करें, बल्कि जाँचिए। क्या हमारा सिद्धांत सही है? "
            "यह तय करने के लिए आपको प्रयोग, तर्क और प्रमाण चाहिए।"
            if hi
            else (
                f"Rather than recalling {topic.lower()}, investigate it. Decide which explanation of "
                f"{topic.lower()} is better supported and defend that choice. A strong answer here names "
                f"the variables, controls them fairly, and states what the evidence cannot prove. "
                f"There is more than one defensible answer - the quality of your reasoning is what is assessed."
            )
        ),
        "key_points": _tr(
            lang,
            [
                "Design a fair test: change one variable, hold the rest constant.",
                "Evaluate a claim by asking what evidence would disprove it.",
                "Real-world application: connect the science to a problem in your community.",
                "Model the limits of your own knowledge.",
            ],
            [
                "उचित प्रयोग बनाएँ: एक चर बदलें, बाकी स्थिर रखें।",
                "दावे का मूल्यांकन करें: कौन-सा प्रमाण उसे खंडित करेगा?",
                "वास्तविक अनुप्रयोग: विज्ञान को अपने समुदाय की समस्या से जोड़ें।",
                "अपनी जानकारी की सीमा को स्वीकार करें।",
            ],
        ),
        "scaffolds": _tr(
            lang,
            [
                "Start by writing what a fair test requires.",
                "Strong answers state assumptions and then test them.",
                "If a question has no single right answer, say so and justify your view.",
                "Challenge one idea from the textbook and explain why.",
            ],
            [
                "शुरुआत में लिखें कि उचित प्रयोग में क्या आवश्यक है।",
                "अच्छे उत्तर मान्यताएँ बताते हैं और उन्हें जाँचते हैं।",
                "यदि प्रश्न का एक ही उत्तर नहीं है, तो अपना तर्क दें।",
                "पाठ्यपुस्तक के एक विचार को चुनौती दें और कारण बताएँ।",
            ],
        ),
    }


def _tr(lang: str, en: list[str], hi: list[str]) -> list[str]:
    return hi if lang == "Hindi" else en


agent = DifferentiationAgent()
