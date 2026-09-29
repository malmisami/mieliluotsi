from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException, Request
from sqlalchemy import create_engine


async def get_active_session(request: Request) -> dict[str, Any]:
    return request.state.session_info if hasattr(request.state, 'session_info') else {}
