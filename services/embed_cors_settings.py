"""Embed widget CORS: env default + optional ``system_settings`` override (super admin)."""

from __future__ import annotations

from flask import make_response, request

from config import EMBED_CORS_ORIGINS
from extensions import db
from models import SystemSetting

EMBED_CORS_SETTING_KEY = "embed_cors_origins"

ALLOW_METHODS = "POST, OPTIONS"
ALLOW_HEADERS = "Content-Type, Authorization, X-Nexura-Embed-Key"
MAX_AGE = "86400"


def embed_cors_env_default_display() -> str:
    """Raw env value shown as hint in Platform settings (falls back to ``*`` when unset)."""
    r = (EMBED_CORS_ORIGINS or "").strip()
    return r if r else "*"


def get_embed_cors_effective_raw() -> str:
    """Comma-separated origins or ``*``. Non-empty DB row overrides ``EMBED_CORS_ORIGINS``."""
    row = SystemSetting.query.filter_by(key=EMBED_CORS_SETTING_KEY).first()
    if row and (row.value or "").strip():
        return (row.value or "").strip()
    env_raw = (EMBED_CORS_ORIGINS or "").strip()
    return env_raw if env_raw else "*"


def save_embed_cors_from_form(raw: str | None) -> None:
    """Persist or clear DB override. Empty string deletes the row (env default applies)."""
    submitted = (raw or "").strip()
    row = SystemSetting.query.filter_by(key=EMBED_CORS_SETTING_KEY).first()
    if not submitted:
        if row:
            db.session.delete(row)
        db.session.commit()
        return
    if row:
        row.value = submitted
    else:
        db.session.add(SystemSetting(key=EMBED_CORS_SETTING_KEY, value=submitted))
    db.session.commit()


def apply_embed_cors_to_response(response):
    """Attach CORS headers for ``/api/embed/*`` when Origin matches policy."""
    if not request.path.startswith("/api/embed"):
        return response
    origin = request.headers.get("Origin")
    raw = get_embed_cors_effective_raw()
    if raw == "*":
        response.headers["Access-Control-Allow-Origin"] = "*"
    elif origin:
        allowed = {x.strip() for x in raw.split(",") if x.strip()}
        if origin in allowed:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers.add("Vary", "Origin")
    response.headers.setdefault("Access-Control-Allow-Methods", ALLOW_METHODS)
    response.headers.setdefault("Access-Control-Allow-Headers", ALLOW_HEADERS)
    response.headers.setdefault("Access-Control-Max-Age", MAX_AGE)
    return response


def handle_embed_cors_preflight():
    """Respond to browser OPTIONS preflight for embed API routes."""
    if request.method != "OPTIONS":
        return None
    if not request.path.startswith("/api/embed"):
        return None
    resp = make_response("", 204)
    return apply_embed_cors_to_response(resp)
