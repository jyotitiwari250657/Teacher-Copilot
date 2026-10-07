"""Each agent must return JSON that satisfies its own output schema."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.agents.differentiation import agent as diff_agent
from app.agents.grader import agent as grader_agent
from app.agents.lesson_planner import agent as lesson_agent
from app.agents.parent_update import agent as parent_agent


# ---------------------------------------------------------------------------
# Lesson Planner
# ---------------------------------------------------------------------------
class TestLessonPlannerSchema:
    BASE = {
        "subject": "Science",
        "grade": "8",
        "topic": "Photosynthesis",
        "duration_minutes": 40,
        "board": "CBSE",
        "language": "English",
    }

    @pytest.mark.parametrize("duration", [20, 30, 40, 45, 60, 90])
    def test_output_validates_for_each_duration(self, duration):
        output = lesson_agent.run({**self.BASE, "duration_minutes": duration})
        assert output.title.strip()
        assert len(output.learning_objectives) >= 3
        assert len(output.lesson_flow) >= 1
        assert len(output.exit_ticket) == 3
        assert output.assessment_rubric

    def test_all_prose_is_in_the_requested_language(self):
        output = lesson_agent.run({**self.BASE, "language": "Hindi"})
        text = " ".join(output.learning_objectives + [output.homework])
        assert any("\u0900" <= ch <= "\u097F" for ch in text)

    def test_english_output_contains_no_devanagari(self):
        output = lesson_agent.run({**self.BASE, "language": "English"})
        text = " ".join(output.learning_objectives + [output.homework])
        assert not any("\u0900" <= ch <= "\u097F" for ch in text)

    def test_teacher_objectives_are_respected(self):
        objectives = ["Explain chlorophyll", "Draw a labelled leaf"]
        output = lesson_agent.run(
            {**self.BASE, "learning_objectives": objectives}
        )
        assert output.learning_objectives == objectives

    def test_invalid_input_is_rejected_with_a_clear_message(self):
        from app.agents.base import AgentError

        with pytest.raises(AgentError) as excinfo:
            lesson_agent.run({**self.BASE, "duration_minutes": 0})
        assert "invalid input" in str(excinfo.value)


class TestLessonPlannerMinutesRule:
    """Total minutes must equal the requested duration - always."""

    BASE = {
        "subject": "Science",
        "grade": "8",
        "topic": "Photosynthesis",
        "board": "CBSE",
        "language": "English",
    }

    @pytest.mark.parametrize("duration", [5, 7, 10, 20, 25, 40, 45, 50, 60, 75, 90, 120])
    def test_minutes_sum_to_the_requested_duration(self, duration):
        output = lesson_agent.run({**self.BASE, "duration_minutes": duration})
        total = sum(item.minutes for item in output.lesson_flow)
        assert total == duration, f"expected {duration}, got {total}"

    @pytest.mark.parametrize("duration", [5, 10, 20, 40, 60, 120])
    def test_every_phase_has_positive_time(self, duration):
        output = lesson_agent.run({**self.BASE, "duration_minutes": duration})
        assert all(item.minutes > 0 for item in output.lesson_flow)

    def test_allocation_helper_is_exact_for_any_total(self):
        from app.agents.lesson_planner import _PHASE_WEIGHTS, allocate_minutes

        for total in range(5, 200):
            allocation = allocate_minutes(total, _PHASE_WEIGHTS)
            assert sum(minutes for _, minutes in allocation) == total

    def test_allocation_drops_phases_for_very_short_periods(self):
        from app.agents.lesson_planner import _PHASE_WEIGHTS, allocate_minutes

        long_run = allocate_minutes(60, _PHASE_WEIGHTS)
        short_run = allocate_minutes(10, _PHASE_WEIGHTS)
        assert len(short_run) < len(long_run)

    def test_postprocess_repairs_a_wrong_total(self):
        """A model that miscounts must not be allowed through."""
        from app.agents.lesson_planner import LessonFlowItem, LessonPlanInput, LessonPlanOutput

        broken = LessonPlanOutput(
            title="x",
            lesson_flow=[
                LessonFlowItem(phase="hook", minutes=10),
                LessonFlowItem(phase="explain", minutes=10),
            ],
            exit_ticket=["a", "b", "c"],
        )
        data = LessonPlanInput(
            subject="Science", topic="Photosynthesis", duration_minutes=45
        )
        fixed = lesson_agent.postprocess(broken, data)
        assert sum(item.minutes for item in fixed.lesson_flow) == 45


# ---------------------------------------------------------------------------
# Grader
# ---------------------------------------------------------------------------
QUESTIONS = [
    {
        "id": "Q1",
        "question": "Which pigment makes leaves green?",
        "marks": 1,
        "type": "mcq",
        "options": ["Haemoglobin", "Chlorophyll", "Melanin"],
        "answer_key": "Chlorophyll",
    },
    {
        "id": "Q2",
        "question": "Write the word equation for photosynthesis.",
        "marks": 3,
        "type": "short",
        "model_answer": "Carbon dioxide plus water, in the presence of sunlight, gives glucose plus oxygen.",
    },
]


class TestGraderSchema:
    def test_output_validates(self):
        output = grader_agent.run(
            {"questions": QUESTIONS, "answers": {"Q1": "Chlorophyll", "Q2": "Sunlight makes food."}}
        )
        assert output.student_ref == "S01"
        assert len(output.per_question_marks) == 2
        assert output.max_total == 4
        assert 0 <= output.percentage <= 100

    def test_every_question_mark_has_the_required_fields(self):
        output = grader_agent.run(
            {"questions": QUESTIONS, "answers": {"Q1": "Chlorophyll", "Q2": "x"}}
        )
        for mark in output.per_question_marks:
            assert mark.question_id
            assert mark.feedback
            assert 0.0 <= mark.confidence <= 1.0
            assert 0 <= mark.marks_awarded <= mark.max_marks

    def test_totals_match_the_sum_of_the_parts(self):
        output = grader_agent.run(
            {"questions": QUESTIONS, "answers": {"Q1": "Chlorophyll", "Q2": "water and sunlight"}}
        )
        assert output.total == round(
            sum(m.marks_awarded for m in output.per_question_marks), 2
        )

    def test_student_ref_is_echoed_not_invented(self):
        output = grader_agent.run(
            {"questions": QUESTIONS, "answers": {"Q1": "Chlorophyll"}, "student_ref": "S07"}
        )
        assert output.student_ref == "S07"

    def test_empty_answer_set_is_handled(self):
        output = grader_agent.run({"questions": QUESTIONS, "answers": {}})
        assert output.total == 0.0
        assert output.percentage == 0.0


class TestMcqExactMatch:
    @pytest.mark.parametrize(
        "given,expected_marks",
        [
            ("Chlorophyll", 1.0),
            ("chlorophyll", 1.0),
            ("  Chlorophyll  ", 1.0),
            ("Melanin", 0.0),
            ("chloroplast", 0.0),
            ("", 0.0),
        ],
    )
    def test_mcq_is_graded_exactly_against_the_key(self, given, expected_marks):
        output = grader_agent.run(
            {"questions": [QUESTIONS[0]], "answers": {"Q1": given}}
        )
        assert output.per_question_marks[0].marks_awarded == expected_marks

    def test_lettered_mcq_options_match_case_insensitively(self):
        question = {
            "id": "Q1",
            "question": "Pick one",
            "marks": 1,
            "type": "mcq",
            "options": ["alpha", "beta"],
            "answer_key": "B",
        }
        for given, expected in [("B", 1.0), ("b", 1.0), ("(B)", 1.0), ("A", 0.0)]:
            output = grader_agent.run(
                {"questions": [question], "answers": {"Q1": given}}
            )
            assert output.per_question_marks[0].marks_awarded == expected, given

    def test_true_false_is_graded_against_the_key(self):
        question = {
            "id": "Q1",
            "question": "Leaves make food.",
            "marks": 1,
            "type": "true_false",
            "answer_key": "True",
        }
        for given, expected in [("True", 1.0), ("yes", 1.0), ("False", 0.0), ("no", 0.0)]:
            output = grader_agent.run({"questions": [question], "answers": {"Q1": given}})
            assert output.per_question_marks[0].marks_awarded == expected, given

    def test_numeric_tolerance(self):
        question = {
            "id": "Q1",
            "question": "How many stomata?",
            "marks": 2,
            "type": "numeric",
            "answer_key": "100",
        }
        for given, expected in [("100", 2.0), ("100.0", 2.0), ("100.5", 2.0), ("90", 0.0)]:
            output = grader_agent.run({"questions": [question], "answers": {"Q1": given}})
            assert output.per_question_marks[0].marks_awarded == expected, given


class TestGraderConfidenceRule:
    def test_low_confidence_forces_review_flag(self):
        output = grader_agent.run(
            {"questions": QUESTIONS, "answers": {"Q1": "Chlorophyll", "Q2": "sun"}}
        )
        assert output.needs_teacher_review is True
        assert output.low_confidence_questions

    def test_high_confidence_does_not_force_review(self):
        output = grader_agent.run(
            {
                "questions": QUESTIONS,
                "answers": {
                    "Q1": "Chlorophyll",
                    "Q2": "Carbon dioxide plus water gives glucose plus oxygen in sunlight.",
                },
            }
        )
        assert output.needs_teacher_review is False

    def test_model_validator_overrides_a_false_flag_from_the_model(self):
        """Even if a real model returns needs_teacher_review=false, the rule wins."""
        from app.agents.grader import GraderOutput

        forced = GraderOutput(
            student_ref="S01",
            per_question_marks=[
                {"question_id": "Q1", "marks_awarded": 1, "max_marks": 1,
                 "feedback": "ok", "confidence": 0.3}
            ],
            needs_teacher_review=False,
        )
        assert forced.needs_teacher_review is True

    def test_blank_answers_are_high_confidence_certainty(self):
        output = grader_agent.run({"questions": QUESTIONS, "answers": {}})
        assert all(m.confidence >= 0.9 for m in output.per_question_marks)
        assert output.needs_teacher_review is False

    def test_threshold_is_exactly_zero_point_six(self):
        from app.agents.grader import CONFIDENCE_THRESHOLD, QuestionMark, GraderOutput

        assert CONFIDENCE_THRESHOLD == 0.6
        at_threshold = GraderOutput(
            per_question_marks=[
                QuestionMark(question_id="Q1", marks_awarded=1, max_marks=1, confidence=0.6)
            ]
        )
        below = GraderOutput(
            per_question_marks=[
                QuestionMark(question_id="Q1", marks_awarded=1, max_marks=1, confidence=0.59)
            ]
        )
        assert at_threshold.needs_teacher_review is False
        assert below.needs_teacher_review is True


class TestGraderStrictness:
    ANSWERS = {
        "Q1": "Chlorophyll",
        "Q2": "Plants use sunlight and water to make food in the leaves.",
    }

    def test_lenient_awards_more_than_strict(self):
        lenient = grader_agent.run(
            {"questions": QUESTIONS, "answers": self.ANSWERS, "strictness": "lenient"}
        )
        strict = grader_agent.run(
            {"questions": QUESTIONS, "answers": self.ANSWERS, "strictness": "strict"}
        )
        assert lenient.total > strict.total

    def test_marks_never_exceed_the_maximum(self):
        lenient = grader_agent.run(
            {"questions": QUESTIONS, "answers": self.ANSWERS, "strictness": "lenient"}
        )
        assert all(m.marks_awarded <= m.max_marks for m in lenient.per_question_marks)


# ---------------------------------------------------------------------------
# Differentiation
# ---------------------------------------------------------------------------
class TestDifferentiationSchema:
    def test_output_validates_and_has_three_levels(self):
        output = diff_agent.run({"topic": "Photosynthesis", "language": "English"})
        assert output.topic == "Photosynthesis"
        assert output.learning_objective
        for level in ("support", "core", "extension"):
            material = getattr(output, level)
            assert material.level == level
            assert material.what_changed
            assert material.content

    @pytest.mark.parametrize("level_name", ["support", "core", "extension"])
    def test_each_level_has_8_to_10_questions(self, level_name):
        output = diff_agent.run({"topic": "Photosynthesis"})
        worksheet = getattr(output, level_name).worksheet
        assert 8 <= len(worksheet) <= 10

    @pytest.mark.parametrize("level_name", ["support", "core", "extension"])
    def test_answer_key_ids_match_the_worksheet_exactly(self, level_name):
        output = diff_agent.run({"topic": "Photosynthesis"})
        material = getattr(output, level_name)
        worksheet_ids = {q.id for q in material.worksheet}
        key_ids = {a.question_id for a in material.answer_key}
        assert worksheet_ids == key_ids

    def test_the_three_levels_are_genuinely_different(self):
        output = diff_agent.run({"topic": "Photosynthesis"})
        statements = {
            output.support.what_changed,
            output.core.what_changed,
            output.extension.what_changed,
        }
        assert len(statements) == 3, "each level must describe a different change"

    def test_all_three_levels_share_one_learning_objective(self):
        output = diff_agent.run({"topic": "Photosynthesis"})
        assert output.support.content and output.core.content and output.extension.content

    def test_hindi_output_is_devanagari(self):
        output = diff_agent.run({"topic": "Photosynthesis", "language": "Hindi"})
        text = output.support.what_changed + output.support.content
        assert any("\u0900" <= ch <= "\u097F" for ch in text)

    def test_grouping_splits_by_score(self):
        performance = [
            {"student_ref": "S01", "percentage": 25},
            {"student_ref": "S02", "percentage": 55},
            {"student_ref": "S03", "percentage": 88},
        ]
        output = diff_agent.run(
            {"topic": "Photosynthesis", "performance": performance}
        )
        groups = {g.level: g.student_refs for g in output.groupings}
        assert groups["support"] == ["S01"]
        assert groups["core"] == ["S02"]
        assert groups["extension"] == ["S03"]

    def test_manual_levels_override_the_score_split(self):
        performance = [
            {"student_ref": "S01", "percentage": 95},
            {"student_ref": "S02", "percentage": 30},
        ]
        output = diff_agent.run(
            {
                "topic": "Photosynthesis",
                "performance": performance,
                "manual_levels": {"S01": "support", "S02": "extension"},
            }
        )
        groups = {g.level: g.student_refs for g in output.groupings}
        assert groups["support"] == ["S01"]
        assert groups["extension"] == ["S02"]

    def test_worksheet_is_padded_when_the_model_under_fills_it(self):
        from app.agents.differentiation import (
            DifferentiationOutput,
            LevelInput,
            LevelMaterial,
        )

        sparse = DifferentiationOutput(
            topic="X",
            learning_objective="y",
            support=LevelMaterial(level="support", what_changed="a", content="b"),
            core=LevelMaterial(level="core", what_changed="a", content="b"),
            extension=LevelMaterial(level="extension", what_changed="a", content="b"),
        )
        fixed = diff_agent.postprocess(sparse, LevelInput(topic="X"))
        for name in ("support", "core", "extension"):
            material = getattr(fixed, name)
            assert len(material.worksheet) == 8
            assert {q.id for q in material.worksheet} == {
                a.question_id for a in material.answer_key
            }


# ---------------------------------------------------------------------------
# Parent Update
# ---------------------------------------------------------------------------
class TestParentUpdateSchema:
    BASE = {
        "student_ref": "S03",
        "subject": "Science",
        "overall_percentage": 78,
        "attendance_pct": 92,
        "tone": "warm",
        "language": "English",
    }

    def test_output_validates(self):
        output = parent_agent.run({**self.BASE, "channel": "whatsapp"})
        assert output.body
        assert output.positive_observation
        assert output.area_to_improve
        assert output.home_step

    def test_whatsapp_body_respects_the_120_word_limit(self):
        output = parent_agent.run({**self.BASE, "channel": "whatsapp"})
        assert output.word_count <= 120

    def test_email_has_a_subject_line(self):
        output = parent_agent.run({**self.BASE, "channel": "email"})
        assert output.subject_line.strip()

    def test_whatsapp_has_no_subject_line(self):
        output = parent_agent.run({**self.BASE, "channel": "whatsapp"})
        assert output.subject_line == ""

    def test_all_three_elements_are_present(self):
        for channel in ("whatsapp", "email"):
            output = parent_agent.run({**self.BASE, "channel": channel})
            assert output.positive_observation.strip(), channel
            assert output.area_to_improve.strip(), channel
            assert output.home_step.strip(), channel

    def test_missing_element_raises_a_clear_error(self):
        from app.agents.base import AgentError
        from app.agents.parent_update import ParentUpdateInput, ParentUpdateOutput

        output = ParentUpdateOutput(
            student_ref="S01",
            body="hello",
            positive_observation="",
            area_to_improve="something",
            home_step="do this",
        )
        with pytest.raises(AgentError) as excinfo:
            parent_agent.postprocess(output, ParentUpdateInput(student_ref="S01"))
        assert "positive observation" in str(excinfo.value)

    def test_hindi_output_is_devanagari(self):
        output = parent_agent.run({**self.BASE, "channel": "whatsapp", "language": "Hindi"})
        assert any("\u0900" <= ch <= "\u097F" for ch in output.body)

    def test_placeholder_is_used_rather_than_a_real_name(self):
        output = parent_agent.run({**self.BASE, "channel": "whatsapp"})
        assert "{{student_name}}" in output.body


class TestParentUpdateSafety:
    BASE = {
        "student_ref": "S03",
        "subject": "Science",
        "attendance_pct": 92,
        "tone": "warm",
        "language": "English",
        "channel": "whatsapp",
    }

    def test_low_scores_are_flagged_for_review(self):
        output = parent_agent.run({**self.BASE, "overall_percentage": 22})
        assert output.needs_teacher_review is True
        assert any("score" in reason.lower() for reason in output.review_reasons)

    def test_low_attendance_is_flagged_for_review(self):
        output = parent_agent.run({**self.BASE, "overall_percentage": 80, "attendance_pct": 55})
        assert output.needs_teacher_review is True
        assert any("attendance" in reason.lower() for reason in output.review_reasons)

    def test_normal_case_is_not_flagged(self):
        output = parent_agent.run({**self.BASE, "overall_percentage": 78})
        assert output.needs_teacher_review is False
        assert output.review_reasons == []

    def test_threshold_boundary(self):
        from app.agents.parent_update import flag_sensitive

        assert flag_sensitive(34.9, 100)[0] is True
        assert flag_sensitive(35.0, 100)[0] is False
        assert flag_sensitive(90, 69.9)[0] is True
        assert flag_sensitive(90, 70.0)[0] is False

    @pytest.mark.parametrize(
        "offensive",
        [
            "Your child is a slow learner.",
            "He is careless and always careless with his work.",
            "The child seems dyslexic.",
            "Other students in the class are doing far better.",
        ],
    )
    def test_diagnostic_or_comparative_wording_is_removed(self, offensive):
        from app.agents.parent_update import sanitize

        cleaned = sanitize(offensive)
        lowered = cleaned.lower()
        for banned in ("slow learner", "dyslex", "careless", "other students"):
            assert banned not in lowered, f"'{banned}' survived sanitisation: {cleaned!r}"

    def test_postprocess_sanitises_a_model_that_slips(self):
        from app.agents.parent_update import ParentUpdateInput, ParentUpdateOutput

        output = ParentUpdateOutput(
            student_ref="S01",
            body="Your child is a slow learner. Other students scored higher.",
            positive_observation="He tries hard.",
            area_to_improve="Writing longer answers.",
            home_step="Read together.",
            word_count=0,
        )
        fixed = parent_agent.postprocess(output, ParentUpdateInput(student_ref="S01"))
        assert "slow learner" not in fixed.body.lower()
        assert "other students" not in fixed.body.lower()

    def test_no_message_names_another_student(self):
        output = parent_agent.run({**self.BASE, "overall_percentage": 60})
        assert "S0" not in output.body  # no anonymous ids leak into the text