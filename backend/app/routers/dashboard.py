"""Dashboard summary endpoint."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlmodel import Session

from ..db import get_session
from ..dependencies import get_current_teacher
from ..models import Teacher
from ..services.analytics import dashboard_summary, humanise_minutes

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary")
def summary(
    teacher: Teacher = Depends(get_current_teacher),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    data = dashboard_summary(session, teacher.id)
    data["time_saved_this_week_human"] = humanise_minutes(
        data["time_saved_this_week_minutes"]
    )
    data["time_saved_all_time_human"] = humanise_minutes(
        data["time_saved_all_time_minutes"]
    )
    data["by_task_human"] = {
        task: humanise_minutes(minutes) for task, minutes in data["time_saved_by_task"].items()
    }
    return data