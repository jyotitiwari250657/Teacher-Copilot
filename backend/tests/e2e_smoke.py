"""End-to-end smoke test against a running backend (mock mode).

Exercises the full Definition of Done: login -> classes -> lesson plan ->
grading -> differentiation -> parent updates -> approval gate -> workflow.
"""
from __future__ import annotations

import json
import sys

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
client = httpx.Client(base_url=BASE, timeout=180.0)

failures: list[str] = []


def check(label: str, condition: bool, extra: str = "") -> None:
    mark = "PASS" if condition else "FAIL"
    print(f"[{mark}] {label}" + (f"  -- {extra}" if extra else ""))
    if not condition:
        failures.append(label)


print("=" * 70)
print("TeacherCopilot end-to-end smoke test")
print("=" * 70)

# --- health -----------------------------------------------------------------
health = client.get("/api/health").json()
check("health ok", health["status"] == "ok", f"mock={health['llm']['mock_mode']}")

# --- login ------------------------------------------------------------------
r = client.post(
    "/auth/login", json={"email": "demo@teachercopilot.app", "password": "demo1234"}
)
check("demo login", r.status_code == 200, r.text[:120])
if r.status_code != 200:
    print("Cannot continue without auth.")
    raise SystemExit(1)
token = r.json()["access_token"]
client.headers["Authorization"] = f"Bearer {token}"
teacher = r.json()["teacher"]
check("teacher identity", teacher["email"] == "demo@teachercopilot.app", teacher["name"])

# bad password must fail
bad = httpx.post(
    f"{BASE}/auth/login", json={"email": "demo@teachercopilot.app", "password": "wrong"}
)
check("wrong password rejected", bad.status_code == 401)

# --- classes / students -----------------------------------------------------
classes = client.get("/classes").json()
check("class seeded", len(classes) >= 1, f"{len(classes)} class(es)")
class_id = classes[0]["id"]
students = client.get("/students", params={"class_id": class_id}).json()
check("12 students seeded", len(students) == 12, f"{len(students)} students")
check("realistic names", all(s["name"] for s in students), students[0]["name"])

# --- assessments ------------------------------------------------------------
assessments = client.get("/grading/assessments", params={"class_id": class_id}).json()
check("question paper seeded", len(assessments) >= 1)
assessment = assessments[0]
check("paper has 10 questions", assessment["question_count"] == 10, str(assessment["total_marks"]))

# --- lesson planner ---------------------------------------------------------
r = client.post(
    "/lessons/generate",
    json={
        "subject": "Science",
        "class_id": class_id,
        "topic": "Photosynthesis",
        "duration_minutes": 45,
        "board": "CBSE",
        "language": "English",
    },
)
check("lesson generated", r.status_code == 200, r.text[:160])
plan = r.json()
total_minutes = sum(i["minutes"] for i in plan["content"]["lesson_flow"])
check("minutes sum to 45", total_minutes == 45, f"got {total_minutes}")
check("exit ticket has 3", len(plan["content"]["exit_ticket"]) == 3)
check("starts as draft", plan["status"] == "draft")

# Hindi variant
rh = client.post(
    "/lessons/generate",
    json={"subject": "Science", "grade": "8", "topic": "Photosynthesis",
          "duration_minutes": 40, "language": "Hindi"},
)
check("Hindi lesson generated", rh.status_code == 200)
check("Hindi content is Devanagari",
      any("\u0900" <= ch <= "\u097F" for ch in rh.json()["content"]["homework"]))

# approve
ra = client.post(f"/lessons/{plan['id']}/approve")
check("lesson approved", ra.json()["status"] == "approved")

# --- grading ----------------------------------------------------------------
s = client.get("/students", params={"class_id": class_id}).json()
submissions = client.get(f"/grading/submissions/{assessment['id']}").json()
check("sample submissions seeded", len(submissions) == 12, f"{len(submissions)}")

r = client.post(
    "/grading/bulk",
    json={
        "assessment_id": assessment["id"],
        "strictness": "standard",
        "submissions": [
            {"student_id": st["id"], "answers": sub["answers"]}
            for st, sub in zip(s, submissions)
        ],
    },
)
check("bulk grading", r.status_code == 200, r.text[:160])
bulk = r.json()
check("all 12 graded", bulk["graded"] == 12, f"graded={bulk['graded']} failed={bulk['failed']}")

pcts = sorted(x["percentage"] for x in bulk["results"])
check("score spread is realistic",
      pcts[0] < 50 and pcts[-1] > 70, f"min={pcts[0]} max={pcts[-1]}")

# overrides
first = bulk["results"][0]
qid = first["result"]["per_question_marks"][0]["question_id"]
r = client.post(
    f"/grading/results/{first['id']}/overrides",
    json={"overrides": [{"question_id": qid, "marks_awarded": 0, "feedback": "Teacher says no marks."}]},
)
check("teacher override saved", r.status_code == 200)
overridden = r.json()
check("override wins over AI",
      overridden["result"]["per_question_marks"][0]["marks_awarded"] == 0,
      f"marks={overridden['result']['per_question_marks'][0]['marks_awarded']}")

ra = client.post(f"/grading/results/{first['id']}/approve")
check("grade approved", ra.json()["approved"] is True)

# analysis
analysis = client.get(f"/grading/analysis/{assessment['id']}").json()
check("class analysis", analysis["graded"] == 12,
      f"avg={analysis['average_percentage']} hardest={[q['question_id'] for q in analysis['hardest_questions']]}")
check("hardest questions identified", len(analysis["hardest_questions"]) > 0)

# --- differentiation --------------------------------------------------------
r = client.post(
    "/differentiate",
    json={"topic": "Photosynthesis", "class_id": class_id, "language": "English",
          "lesson_plan_id": plan["id"]},
)
check("differentiation generated", r.status_code == 200, r.text[:160])
mat = r.json()
for level in ("support", "core", "extension"):
    n = len(mat[level]["worksheet"])
    check(f"{level} worksheet 8-10 questions", 8 <= n <= 10, f"{n} questions")
    check(f"{level} answer key matches", len(mat[level]["answer_key"]) == n)
total_grouped = sum(len(g["students"]) for g in mat["groupings"])
check("students grouped", total_grouped == 12, f"{total_grouped} grouped")
check("groupings have real names", all(
    st["name"] for g in mat["groupings"] for st in g["students"]))

# --- parent updates ---------------------------------------------------------
r = client.post(
    "/parent-updates/generate",
    json={"class_id": class_id, "channel": "whatsapp", "language": "English", "tone": "warm"},
)
check("parent messages generated", r.status_code == 200, r.text[:160])
gen = r.json()
check("12 messages created", gen["generated"] == 12, f"{gen['generated']} created")
msg = gen["messages"][0]
check("no unreplaced placeholders", "{{" not in msg["body"], msg["body"][:80])
check("whatsapp under 120 words", msg["word_count"] <= 120, f"{msg['word_count']} words")
check("messages need approval", msg["status"] in ("draft", "needs_review"), msg["status"])
check("low scores flagged", any(m["needs_teacher_review"] for m in gen["messages"]),
      f"{sum(1 for m in gen['messages'] if m['needs_teacher_review'])} flagged")

# THE SAFETY GATE -----------------------------------------------------------
r = client.post("/parent-updates/send", json={"message_ids": [msg["id"]], "send_all": False})
check("unapproved send is refused", r.json()["sent"] == 0 and r.json()["blocked"] == 1,
      r.json()["results"][0]["detail"][:90] if r.json()["results"] else "no results")

# approve then send
r = client.post(f"/parent-updates/{msg['id']}/approve")
check("approve message", r.json()["status"] == "approved")
r = client.post("/parent-updates/send", json={"message_ids": [msg["id"]], "send_all": False})
sent = r.json()
check("approved message sends", sent["sent"] == 1, sent["results"][0]["detail"][:80])
check("send recorded as simulated", sent["results"][0]["status"] == "simulated_sent")

# editing an approved message revokes approval
r = client.patch(f"/parent-updates/{msg['id']}", json={"body": "Changed after approval."})
check("editing revokes approval", r.json()["status"] == "draft", r.json()["status"])

# --- exports ----------------------------------------------------------------
r = client.get(f"/export/lesson/{plan['id']}", params={"format": "pdf"})
check("lesson PDF", r.status_code == 200 and r.content[:4] == b"%PDF",
      f"{len(r.content)} bytes")
r = client.get(f"/export/lesson/{plan['id']}", params={"format": "docx"})
check("lesson DOCX", r.status_code == 200 and r.content[:2] == b"PK",
      f"{len(r.content)} bytes")
for level in ("support", "core", "extension"):
    r = client.get(f"/export/worksheet/{mat['id']}",
                   params={"format": "pdf", "level": level, "include_answers": True})
    check(f"worksheet PDF ({level})", r.status_code == 200 and r.content[:4] == b"%PDF",
          f"{len(r.content)} bytes")
r = client.get(f"/export/worksheet/{mat['id']}", params={"format": "docx", "level": "core"})
check("worksheet DOCX", r.status_code == 200 and r.content[:2] == b"PK", f"{len(r.content)} bytes")

# --- workflow ---------------------------------------------------------------
r = client.post(
    "/workflow/run",
    json={"class_id": class_id, "topic": "Photosynthesis", "subject": "Science",
          "language": "English", "duration_minutes": 40, "use_sample_answers": True},
)
check("workflow run", r.status_code == 200, r.text[:160])
run = r.json()
check("5 steps recorded", len(run["steps"]) == 5, f"{len(run['steps'])} steps")
for step in run["steps"]:
    check(f"step '{step['step_key']}' {step['status']}",
          step["status"] in ("done", "needs_review"), step["detail"][:70])
check("run finished", run["status"] in ("done", "done_with_errors"), run["status"])
check("approval inbox filled", run["inbox"]["count"] > 0,
      f"{run['inbox']['count']} items")
check("agent logs written", len(run["logs"]) > 0, f"{len(run['logs'])} logs")

# re-run a single step
r = client.post(f"/workflow/{run['id']}/steps/parent_messages/rerun")
check("re-run single step", r.status_code == 200, r.text[:160])

# status endpoint
r = client.get(f"/workflow/{run['id']}/status")
check("workflow status endpoint", r.status_code == 200 and r.json()["id"] == run["id"])

# --- dashboard --------------------------------------------------------------
dash = client.get("/dashboard/summary").json()
check("dashboard summary", "time_saved_this_week_minutes" in dash,
      f"week={dash['time_saved_this_week_minutes']}min "
      f"({dash['time_saved_this_week_human']}), "
      f"plans={dash['lesson_plans_created']}, messages={dash['messages_sent']}")
check("weekly chart populated", len(dash["weekly_time_saved"]) == 6)
check("class overview populated", len(dash["class_overview"]) >= 1)

# --- auth required ----------------------------------------------------------
r = httpx.get(f"{BASE}/classes")
check("unauthenticated request rejected", r.status_code == 401)

# --- validation -------------------------------------------------------------
r = client.post("/lessons/generate", json={"subject": "", "topic": "", "duration_minutes": 1})
check("input validation rejects bad payload", r.status_code == 422, r.text[:80])

print("=" * 70)
if failures:
    print(f"RESULT: {len(failures)} FAILURE(S)")
    for f in failures:
        print("  -", f)
    raise SystemExit(1)
print("RESULT: ALL CHECKS PASSED")