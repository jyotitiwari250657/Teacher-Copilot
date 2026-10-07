"""CRUD for students, including CSV import."""
from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlmodel import Session, select

from ..db import get_session
from ..dependencies import get_current_teacher
from ..models import Student, Teacher
from ..routers.classes import get_owned_class
from ..schemas import StudentCreate, StudentOut, StudentUpdate

router = APIRouter(prefix="/students", tags=["students"])

EXPECTED_HEADER = ["name", "roll_no", "parent_name", "parent_phone", "parent_email",
                   "preferred_language", "attendance_pct"]


def _owned_student(student_id: int, teacher: Teacher, session: Session) -> Student:
    student = session.get(Student, student_id)
    if student is None:
        raise HTTPException(status_code=404, detail="Student not found.")
    if student.class_id is None:
        raise HTTPException(status_code=404, detail="Student not found.")
    get_owned_class(student.class_id, teacher, session)
    return student


@router.get("", response_model=list[StudentOut])
def list_students(
    class_id: int,
    teacher: Teacher = Depends(get_current_teacher),
    session: Session = Depends(get_session),
) -> list[StudentOut]:
    get_owned_class(class_id, teacher, session)
    students = session.exec(select(Student).where(Student.class_id == class_id)).all()
    def sort_key(s: Student) -> tuple[int, str]:
        try:
            return (int(s.roll_no), "")
        except (TypeError, ValueError):
            return (10**6, s.roll_no or s.name)
    return [StudentOut.model_validate(s) for s in sorted(students, key=sort_key)]


@router.post("", response_model=StudentOut, status_code=201)
def create_student(
    class_id: int,
    payload: StudentCreate,
    teacher: Teacher = Depends(get_current_teacher),
    session: Session = Depends(get_session),
) -> StudentOut:
    get_owned_class(class_id, teacher, session)
    student = Student(**payload.model_dump(), class_id=class_id)
    session.add(student)
    session.commit()
    session.refresh(student)
    return StudentOut.model_validate(student)


@router.post("/import", response_model=dict)
async def import_students(
    class_id: int,
    file: UploadFile = File(...),
    teacher: Teacher = Depends(get_current_teacher),
    session: Session = Depends(get_session),
) -> dict:
    """Bulk-import students from a CSV with a header row.

    Columns: name, roll_no, parent_name, parent_phone, parent_email,
             preferred_language, attendance_pct
    Unknown columns are ignored; missing optional columns fall back to defaults.
    """
    get_owned_class(class_id, teacher, session)

    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="CSV must be UTF-8 encoded.")

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise HTTPException(status_code=400, detail="The CSV looks empty.")

    normalised = {name.strip().lower(): name for name in reader.fieldnames if name}
    if "name" not in normalised:
        raise HTTPException(
            status_code=400,
            detail="The CSV must have a 'name' column. "
            f"Expected columns: {', '.join(EXPECTED_HEADER)}",
        )

    created, errors = 0, []
    for row_index, row in enumerate(reader, start=2):
        def value(key: str, default: str = "") -> str:
            column = normalised.get(key)
            return (row.get(column) or default).strip() if column else default

        name = value("name")
        if not name:
            errors.append(f"Row {row_index}: missing name")
            continue
        try:
            attendance = float(value("attendance_pct", "100") or 100)
        except ValueError:
            attendance = 100.0
        attendance = max(0.0, min(100.0, attendance))
        language = value("preferred_language", "English") or "English"
        if language.lower() not in {"english", "hindi"}:
            language = "English"

        session.add(
            Student(
                name=name[:120],
                roll_no=value("roll_no")[:20],
                class_id=class_id,
                parent_name=value("parent_name")[:120],
                parent_phone=value("parent_phone")[:32],
                parent_email=value("parent_email")[:180],
                preferred_language=language.title(),
                attendance_pct=attendance,
                teacher_notes=value("teacher_notes")[:1000],
            )
        )
        created += 1

    session.commit()
    return {"created": created, "errors": errors}


@router.get("/{student_id}", response_model=StudentOut)
def get_student(
    student_id: int,
    teacher: Teacher = Depends(get_current_teacher),
    session: Session = Depends(get_session),
) -> StudentOut:
    return StudentOut.model_validate(_owned_student(student_id, teacher, session))


@router.patch("/{student_id}", response_model=StudentOut)
def update_student(
    student_id: int,
    payload: StudentUpdate,
    teacher: Teacher = Depends(get_current_teacher),
    session: Session = Depends(get_session),
) -> StudentOut:
    student = _owned_student(student_id, teacher, session)
    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(student, field, value)
    session.add(student)
    session.commit()
    session.refresh(student)
    return StudentOut.model_validate(student)


@router.delete("/{student_id}", status_code=204)
def delete_student(
    student_id: int,
    teacher: Teacher = Depends(get_current_teacher),
    session: Session = Depends(get_session),
) -> None:
    session.delete(_owned_student(student_id, teacher, session))
    session.commit()


@router.get("/export/template")
def csv_template() -> dict:
    """So the UI can offer a one-click CSV template download."""
    return {
        "filename": "students_template.csv",
        "content": (
            "name,roll_no,parent_name,parent_phone,parent_email,"
            "preferred_language,attendance_pct\n"
            "Aarav Sharma,1,Mr. Rajesh Sharma,+919810001001,"
            "rajesh@example.com,English,95\n"
            "Diya Patel,2,Mrs. Meera Patel,+919810001002,"
            "meera@example.com,Hindi,88\n"
        ),
    }