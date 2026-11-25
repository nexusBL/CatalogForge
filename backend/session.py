from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx
from fastapi import HTTPException, Request

from backend.schemas import AuthUser

SESSION_PATH = "/api/auth/get-session"
DEFAULT_AUTH_URL = "http://localhost:3001"


def auth_base_url() -> str:
    """Use the same Better Auth origin as the login proxy (auth/.env / AUTH_URL)."""
    configured = (os.getenv("BETTER_AUTH_URL") or os.getenv("AUTH_URL") or "").strip().rstrip("/")
    if configured:
        return configured
    auth_env = Path(__file__).resolve().parents[1] / "auth" / ".env"
    if auth_env.is_file():
        for raw in auth_env.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line.startswith("BETTER_AUTH_URL="):
                value = line.split("=", 1)[1].strip().strip('"').strip("'").rstrip("/")
                if value:
                    return value
    return DEFAULT_AUTH_URL


def require_session(request: Request) -> AuthUser:
    cookie = request.headers.get("cookie")
    authorization = request.headers.get("authorization")
    if not cookie and not authorization:
        raise HTTPException(status_code=401, detail="Not authenticated")

    base_url = auth_base_url()
    headers: dict[str, str] = {}
    if cookie:
        headers["cookie"] = cookie
    if authorization:
        headers["authorization"] = authorization

    try:
        response = httpx.get(f"{base_url}{SESSION_PATH}", headers=headers, timeout=5.0)
    except httpx.HTTPError:
        raise HTTPException(status_code=401, detail="Authentication service unavailable") from None

    if response.status_code != 200:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        payload = response.json()
    except (ValueError, TypeError):
        raise HTTPException(status_code=401, detail="Not authenticated") from None
    if not payload or not isinstance(payload, dict) or not payload.get("user"):
        raise HTTPException(status_code=401, detail="Not authenticated")

    user: dict[str, Any] = payload["user"]
    email = user.get("email")
    user_id = user.get("id")
    if not email or not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return AuthUser(id=str(user_id), email=str(email))
