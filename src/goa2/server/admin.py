"""Gating for admin-only endpoints (replay debugger + bug-report triage).

Two independent enablement paths:

- ``GOA2_REPLAY_API`` truthy (local development): admin routes are registered
  and require no auth — the historical dev-only behavior.
- ``GOA2_ADMIN_TOKEN`` set (production): admin routes are registered but every
  request must carry ``Authorization: Bearer <token>``. Comparison is
  constant-time. This is what lets the developer triage bug reports and step
  through replays on the deployed server.

When neither is configured the routes are never registered (404), so the
omniscient replay view is unreachable — same guarantee as before.
"""

from __future__ import annotations

import os
import secrets

from fastapi import HTTPException, Request


def replay_api_enabled() -> bool:
    """True when GOA2_REPLAY_API is set to a truthy value (dev mode, no auth)."""
    return os.environ.get("GOA2_REPLAY_API", "").strip().lower() in ("1", "true", "yes", "on")


def _admin_token() -> str | None:
    token = os.environ.get("GOA2_ADMIN_TOKEN", "").strip()
    return token or None


def admin_api_enabled() -> bool:
    """True when the admin routers should be registered at all."""
    return replay_api_enabled() or _admin_token() is not None


def require_admin(request: Request) -> None:
    """FastAPI dependency guarding every admin route.

    Dev flag set -> open. Otherwise a matching admin bearer token is required.
    The no-token-configured branch is defense in depth: the router should not
    be mounted in that case.
    """
    if replay_api_enabled():
        return
    token = _admin_token()
    if token is None:
        raise HTTPException(status_code=404, detail="Not found")
    auth = request.headers.get("Authorization", "")
    supplied = auth[len("Bearer ") :] if auth.startswith("Bearer ") else ""
    if not supplied or not secrets.compare_digest(supplied, token):
        raise HTTPException(status_code=401, detail="Invalid admin token")
