from __future__ import annotations

from typing import Any

import httpx
from fastapi import HTTPException, Request

from backend.schemas import AuthUser
from backend.session import auth_base_url

ORGANIZATION_LIST_PATH = "/api/auth/organization/list"
_STATE_KEY = "organization_ids"


def require_organization_member(request: Request, user: AuthUser, organization_id: str | None) -> str:
    """Return a verified organization id the authenticated user belongs to.

    422 if missing; 403 if the user is not a member. Does not disclose whether
    a catalogue/job exists in another organization.
    """
    org_id = (organization_id or "").strip()
    if not org_id:
        raise HTTPException(status_code=422, detail="organization_id is required")
    memberships = fetch_organization_ids(request, user)
    if org_id not in memberships:
        raise HTTPException(status_code=403, detail="Not authorized for this organization.")
    return org_id


def fetch_organization_ids(request: Request, user: AuthUser) -> set[str]:
    cached = getattr(request.state, _STATE_KEY, None)
    if cached is not None:
        return cached
    ids = _load_organization_ids(request, user)
    setattr(request.state, _STATE_KEY, ids)
    return ids


def _load_organization_ids(request: Request, _user: AuthUser) -> set[str]:
    cookie = request.headers.get("cookie")
    authorization = request.headers.get("authorization")
    headers: dict[str, str] = {}
    if cookie:
        headers["cookie"] = cookie
    if authorization:
        headers["authorization"] = authorization
    if not headers:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        response = httpx.get(f"{auth_base_url()}{ORGANIZATION_LIST_PATH}", headers=headers, timeout=5.0)
    except httpx.HTTPError:
        raise HTTPException(status_code=401, detail="Authentication service unavailable") from None

    if response.status_code == 401:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if response.status_code != 200:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        payload = response.json()
    except (ValueError, TypeError):
        raise HTTPException(status_code=401, detail="Not authenticated") from None
    return parse_organization_ids(payload)


def parse_organization_ids(payload: Any) -> set[str]:
    """Accept Better Auth's array of organizations, plus a few wrapped shapes."""
    rows: Any = payload
    if isinstance(payload, dict):
        rows = payload.get("organizations")
        if rows is None:
            rows = payload.get("data")
        if rows is None:
            rows = payload.get("body")
        if rows is None:
            return set()
    if not isinstance(rows, list):
        return set()
    ids: set[str] = set()
    for item in rows:
        if isinstance(item, str):
            cleaned = item.strip()
            if cleaned:
                ids.add(cleaned)
            continue
        if not isinstance(item, dict):
            continue
        raw = item.get("id") or item.get("organizationId") or item.get("organization_id")
        if raw is None:
            continue
        cleaned = str(raw).strip()
        if cleaned:
            ids.add(cleaned)
    return ids
