"""Privacy helpers.

The rule: student names, roll numbers and contact details are never sent to the
language model. Agents receive pseudonymous refs (``S01``, ``S02``, ...) and the
name is re-attached locally after generation.
"""
from __future__ import annotations

from typing import Any, Iterable

from ..models import Student


def make_refs(students: Iterable[Student]) -> dict[int, str]:
    """Map ``student_id -> "S01"`` in a stable roll-number order."""
    ordered = sorted(students, key=lambda s: _roll_key(s))
    return {student.id: f"S{index:02d}" for index, student in enumerate(ordered, 1)}


def _roll_key(student: Student) -> tuple[int, str]:
    try:
        return (int(student.roll_no), "")
    except (TypeError, ValueError):
        return (10**6, student.roll_no or student.name)


def student_ref(ref: str) -> str:
    """Normalise a ref so 's1', 'S-01' and 'S01' all compare equal."""
    digits = "".join(ch for ch in str(ref) if ch.isdigit())
    return f"S{int(digits):02d}" if digits else str(ref).upper()


def ref_to_student_id(refs: dict[int, str], ref: str) -> int | None:
    target = student_ref(ref)
    for student_id, value in refs.items():
        if student_ref(value) == target:
            return student_id
    return None


def scrub(payload: Any, students: Iterable[Student]) -> Any:
    """Defence in depth: replace any known name/phone/email with its ref.

    Used as a final guard before a prompt is built, so a future code change
    cannot accidentally leak an identifier to the model.
    """
    secrets: list[tuple[str, str]] = []
    for student in students:
        secrets.append((student.name, "<student>"))
        if student.parent_name:
            secrets.append((student.parent_name, "<parent>"))
        if student.parent_phone:
            secrets.append((student.parent_phone, "<phone>"))
        if student.parent_email:
            secrets.append((student.parent_email, "<email>"))
        if student.roll_no and len(student.roll_no) > 1:
            secrets.append((student.roll_no, "<roll>"))

    if isinstance(payload, str):
        text = payload
        for secret, placeholder in secrets:
            if secret:
                text = text.replace(secret, placeholder)
        return text
    if isinstance(payload, dict):
        return {k: scrub(v, students) for k, v in payload.items()}
    if isinstance(payload, list):
        return [scrub(v, students) for v in payload]
    return payload