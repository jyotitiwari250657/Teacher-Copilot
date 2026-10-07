"""CRUD for school classes."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..db import get_session
from ..dependencies import get_current_teacher
from ..models import SchoolClass, Student, Teacher
from ..schemas import ClassCreate, ClassOut, ClassUpdate

router = APIRouter(prefix="/classes", tags=["classes"])


def _to_out(school_class: SchoolClass, student_count: int = 0) -> ClassOut:
    data = ClassOut.model_validate(school_class)
    data.student_count = student_count
    return data


def get_owned_class(
    class_id: int, teacher: Teacher, session: Session
) -> SchoolClass:
    school_class = session.get(SchoolClass, class_id)
    if school_class is None or school_class.teacher_id != teacher.id:
        raise HTTPException(status_code=404, detail="Class not found.")
    return school_class


@router.get("", response_model=list[ClassOut])
def list_classes(
    teacher: Teacher = Depends(get_current_teacher),
    session: Session = Depends(get_session),
) -> list[ClassOut]:
    classes = session.exec(
        select(SchoolClass).where(SchoolClass.teacher_id == teacher.id)
    ).all()
    out: list[ClassOut] = []
    for school_class in classes:
        count = len(
            session.exec(select(Student).where(Student.class_id == school_class.id)).all()
        )
        out.append(_to_out(school_class, count))
    return sorted(out, key=lambda c: (c.grade, c.name))


@router.post("", response_model=ClassOut, status_code=201)
def create_class(
    payload: ClassCreate,
    teacher: Teacher = Depends(get_current_teacher),
    session: Session = Depends(get_session),
) -> ClassOut:
    school_class = SchoolClass(
        **payload.model_dump(), teacher_id=teacher.id
    )
    session.add(school_class)
    session.commit()
    session.refresh(school_class)
    return _to_out(school_class, 0)


@router.get("/{class_id}", response_model=ClassOut)
def get_class(
    class_id: int,
    teacher: Teacher = Depends(get_current_teacher),
    session: Session = Depends(get_session),
) -> ClassOut:
    school_class = get_owned_class(class_id, teacher, session)
    count = len(
        session.exec(select(Student).where(Student.class_id == class_id)).all()
    )
    return _to_out(school_class, count)


@router.patch("/{class_id}", response_model=ClassOut)
def update_class(
    class_id: int,
    payload: ClassUpdate,
    teacher: Teacher = Depends(get_current_teacher),
    session: Session = Depends(get_session),
) -> ClassOut:
    school_class = get_owned_class(class_id, teacher, session)
    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(school_class, field, value)
    session.add(school_class)
    session.commit()
    session.refresh(school_class)
    return _to_out(school_class)


@router.delete("/{class_id}", status_code=204)
def delete_class(
    class_id: int,
    teacher: Teacher = Depends(get_current_teacher),
    session: Session = Depends(get_session),
) -> None:
    school_class = get_owned_class(class_id, teacher, session)
    for student in session.exec(
        select(Student).where(Student.class_id == class_id)
    ).all():
        session.delete(student)
    session.delete(school_class)
    session.commit()