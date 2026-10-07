"""Lesson Planner Agent.

Turns (subject, grade, topic, duration, board, language) into a classroom-ready
lesson plan whose phase durations sum *exactly* to the requested time.
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from .base import AgentError, BaseAgent

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
Phase = Literal["hook", "explain", "activity", "practice", "assessment", "recap"]


class LessonPlanInput(BaseModel):
    subject: str
    grade: str = ""
    topic: str
    duration_minutes: int = Field(default=40, ge=5, le=300)
    board: Literal["CBSE", "ICSE", "State", "Other"] = "CBSE"
    language: Literal["English", "Hindi"] = "English"
    learning_objectives: list[str] = Field(default_factory=list)
    class_level_notes: str = ""


class LessonFlowItem(BaseModel):
    phase: Phase
    minutes: int = Field(ge=0)
    teacher_actions: list[str] = Field(default_factory=list)
    student_actions: list[str] = Field(default_factory=list)


class RubricRow(BaseModel):
    criterion: str
    description: str = ""
    marks: float = 0


class LessonPlanOutput(BaseModel):
    title: str
    learning_objectives: list[str] = Field(default_factory=list)
    prior_knowledge: list[str] = Field(default_factory=list)
    materials: list[str] = Field(default_factory=list)
    lesson_flow: list[LessonFlowItem] = Field(default_factory=list)
    key_vocabulary: list[str] = Field(default_factory=list)
    common_misconceptions: list[str] = Field(default_factory=list)
    homework: str = ""
    exit_ticket: list[str] = Field(default_factory=list)
    assessment_rubric: list[RubricRow] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Time allocation
# ---------------------------------------------------------------------------
# Relative share of the period each phase deserves, best first to drop.
_PHASE_WEIGHTS: list[tuple[str, float]] = [
    ("hook", 0.12),
    ("explain", 0.25),
    ("activity", 0.25),
    ("practice", 0.18),
    ("assessment", 0.12),
    ("recap", 0.08),
]
_MIN_PHASE_MINUTES = 3


def allocate_minutes(total: int, weights: list[tuple[str, float]]) -> list[tuple[str, int]]:
    """Split ``total`` minutes across phases, summing to exactly ``total``.

    Uses the largest-remainder method so the integers always add up, and drops
    the lowest-weight phases first when the period is too short for all six.
    """
    phases = list(weights)
    while phases and len(phases) * _MIN_PHASE_MINUTES > total:
        # Drop the smallest-weight phase and renormalise the rest.
        smallest = min(range(len(phases)), key=lambda i: phases[i][1])
        phases = [(p, w) for i, (p, w) in enumerate(phases) if i != smallest]
        weight_sum = sum(w for _, w in phases) or 1.0
        phases = [(p, w / weight_sum) for p, w in phases]

    if not phases:  # pathological: a 1-2 minute period
        return [("explain", max(1, total))]

    weight_sum = sum(w for _, w in phases)
    exact = [(p, (w / weight_sum) * total) for p, w in phases]
    floored = [(p, int(v)) for p, v in exact]
    remainder = total - sum(v for _, v in floored)

    # Hand out the leftover minutes to the largest fractional parts.
    order = sorted(
        range(len(exact)),
        key=lambda i: exact[i][1] - floored[i][1],
        reverse=True,
    )
    floored = [list(item) for item in floored]
    for i in range(remainder):
        floored[order[i % len(order)]][1] += 1

    return [(p, max(1, int(v))) for p, v in floored]


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """\
You are the Lesson Planner for TeacherCopilot, an assistant used by school
teachers in India. You write lesson plans that a busy teacher can pick up and
teach from without rewriting them.

## What you produce
A single JSON object describing one lesson. The exact shape is:

{
  "title": string,
  "learning_objectives": [string],          // 3-5 measurable objectives, "By the end of this lesson students will be able to ..."
  "prior_knowledge": [string],              // 2-4 things students are assumed to already know
  "materials": [string],                    // cheap, physical, low-resource items
  "lesson_flow": [                            // ordered phases, minutes MUST sum to the requested duration
    {
      "phase": "hook" | "explain" | "activity" | "practice" | "assessment" | "recap",
      "minutes": integer,
      "teacher_actions": [string],
      "student_actions": [string]
    }
  ],
  "key_vocabulary": [string],               // 5-8 terms with short meanings
  "common_misconceptions": [string],        // 2-4 likely wrong ideas + how to correct them
  "homework": string,                       // a task doable at home without internet
  "exit_ticket": [string],                  // EXACTLY 3 short questions
  "assessment_rubric": [                     // 3-4 rows
    { "criterion": string, "description": string, "marks": number }
  ]
}

## Hard rules
1. Reply with ONLY the JSON object. No markdown fences, no commentary, no
   text before or after it.
2. The `minutes` of every lesson_flow item MUST add up EXACTLY to the requested
   duration. This is checked automatically; a wrong total is a failed lesson.
3. Use realistic phases in this order: hook, explain, activity, practice,
   assessment, recap. For periods of 20 minutes or less, use fewer phases.
4. The classroom is LOW RESOURCE. Never assume a projector, a working
   internet connection, a laptop per student, or a lab with equipment. Prefer
   chalkboard work, charts, cardboard models, plants, stones, and worksheets.
5. `teacher_actions` are things a teacher says or does. `student_actions` are
   what students do. Keep each to 1-3 short imperative strings.
6. `exit_ticket` has exactly 3 items.
7. All prose must be in the requested output language (English or Hindi). If
   Hindi is requested, write natural Devanagari Hindi that a student would
   understand, and keep scientific terms in English in brackets on first use.

## Few-shot example
Input: subject=Science, grade=8, topic="States of Matter", duration_minutes=40,
language=English.
Output:
{
  "title": "States of Matter: Why Ice Melts but Water Does Not Evaporate",
  "learning_objectives": [
    "By the end of this lesson students will be able to name the three states of matter and give one example of each",
    "Students will be able to explain that heating or cooling changes particle movement",
    "Students will be able to classify an unfamiliar substance into solid, liquid or gas"
  ],
  "prior_knowledge": [
    "Students know that matter occupies space and has weight",
    "Students have seen water in all three states"
  ],
  "materials": [
    "Ice cubes in a steel bowl",
    "A beaker and a candle (supervised)",
    "Chart of particle arrangement",
    "Chalkboard"
  ],
  "lesson_flow": [
    { "phase": "hook", "minutes": 5, "teacher_actions": ["Hold up an ice cube and ask what students feel", "Record two guesses on the board"], "student_actions": ["Touch the ice cube", "Call out guesses"] },
    { "phase": "explain", "minutes": 10, "teacher_actions": ["Draw the three particle diagrams", "Move a marker slowly and quickly to show motion"], "student_actions": ["Copy the three diagrams", "Answer: which state moves fastest?"] },
    { "phase": "activity", "minutes": 10, "teacher_actions": ["Hand out three sealed containers with chalk, water and air", "Ask groups to shake and observe"], "student_actions": ["Work in groups of four", "Record observations in the worksheet"] },
    { "phase": "practice", "minutes": 8, "teacher_actions": ["Give six substances to classify aloud"], "student_actions": ["Write solid, liquid or gas for each"] },
    { "phase": "assessment", "minutes": 4, "teacher_actions": ["Collect the exit tickets"], "student_actions": ["Answer the three exit ticket questions"] },
    { "phase": "recap", "minutes": 3, "teacher_actions": ["Ask students to say one thing they will remember", "Preview the next lesson"], "student_actions": ["State one idea in their own words"] }
  ],
  "key_vocabulary": [
    "Matter - anything that has weight and takes up space",
    "Particle - the very small unit that makes up a substance",
    "Melting - solid changing to liquid on heating",
    "Evaporation - liquid changing to gas"
  ],
  "common_misconceptions": [
    "Students think ice melts because it 'gets lighter' - show that mass is unchanged using a balance",
    "Students think gases have no mass - weigh an empty balloon, then the same balloon filled with air"
  ],
  "homework": "Find three things at home that change state and write one line on what caused it.",
  "exit_ticket": [
    "Name the three states of matter and give one example of each.",
    "What happens to particle movement when a solid is heated?",
    "A bucket of water is left in the sun. Which state change happens, and why?"
  ],
  "assessment_rubric": [
    { "criterion": "Names the states", "description": "Lists all three states correctly with an example", "marks": 2 },
    { "criterion": "Explains particle movement", "description": "Links heating to faster or slower particle motion", "marks": 2 },
    { "criterion": "Applies to a new case", "description": "Classifies an unfamiliar substance correctly", "marks": 1 }
  ]
}
"""

# ---------------------------------------------------------------------------
# Mock response builder
# ---------------------------------------------------------------------------
_HINDI_TOPIC_HINT = {
    "photosynthesis": "प्रकाश संश्लेषण",
    "respiration": "श्वसन",
}


def _t(topic: str, language: str) -> str:
    """Display name for the topic, transliterated when Hindi is requested."""
    if language == "Hindi":
        return _HINDI_TOPIC_HINT.get(topic.strip().lower(), topic)
    return topic


def _tr(lang: str, en: list[str], hi: list[str]) -> list[str]:
    return hi if lang == "Hindi" else en


class LessonPlannerAgent(BaseAgent[LessonPlanInput, LessonPlanOutput]):
    name = "lesson_planner"
    system_prompt = SYSTEM_PROMPT
    input_model = LessonPlanInput
    output_model = LessonPlanOutput
    temperature = 0.7
    max_tokens = 4000
    description = "Builds classroom-ready lesson plans with exact time budgeting."

    def build_mock(self, payload: dict[str, Any]) -> dict[str, Any]:
        subject = payload.get("subject", "General")
        grade = payload.get("grade", "")
        topic = payload.get("topic", "the topic")
        duration = int(payload.get("duration_minutes", 40) or 40)
        board = payload.get("board", "CBSE")
        lang = payload.get("language", "English")
        notes = payload.get("class_level_notes", "") or ""
        given_objectives = payload.get("learning_objectives") or []

        title_topic = _t(topic, lang)
        if lang == "Hindi":
            title = f"{title_topic} - {subject} पाठ ({grade or ''} कक्षा)".strip(" -")
        else:
            title = f"{topic} - {subject} Lesson ({grade} class)".replace("  ", " ").strip()

        objectives = list(given_objectives)[:5]
        if not objectives:
            objectives = _tr(
                lang,
                [
                    f"Define {topic.lower()} in the student's own words",
                    f"Explain one real-life example of {topic.lower()}",
                    f"Apply {topic.lower()} to a new situation and justify the answer",
                ],
                [
                    f"इस पाठ के अंत तक विद्यार्थी {topic} को अपने शब्दों में समझा पाएंगे",
                    f"विद्यार्थी {topic} का एक वास्तविक जीवन का उदाहरण समझा पाएंगे",
                    f"विद्यार्थी {topic} को नई परिस्थिति में लागू कर सकेंगे",
                ],
            )

        allocation = allocate_minutes(duration, _PHASE_WEIGHTS)
        flow = []
        for phase, minutes in allocation:
            flow.append(
                {
                    "phase": phase,
                    "minutes": minutes,
                    "teacher_actions": _phase_teacher_actions(phase, topic, subject, lang, notes),
                    "student_actions": _phase_student_actions(phase, topic, lang),
                }
            )

        return {
            "title": title,
            "learning_objectives": objectives,
            "prior_knowledge": _tr(
                lang,
                [
                    f"Students can read a short paragraph about {subject.lower()}.",
                    "Students have seen or touched a related example in daily life.",
                    "Students can write a full sentence independently.",
                ],
                [
                    f"विद्यार्थी {subject} के बारे में एक छोटा अनुच्छेद पढ़ सकते हैं।",
                    "विद्यार्थियों ने दैनिक जीवन से जुड़ा उदाहरण देखा है।",
                    "विद्यार्थी स्वतंत्र रूप से पूर्ण वाक्य लिख सकते हैं।",
                ],
            ),
            "materials": _tr(
                lang,
                [
                    "Chalkboard and chalk",
                    "Handout / worksheet printed on paper",
                    "Chart or picture of the topic",
                    "Everyday objects related to the topic (leaves, stones, containers)",
                    "Two coloured markers for pair work",
                ],
                [
                    "चॉकबोर्ड और चॉक",
                    "कागज़ पर छपा हुआ वर्कशीट",
                    f"{topic} का चित्र या चार्ट",
                    "विषय से जुड़ी सामान्य वस्तुएँ",
                    "जोड़ी कार्य के लिए दो रंगीन मार्कर",
                ],
            ),
            "lesson_flow": flow,
            "key_vocabulary": _tr(
                lang,
                [
                    f"{topic} - the central idea of this lesson",
                    "Evidence - an observation that supports an idea",
                    "Variable - a factor that can be changed",
                    "Conclusion - what we decide after the activity",
                    "Application - using an idea in a new situation",
                ],
                [
                    f"{topic} - इस पाठ का मुख्य विचार",
                    "प्रमाण - किसी विचार का समर्थन करने वाला निरीक्षण",
                    "चर - वह कारक जिसे बदला जा सकता है",
                    "निष्कर्ष - कार्य के बाद हमारा निर्णय",
                    "अनुप्रयोग - नई परिस्थिति में विचार का प्रयोग",
                ],
            ),
            "common_misconceptions": _tr(
                lang,
                [
                    f"Students repeat the definition without applying it - always ask for an example from their own life.",
                    f"Students confuse {topic} with a related idea - contrast the two explicitly on the board.",
                    "Students copy the board instead of thinking - ask for one original example from each pair.",
                ],
                [
                    "विद्यार्थी परिभाषा दोहराते हैं पर उसका प्रयोग नहीं करते - उदाहरण अवश्य पूछें।",
                    f"विद्यार्थी {topic} को संबंधित विचार से भ्रमित करते हैं - दोनों का अंतर स्पष्ट करें।",
                    "विद्यार्थी बोर्ड कॉपी करते हैं - प्रत्येक जोड़ी से नया उदाहरण पूछें।",
                ],
            ),
            "homework": " ".join(
                _tr(
                    lang,
                    [
                        f"Write five sentences about {topic.lower()} using the five key words from class.",
                        "Underline each key word you used.",
                        "Ask an adult at home one question about the topic and note their answer.",
                    ],
                    [
                        f"पाठ में सिखाए गए पाँच शब्दों का प्रयोग करते हुए {topic} पर पाँच वाक्य लिखें।",
                        "आपके द्वारा प्रयोग किए गए शब्दों को रेखांकित करें।",
                        "घर पर किसी बड़े से इस विषय पर एक प्रश्न पूछकर उत्तर लिखें।",
                    ],
                )
            ),
            "exit_ticket": _tr(
                lang,
                [
                    f"State the main idea of today's lesson about {topic.lower()} in one sentence.",
                    f"Give one example of {topic.lower()} from your own life.",
                    f"What is one question you still have about {topic.lower()}?",
                ],
                [
                    f"आज के पाठ का मुख्य विचार एक वाक्य में लिखिए।",
                    f"अपने जीवन से {topic} का एक उदाहरण दीजिए।",
                    f"{topic} के बारे में आपका एक प्रश्न क्या है?",
                ],
            ),
            "assessment_rubric": [
                {"criterion": "Concept understanding", "description": f"Explains {topic} correctly in own words", "marks": 3},
                {"criterion": "Example quality", "description": "Gives a relevant real-life example", "marks": 2},
                {"criterion": "Application", "description": f"Uses {topic} in a new situation", "marks": 3},
                {"criterion": "Participation and notebook work", "description": "Contributes in class and writes clearly", "marks": 2},
            ],
        }

    # ---- hard rule enforcement -----------------------------------------
    def postprocess(self, output: LessonPlanOutput, data: LessonPlanInput) -> LessonPlanOutput:
        """Guarantee the minutes-sum rule and the 3-item exit ticket."""
        if not output.lesson_flow:
            raise AgentError(
                "The lesson planner returned an empty lesson_flow.",
                agent=self.name,
            )

        total = sum(item.minutes for item in output.lesson_flow)
        if total != data.duration_minutes:
            output.lesson_flow = _rebalance(output.lesson_flow, data.duration_minutes)
            new_total = sum(item.minutes for item in output.lesson_flow)
            if new_total != data.duration_minutes:
                raise AgentError(
                    f"Could not balance the lesson to exactly {data.duration_minutes} minutes "
                    f"(got {new_total}). Please regenerate.",
                    agent=self.name,
                )

        if len(output.exit_ticket) != 3:
            fixed = list(output.exit_ticket)[:3]
            while len(fixed) < 3:
                fixed.append(
                    f"Write one thing you learned about {data.topic} today."
                )
            output.exit_ticket = fixed

        if not output.title.strip():
            output.title = f"{data.topic} - {data.subject}"

        return output


def _rebalance(flow: list[LessonFlowItem], target: int) -> list[LessonFlowItem]:
    """Rescale a flow so the phase minutes add up to ``target``.

    The first phase absorbs (or gives up) any rounding slack so the total is
    exact without changing the relative shape of the lesson.
    """
    if not flow or target <= 0:
        return flow

    current = sum(item.minutes for item in flow)
    if current <= 0:
        per = max(1, target // len(flow))
        for item in flow:
            item.minutes = per
        flow[0].minutes += target - per * len(flow)
        return flow

    scaled: list[int] = []
    running = 0
    for index, item in enumerate(flow):
        if index == len(flow) - 1:
            scaled.append(max(0, target - running))
        else:
            value = int(round(item.minutes * target / current))
            value = max(0, value)
            scaled.append(value)
            running += value
    for item, value in zip(flow, scaled):
        item.minutes = value
    return flow


def _phase_teacher_actions(
    phase: str, topic: str, subject: str, lang: str, notes: str
) -> list[str]:
    adaptation = (
        [f"Adapt pace for this class: {notes[:160]}"] if notes and lang == "English" else []
    )
    actions = {
        "hook": _tr(
            lang,
            [
                f"Start with a question: 'What do you already know about {topic.lower()}?'",
                "Write student guesses on the board without correcting them yet.",
            ],
            [
                f"शुरुआत प्रश्न से करें: '{topic} के बारे में आप क्या जानते हैं?'",
                "विद्यार्थियों के उत्तर बोर्ड पर लिखें, अभी सुधार न करें।",
            ],
        ),
        "explain": _tr(
            lang,
            [
                f"Introduce {topic.lower()} in simple steps using the chalkboard.",
                "Draw a labelled diagram and explain each part aloud.",
                "Check understanding with two quick questions.",
            ],
            [
                f"{topic} को सरल चरणों में समझाएँ।",
                "नामांकित चित्र बनाएँ और हर भाग समझाएँ।",
                "दो त्वरित प्रश्नों से समझ जाँचें।",
            ],
        ),
        "activity": _tr(
            lang,
            [
                f"Give each group of four the {topic.lower()} activity sheet.",
                "Demonstrate the first step, then let groups work for most of the time.",
                "Walk between groups and ask 'why do you think that?'",
            ],
            [
                f"हर समूह को {topic} गतिविधि पत्रक दें।",
                "पहला चरण प्रदर्शित करें, फिर समूह कार्य करें।",
                "समूहों के बीच घूमें और 'तुमने ऐसा क्यों सोचा?' पूछें।",
            ],
        ),
        "practice": _tr(
            lang,
            [
                f"Work through three guided questions on {topic.lower()} together.",
                "Let students try the last question in pairs before whole-class correction.",
                "Correct gently and praise correct reasoning, not just correct answers.",
            ],
            [
                f"{topic} पर तीन निर्देशित प्रश्न एक साथ हल करें।",
                "अंतिम प्रश्न विद्यार्थी जोड़ों में हल करें।",
                "धीरे से सुधारें और सही तर्क की प्रशंसा करें।",
            ],
        ),
        "assessment": _tr(
            lang,
            [
                f"Ask the three exit-ticket questions about {topic.lower()}.",
                "Collect the tickets and scan for misconceptions before students leave.",
            ],
            [
                f"{topic} पर तीन निकास-टिकट प्रश्न पूछें।",
                "टिकट एकत्र करें और अवधारणाओं की जाँच करें।",
            ],
        ),
        "recap": _tr(
            lang,
            [
                f"Ask students to summarise {topic.lower()} in one sentence each.",
                "Preview the next lesson and set the homework.",
            ],
            [
                f"विद्यार्थियों से {topic} का एक वाक्य में सार लिखवाएँ।",
                "अगले पाठ का परिचय दें और गृहकार्य दें।",
            ],
        ),
    }
    return list(actions.get(phase, [])) + adaptation


def _phase_student_actions(phase: str, topic: str, lang: str) -> list[str]:
    actions = {
        "hook": _tr(
            lang,
            ["Call out an answer", "Write one guess in the notebook"],
            ["उत्तर बोलें", "नोटबुक में एक अनुमान लिखें"],
        ),
        "explain": _tr(
            lang,
            ["Listen and copy the labelled diagram", "Answer two checking questions"],
            ["नामांकित चित्र कॉपी करें", "दो जाँच प्रश्नों के उत्तर दें"],
        ),
        "activity": _tr(
            lang,
            ["Work in a group of four", "Write observations on the activity sheet"],
            ["चार विद्यार्थियों के समूह में कार्य करें", "गतिविधि पत्रक पर निरीक्षण लिखें"],
        ),
        "practice": _tr(
            lang,
            ["Attempt the questions in the notebook", "Compare answers with a partner"],
            ["नोटबुक में प्रश्न हल करें", "साथी से उत्तर की तुलना करें"],
        ),
        "assessment": _tr(
            lang,
            ["Write the three exit-ticket answers", "Hand the ticket to the teacher"],
            ["तीन निकास-टिकट उत्तर लिखें", "टिकट शिक्षक को दें"],
        ),
        "recap": _tr(
            lang,
            ["Write one sentence summarising the lesson", "Note the homework"],
            ["पाठ का एक वाक्य सार लिखें", "गृहकार्य लिखें"],
        ),
    }
    return list(actions.get(phase, []))


agent = LessonPlannerAgent()
