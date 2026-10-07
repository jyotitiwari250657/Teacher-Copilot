"""FastAPI dependencies: authentication, rate limiting, shared lookups."""
from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import Session, select

from .config import settings
from .db import get_session
from .models import Teacher
from .security import decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
def get_current_teacher(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    session: Session = Depends(get_session),
) -> Teacher:
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated. Please log in.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_access_token(credentials.credentials)
    if not payload or "sub" not in payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Your session has expired. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        teacher_id = int(payload["sub"])
    except (TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Malformed session token.")

    teacher = session.get(Teacher, teacher_id)
    if teacher is None:
        raise HTTPException(status_code=401, detail="Account no longer exists.")
    return teacher


# ---------------------------------------------------------------------------
# Rate limiting (in-process sliding window, keyed by teacher)
# ---------------------------------------------------------------------------
_hits: dict[str, deque[float]] = defaultdict(deque)


def rate_limit(max_calls: Optional[int] = None, window: Optional[int] = None) -> None:
    """Dependency factory guarding LLM-backed endpoints."""

    limit = max_calls if max_calls is not None else settings.rate_limit_max_calls
    seconds = window if window is not None else settings.rate_limit_window_seconds

    def _dependency(
        request: Request, teacher: Teacher = Depends(get_current_teacher)
    ) -> Teacher:
        key = f"{teacher.id}"
        now = time.monotonic()
        bucket = _hits[key]
        while bucket and now - bucket[0] > seconds:
            bucket.popleft()
        if len(bucket) >= limit:
            retry_after = int(seconds - (now - bucket[0])) + 1
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"Too many AI requests. Please wait {retry_after}s and try again "
                    f"(limit: {limit} per {seconds}s)."
                ),
                headers={"Retry-After": str(retry_after)},
            )
        bucket.append(now)
        return teacher

    return _dependency


def reset_rate_limits() -> None:
    """Test helper."""
    _hits.clear()
