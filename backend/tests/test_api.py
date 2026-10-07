"""API-level tests: the approval gate, overrides, exports and the orchestrator."""
from __future__ import annotations

import io

import pytest


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
class TestAuth:
    def test_demo_login_succeeds(self, client):
        assert client.headers.get("Authorization", "").startswith("Bearer ")

    def test_wrong_password_is_rejected(self, anon_client):
        response = anon_client.post(
            "/auth/login",
            json={"email": "demo@teachercopilot.app", "password": "wrong"},
        )
        assert response.status_code == 401

    def test_protected_routes_require_a_token(self, anon_client):
        assert anon_client.get("/classes").status_code == 401
        assert anon_client.get("/dashboard/summary").status_code == 401

    def test_garbage_token_is_rejected(self, anon_client):
        response = anon_client.get(
            "/classes", headers={"Authorization": "Bearer not-a-real-token"}
        )
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# Classes & students
# ---------------------------------------------------------------------------
class TestClassesAndStudents:
    def test_seeded_class_exists(self, client):
        classes = client.get("/classes").json()
        assert len(classes) == 1
        assert classes[0]["name"] == "Class 8-B"
        assert classes[0]["student_count"] == 12

    def test_seeded_students_have_realistic_details(self, client):
        students = client.get("/students", params={"class_id": 1}).json()
        assert len(students) == 12
        assert all(student["name"] and student["roll_no"] for student in students)
        assert any(student["preferred_language"] == "Hindi" for student in students)

    def test_create_class_and_student(self, client):
        new_class = client.post(
            "/classes", json={"name": "Class 9-A", "grade": "9", "subject": "Maths"}
        ).json()
        student = client.post(
            "/students",
            params={"class_id": new_class["id"]},
            json={"name": "Test Student", "roll_no": "1"},
        ).json()
        assert student["name"] == "Test Student"
        assert client.get("/classes").json()[1]["student_count"] == 1

    def test_csv_import(self, client):
        csv_body = (
            "name,roll_no,parent_name,parent_phone,preferred_language,attendance_pct\n"
            "Asha Rao,20,Mr Rao,+919999999901,Hindi,88\n"
            "Ben Das,21,Mr Das,+919999999902,English,95\n"
        )
        response = client.post(
            "/students/import",
            params={"class_id": 1},
            files={"file": ("students.csv", io.BytesIO(csv_body.encode()), "text/csv")},
        )
        assert response.status_code == 200
        assert response.json()["created"] == 2
        assert len(client.get("/students", params={"class_id": 1}).json()) == 14

    def test_csv_without_name_column_is_rejected(self, client):
        csv_body = "roll_no,parent_name\n1,Mr Rao\n"
        response = client.post(
            "/students/import",
            params={"class_id": 1},
            files={"file": ("bad.csv", io.BytesIO(csv_body.encode()), "text/csv")},
        )
        assert response.status_code == 400

    def test_another_teachers_class_is_not_reachable(self, client):
        assert client.get("/students", params={"class_id": 9999}).status_code == 404


# ---------------------------------------------------------------------------
# Lesson plans
# ---------------------------------------------------------------------------
class TestLessonPlans:
    def test_generate_and_approve(self, client):
        created = client.post(
            "/lessons/generate",
            json={
                "subject": "Science",
                "class_id": 1,
                "topic": "Photosynthesis",
                "duration_minutes": 40,
            },
        ).json()
        assert created["status"] == "draft"
        assert sum(i["minutes"] for i in created["content"]["lesson_flow"]) == 40

        approved = client.post(f"/lessons/{created['id']}/approve").json()
        assert approved["status"] == "approved"
        assert approved["approved_at"] is not None

    def test_edit_then_save(self, client):
        created = client.post(
            "/lessons/generate",
            json={"subject": "Science", "topic": "Photosynthesis", "duration_minutes": 30},
        ).json()
        content = created["content"]
        content["homework"] = "Draw a labelled leaf."
        updated = client.patch(
            f"/lessons/{created['id']}", json={"content": content}
        ).json()
        assert updated["content"]["homework"] == "Draw a labelled leaf."

    def test_regenerate_keeps_the_same_duration(self, client):
        created = client.post(
            "/lessons/generate",
            json={"subject": "Science", "topic": "Photosynthesis", "duration_minutes": 50},
        ).json()
        again = client.post(f"/lessons/{created['id']}/regenerate").json()
        assert sum(i["minutes"] for i in again["content"]["lesson_flow"]) == 50
        assert again["status"] == "draft"

    def test_invalid_duration_is_rejected(self, client):
        response = client.post(
            "/lessons/generate",
            json={"subject": "Science", "topic": "X", "duration_minutes": 0},
        )
        assert response.status_code == 422
        assert "problems" in response.json()

    def test_missing_topic_is_rejected(self, client):
        response = client.post("/lessons/generate", json={"subject": "Science"})
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Grading
# ---------------------------------------------------------------------------
class TestGradingApi:
    def test_bulk_grade_of_the_seeded_class(self, client):
        submissions = client.get("/grading/submissions/1").json()
        assert len(submissions) == 12
        response = client.post(
            "/grading/bulk",
            json={
                "assessment_id": 1,
                "strictness": "standard",
                "submissions": [
                    {"student_id": s["student_id"], "answers": s["answers"]}
                    for s in submissions
                ],
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["graded"] == 12
        assert payload["failed"] == 0

    def test_results_produce_a_realistic_spread(self, client):
        submissions = client.get("/grading/submissions/1").json()
        client.post(
            "/grading/bulk",
            json={
                "assessment_id": 1,
                "submissions": [
                    {"student_id": s["student_id"], "answers": s["answers"]}
                    for s in submissions
                ],
            },
        )
        analysis = client.get("/grading/analysis/1").json()
        percentages = [s["percentage"] for s in analysis["students"]]
        assert min(percentages) < 50 < max(percentages)
        assert analysis["hardest_questions"]

    def test_teacher_override_wins_and_is_remembered(self, client):
        submissions = client.get("/grading/submissions/1").json()
        graded = client.post(
            "/grading/bulk",
            json={
                "assessment_id": 1,
                "submissions": [{"student_id": 1, "answers": submissions[0]["answers"]}],
            },
        ).json()
        result = graded["results"][0]
        question_id = result["result"]["per_question_marks"][0]["question_id"]
        original = result["result"]["per_question_marks"][0]["marks_awarded"]
        new_marks = 0 if original != 0 else 1

        overridden = client.post(
            f"/grading/results/{result['id']}/overrides",
            json={"overrides": [{"question_id": question_id, "marks_awarded": new_marks}]},
        ).json()
        assert overridden["result"]["per_question_marks"][0]["marks_awarded"] == new_marks
        assert question_id in overridden["teacher_overrides"]

        # Re-fetching must show the override, not the AI's original mark.
        refetched = [
            r
            for r in client.get("/grading/results", params={"assessment_id": 1}).json()["results"]
            if r["id"] == result["id"]
        ][0]
        assert question_id in refetched["teacher_overrides"]

    def test_approve_result_clears_the_review_flag(self, client):
        submissions = client.get("/grading/submissions/1").json()
        graded = client.post(
            "/grading/bulk",
            json={
                "assessment_id": 1,
                "submissions": [{"student_id": 1, "answers": submissions[0]["answers"]}],
            },
        ).json()
        approved = client.post(f"/grading/results/{graded['results'][0]['id']}/approve").json()
        assert approved["approved"] is True
        assert approved["needs_teacher_review"] is False

    def test_marks_are_not_final_until_approved(self, client):
        submissions = client.get("/grading/submissions/1").json()
        graded = client.post(
            "/grading/bulk",
            json={
                "assessment_id": 1,
                "submissions": [{"student_id": 1, "answers": submissions[0]["answers"]}],
            },
        ).json()
        assert graded["results"][0]["approved"] is False

    def test_csv_bulk_grading(self, client):
        submissions = client.get("/grading/submissions/1").json()
        header = "student_id,Q1,Q2,Q3,Q4,Q5,Q6,Q7,Q8,Q9,Q10\n"
        row = f"1,{submissions[0]['answers']['Q1']},{submissions[0]['answers']['Q2']}\n"
        # Build a full-width row from the seeded answers.
        values = submissions[0]["answers"]
        row = "1," + ",".join(values[f"Q{i}"] for i in range(1, 11)) + "\n"
        response = client.post(
            "/grading/bulk-csv",
            params={"assessment_id": 1},
            files={
                "file": (
                    "answers.csv",
                    io.BytesIO((header + row).encode()),
                    "text/csv",
                )
            },
        )
        assert response.status_code == 200
        assert response.json()["graded"] == 1

    def test_bulk_grading_is_idempotent(self, client):
        submissions = client.get("/grading/submissions/1").json()
        payload = {
            "assessment_id": 1,
            "submissions": [{"student_id": 1, "answers": submissions[0]["answers"]}],
        }
        client.post("/grading/bulk", json=payload)
        client.post("/grading/bulk", json=payload)
        # One submission row per student, no duplicates.
        assert len(client.get("/grading/submissions/1").json()) == 12


# ---------------------------------------------------------------------------
# Differentiation
# ---------------------------------------------------------------------------
class TestDifferentiationApi:
    def test_generate_three_levels_and_groupings(self, client):
        submissions = client.get("/grading/submissions/1").json()
        client.post(
            "/grading/bulk",
            json={
                "assessment_id": 1,
                "submissions": [
                    {"student_id": s["student_id"], "answers": s["answers"]}
                    for s in submissions
                ],
            },
        )
        material = client.post(
            "/differentiate",
            json={"topic": "Photosynthesis", "class_id": 1, "language": "English"},
        ).json()

        for level in ("support", "core", "extension"):
            assert 8 <= len(material[level]["worksheet"]) <= 10
            assert material[level]["what_changed"]

        grouped = sum(len(g["students"]) for g in material["groupings"])
        assert grouped == 12
        # Names are resolved locally, never sent to the model.
        assert all(st["name"] for g in material["groupings"] for st in g["students"])


# ---------------------------------------------------------------------------
# Parent updates - the safety-critical part
# ---------------------------------------------------------------------------
class TestParentUpdateApprovalGate:
    """Nothing reaches a parent without explicit teacher approval."""

    def _generate_one(self, client):
        return client.post(
            "/parent-updates/generate",
            json={"class_id": 1, "channel": "whatsapp", "tone": "warm", "language": "English"},
        ).json()

    def test_generated_messages_start_as_drafts(self, client):
        payload = self._generate_one(client)
        assert payload["generated"] == 12
        assert all(
            message["status"] in ("draft", "needs_review") for message in payload["messages"]
        )
        assert payload["requires_approval"] is True

    def test_unapproved_messages_cannot_be_sent(self, client):
        message = self._generate_one(client)["messages"][0]
        response = client.post(
            "/parent-updates/send",
            json={"message_ids": [message["id"]], "send_all": False},
        )
        assert response.json()["sent"] == 0
        assert response.json()["blocked"] == 1
        # Status must be unchanged: still a draft.
        assert client.get(f"/parent-updates/{message['id']}").json()["status"] == "draft"

    def test_approve_then_send(self, client):
        message = self._generate_one(client)["messages"][0]
        approved = client.post(f"/parent-updates/{message['id']}/approve").json()
        assert approved["status"] == "approved"
        assert approved["can_send"] is True

        sent = client.post(
            "/parent-updates/send",
            json={"message_ids": [message["id"]], "send_all": False},
        ).json()
        assert sent["sent"] == 1
        assert sent["results"][0]["status"] == "simulated_sent"

    def test_send_all_only_touches_approved_messages(self, client):
        messages = self._generate_one(client)["messages"]
        client.post(f"/parent-updates/{messages[0]['id']}/approve")
        client.post(f"/parent-updates/{messages[1]['id']}/approve")

        sent = client.post(
            "/parent-updates/send", json={"send_all": True, "message_ids": []}
        ).json()
        assert sent["sent"] == 2

        statuses = {
            m["id"]: m["status"] for m in client.get("/parent-updates", params={"class_id": 1}).json()
        }
        assert statuses[messages[0]["id"]] == "simulated_sent"
        assert statuses[messages[1]["id"]] == "simulated_sent"
        # Never-approved messages keep their un-sent status ("draft", or
        # "needs_review" for a flagged student).
        assert statuses[messages[2]["id"]] in ("draft", "needs_review")

    def test_editing_an_approved_message_revokes_approval(self, client):
        message = self._generate_one(client)["messages"][0]
        client.post(f"/parent-updates/{message['id']}/approve")
        edited = client.patch(
            f"/parent-updates/{message['id']}", json={"body": "Completely different text."}
        ).json()
        assert edited["status"] == "draft"
        assert edited["can_send"] is False

    def test_messaging_service_refuses_unapproved_statuses_directly(self):
        from app.models import ParentMessage
        from app.services import messaging

        for status in ("draft", "needs_review", "simulated_sent", "sent", "failed"):
            message = ParentMessage(id=1, status=status, body="hello", channel="whatsapp")
            allowed, _reason = messaging.can_send(message)
            assert allowed is False, f"{status} must not be sendable"
            with pytest.raises(messaging.SendNotAllowed):
                messaging.send_message(message)

        ok = ParentMessage(id=1, status="approved", body="hello", channel="whatsapp")
        assert messaging.can_send(ok)[0] is True

    def test_approving_twice_is_rejected(self, client):
        message = self._generate_one(client)["messages"][0]
        client.post(f"/parent-updates/{message['id']}/approve")
        assert client.post(f"/parent-updates/{message['id']}/approve").status_code == 409

    def test_low_scores_are_flagged_before_sending(self, client):
        payload = self._generate_one(client)
        flagged = [m for m in payload["messages"] if m["needs_teacher_review"]]
        assert flagged, "the seeded class includes low scorers who must be flagged"
        for message in flagged:
            assert message["status"] == "needs_review"
            assert message["review_reasons"]

    def test_whatsapp_messages_respect_the_word_limit(self, client):
        for message in self._generate_one(client)["messages"]:
            assert message["word_count"] <= 120

    def test_messages_contain_no_unreplaced_placeholders(self, client):
        for message in self._generate_one(client)["messages"]:
            assert "{{" not in message["body"]
            assert message["student_name"] in message["body"]

    def test_hindi_generation(self, client):
        payload = client.post(
            "/parent-updates/generate",
            json={"class_id": 1, "channel": "whatsapp", "language": "Hindi"},
        ).json()
        assert payload["generated"] == 12
        assert any("\u0900" <= ch <= "\u097F" for ch in payload["messages"][0]["body"])

    def test_email_generation_has_a_subject(self, client):
        payload = client.post(
            "/parent-updates/generate",
            json={"class_id": 1, "channel": "email", "language": "English"},
        ).json()
        assert all(message["subject"] for message in payload["messages"])


# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------
class TestExports:
    def test_lesson_pdf_and_docx(self, client):
        plan = client.post(
            "/lessons/generate",
            json={"subject": "Science", "topic": "Photosynthesis", "duration_minutes": 40},
        ).json()

        pdf = client.get(f"/export/lesson/{plan['id']}", params={"format": "pdf"})
        assert pdf.status_code == 200
        assert pdf.content[:4] == b"%PDF"
        assert pdf.headers["content-type"] == "application/pdf"

        docx = client.get(f"/export/lesson/{plan['id']}", params={"format": "docx"})
        assert docx.status_code == 200
        assert docx.content[:2] == b"PK"  # zip container

    @pytest.mark.parametrize("level", ["support", "core", "extension"])
    @pytest.mark.parametrize("fmt", ["pdf", "docx"])
    def test_worksheet_exports(self, client, level, fmt):
        material = client.post(
            "/differentiate", json={"topic": "Photosynthesis", "class_id": 1}
        ).json()
        response = client.get(
            f"/export/worksheet/{material['id']}",
            params={"level": level, "format": fmt, "include_answers": True},
        )
        assert response.status_code == 200
        expected = b"%PDF" if fmt == "pdf" else b"PK"
        assert response.content[:4 if fmt == 'pdf' else 2] == expected

    def test_unknown_worksheet_level_is_rejected(self, client):
        material = client.post(
            "/differentiate", json={"topic": "Photosynthesis", "class_id": 1}
        ).json()
        response = client.get(
            f"/export/worksheet/{material['id']}", params={"level": "wizard", "format": "pdf"}
        )
        assert response.status_code == 422

    def test_missing_plan_is_a_404(self, client):
        assert client.get("/export/lesson/9999").status_code == 404


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------
class TestOrchestrator:
    def test_full_run_completes_every_step(self, client):
        run = client.post(
            "/workflow/run",
            json={
                "class_id": 1,
                "topic": "Photosynthesis",
                "subject": "Science",
                "duration_minutes": 40,
                "use_sample_answers": True,
            },
        ).json()

        assert len(run["steps"]) == 5
        for step in run["steps"]:
            assert step["status"] in ("done", "needs_review"), (
                f"step {step['step_key']} ended as {step['status']}: {step['detail']}"
            )
        # "needs_review" means the output is waiting for the teacher - it is a
        # success state, so a clean run must be reported as plain "done".
        assert run["status"] == "done"

    def test_run_fills_the_approval_inbox(self, client):
        run = client.post(
            "/workflow/run",
            json={"class_id": 1, "topic": "Photosynthesis", "use_sample_answers": True},
        ).json()
        assert run["inbox"]["count"] > 0
        kinds = {item["kind"] for item in run["inbox"]["items"]}
        assert "parent_message" in kinds
        assert "grade" in kinds

    def test_run_writes_agent_logs(self, client):
        run = client.post(
            "/workflow/run",
            json={"class_id": 1, "topic": "Photosynthesis", "use_sample_answers": True},
        ).json()
        assert len(run["logs"]) >= 5
        assert all(log["agent"] for log in run["logs"])
        assert all(log["success"] for log in run["logs"])

    def test_run_feeds_results_between_agents(self, client):
        run = client.post(
            "/workflow/run",
            json={"class_id": 1, "topic": "Photosynthesis", "use_sample_answers": True},
        ).json()
        # Grading produced marks, and regrouping used them.
        grade_step = next(s for s in run["steps"] if s["step_key"] == "grade")
        regroup_step = next(s for s in run["steps"] if s["step_key"] == "regroup")
        assert grade_step["output"]["graded"] == 12
        assert regroup_step["output"]["group_sizes"]
        assert sum(regroup_step["output"]["group_sizes"].values()) == 12

    def test_status_endpoint_reflects_the_run(self, client):
        created = client.post(
            "/workflow/run",
            json={"class_id": 1, "topic": "Photosynthesis", "use_sample_answers": True},
        ).json()
        status = client.get(f"/workflow/{created['id']}/status").json()
        assert status["id"] == created["id"]
        assert len(status["steps"]) == 5

    def test_a_single_step_can_be_re_run(self, client):
        created = client.post(
            "/workflow/run",
            json={"class_id": 1, "topic": "Photosynthesis", "use_sample_answers": True},
        ).json()
        rerun = client.post(f"/workflow/{created['id']}/steps/parent_messages/rerun")
        assert rerun.status_code == 200
        assert rerun.json()["rerun_step"] == "parent_messages"
        # The other steps are untouched.
        assert len(rerun.json()["steps"]) == 5

    def test_unknown_step_is_rejected(self, client):
        created = client.post(
            "/workflow/run",
            json={"class_id": 1, "topic": "Photosynthesis", "use_sample_answers": True},
        ).json()
        response = client.post(f"/workflow/{created['id']}/steps/not_a_step/rerun")
        assert response.status_code == 400

    def test_step_definitions_are_exposed(self, client):
        steps = client.get("/workflow/steps/definition").json()
        assert [s["step_key"] for s in steps] == [
            "lesson_plan",
            "differentiate",
            "grade",
            "regroup",
            "parent_messages",
        ]


class TestOrchestratorFailureIsolation:
    """One failing agent must never abort the whole run."""

    def test_a_failing_step_does_not_stop_the_others(self, client, monkeypatch):
        from app.orchestrator import Orchestrator

        def boom(self, context):
            from app.orchestrator import StepOutcome

            raise RuntimeError("the grading service exploded")

        monkeypatch.setattr(Orchestrator, "_step_grade", boom)

        run = client.post(
            "/workflow/run",
            json={"class_id": 1, "topic": "Photosynthesis", "use_sample_answers": True},
        ).json()

        steps = {s["step_key"]: s for s in run["steps"]}
        assert steps["grade"]["status"] == "failed"
        assert "exploded" in steps["grade"]["detail"]

        # The steps after it still ran.
        assert steps["parent_messages"]["status"] in ("done", "needs_review")
        assert steps["lesson_plan"]["status"] in ("done", "needs_review")
        # And the run itself is flagged, not silently "done".
        assert run["status"] in ("done_with_errors", "failed")

    def test_agent_error_in_a_step_is_captured_not_raised(self, client, monkeypatch):
        from app.agents.base import AgentError
        from app.orchestrator import Orchestrator

        def boom(self, context):
            raise AgentError("The model returned invalid JSON", agent="lesson_planner")

        monkeypatch.setattr(Orchestrator, "_step_lesson_plan", boom)

        run = client.post(
            "/workflow/run",
            json={"class_id": 1, "topic": "Photosynthesis", "use_sample_answers": True},
        ).json()
        steps = {s["step_key"]: s for s in run["steps"]}
        assert steps["lesson_plan"]["status"] == "failed"
        assert "invalid JSON" in steps["lesson_plan"]["detail"]
        # The pipeline carried on and grading still happened.
        assert steps["grade"]["status"] in ("done", "needs_review")

    def test_regroup_is_skipped_when_there_are_no_marks(self, client, monkeypatch):
        from app.orchestrator import Orchestrator, StepOutcome

        def skip_grading(self, context):
            context.performance = []
            return StepOutcome(status="done", detail="no marks", output={"graded": 0})

        monkeypatch.setattr(Orchestrator, "_step_grade", skip_grading)

        run = client.post(
            "/workflow/run",
            json={"class_id": 1, "topic": "Photosynthesis", "use_sample_answers": True},
        ).json()
        steps = {s["step_key"]: s for s in run["steps"]}
        assert steps["regroup"]["status"] == "skipped"
        assert "Grade the class first" in steps["regroup"]["detail"]
        # One skipped step downgrades the run, but does not fail it.
        assert run["status"] == "done_with_errors"

    def test_run_status_semantics(self, client, monkeypatch):
        """done / done_with_errors / failed must mean what they say."""
        from app.orchestrator import Orchestrator

        # 1. Clean run -> "done" (even though several steps need review).
        clean = client.post(
            "/workflow/run",
            json={"class_id": 1, "topic": "Photosynthesis", "use_sample_answers": True},
        ).json()
        assert clean["status"] == "done"
        assert any(s["status"] == "needs_review" for s in clean["steps"])

        # 2. Every step broken -> "failed".
        def boom(self, context):
            raise RuntimeError("down")

        for name in (
            "_step_lesson_plan",
            "_step_differentiate",
            "_step_grade",
            "_step_regroup",
            "_step_parent_messages",
        ):
            monkeypatch.setattr(Orchestrator, name, boom)

        broken = client.post(
            "/workflow/run",
            json={"class_id": 1, "topic": "Photosynthesis", "use_sample_answers": True},
        ).json()
        assert broken["status"] == "failed"
        assert all(s["status"] == "failed" for s in broken["steps"])

    def test_run_survives_a_failing_first_step(self, client, monkeypatch):
        from app.orchestrator import Orchestrator

        def boom(self, context):
            raise RuntimeError("immediate failure")

        monkeypatch.setattr(Orchestrator, "_step_lesson_plan", boom)

        response = client.post(
            "/workflow/run",
            json={"class_id": 1, "topic": "Photosynthesis", "use_sample_answers": True},
        )
        # The endpoint returns 200 with a run that records the failure.
        assert response.status_code == 200
        steps = {s["step_key"]: s for s in response.json()["steps"]}
        assert steps["lesson_plan"]["status"] == "failed"


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
class TestDashboard:
    def test_summary_shape(self, client):
        summary = client.get("/dashboard/summary").json()
        for key in (
            "lesson_plans_created",
            "papers_graded",
            "messages_sent",
            "time_saved_this_week_minutes",
            "weekly_time_saved",
            "class_overview",
        ):
            assert key in summary

    def test_time_saved_increases_after_work(self, client):
        before = client.get("/dashboard/summary").json()["time_saved_this_week_minutes"]
        client.post(
            "/lessons/generate",
            json={"subject": "Science", "topic": "Photosynthesis", "duration_minutes": 40},
        )
        after = client.get("/dashboard/summary").json()["time_saved_this_week_minutes"]
        assert after > before

    def test_weekly_chart_has_six_weeks(self, client):
        assert len(client.get("/dashboard/summary").json()["weekly_time_saved"]) == 6


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------
class TestRateLimit:
    def test_too_many_ai_calls_are_throttled(self, client):
        from app.dependencies import reset_rate_limits

        reset_rate_limits()
        statuses = []
        for _ in range(45):
            statuses.append(
                client.post(
                    "/lessons/generate",
                    json={"subject": "Science", "topic": "X", "duration_minutes": 40},
                ).status_code
            )
            if statuses[-1] == 429:
                break
        assert 429 in statuses, "the rate limiter never engaged"
        reset_rate_limits()
