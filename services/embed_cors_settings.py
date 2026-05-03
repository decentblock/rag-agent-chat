"""Embed widget CORS: platform default + per–embed-key origins + optional ``system_settings``."""

from __future__ import annotations

from flask import g, make_response, request

from config import EMBED_CORS_ORIGINS
from extensions import db
from models import ApiKey, SystemSetting
from services.embed_key_service import parse_allowed_embed_origins

EMBED_CORS_SETTING_KEY = "embed_cors_origins"

ALLOW_METHODS = "GET, POST, OPTIONS"
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


def _global_origin_pool(raw: str) -> set[str]:
    if (raw or "").strip() == "*":
        return set()
    return {x.strip().rstrip("/") for x in raw.split(",") if x.strip()}


def union_preflight_origin_pool() -> set[str]:
    """Origins allowed by platform settings plus every active embed key’s explicit list."""
    raw_global = get_embed_cors_effective_raw()
    pool = _global_origin_pool(raw_global)
    for row in ApiKey.query.filter_by(is_active=True).all():
        for o in parse_allowed_embed_origins(row):
            pool.add(o.rstrip("/"))
    return pool


def resolve_embed_preflight_allow_origin() -> tuple[bool, str | None]:
    """OPTIONS: ``(use_star, reflected_origin)``. ``use_star`` True → echo ``*``."""
    origin = (request.headers.get("Origin") or "").strip().rstrip("/")
    raw_global = get_embed_cors_effective_raw()
    if raw_global.strip() == "*":
        return True, "*"
    if not origin:
        return False, None
    pool = union_preflight_origin_pool()
    if origin in pool:
        return False, origin
    return False, None


def validate_embed_post_origin(origin_header: str | None, api_row: ApiKey) -> bool:
    """Check Origin for this key / platform fallback; set ``g`` flags for ``after_request``."""
    raw_global = get_embed_cors_effective_raw()
    key_origins = parse_allowed_embed_origins(api_row)

    if key_origins:
        origin_norm = (origin_header or "").strip().rstrip("/")
        if origin_norm and origin_norm in key_origins:
            g.embed_cors_reflect_origin = origin_norm
            return True
        return False

    if raw_global.strip() == "*":
        g.embed_cors_reflect_star = True
        return True

    origin_norm = (origin_header or "").strip().rstrip("/")
    pool = _global_origin_pool(raw_global)
    if origin_norm and origin_norm in pool:
        g.embed_cors_reflect_origin = origin_norm
        return True
    return False


def apply_embed_cors_to_response(response):
    """CORS headers for ``/api/embed/*`` (OPTIONS union preflight; POST uses ``g``)."""
    if not request.path.startswith("/api/embed"):
        return response

    acao: str | None = None
    if request.method == "OPTIONS":
        use_star, refl = resolve_embed_preflight_allow_origin()
        acao = "*" if use_star else refl
    else:
        if getattr(g, "embed_cors_reflect_star", False):
            acao = "*"
        elif getattr(g, "embed_cors_reflect_origin", None):
            acao = g.embed_cors_reflect_origin

    if acao:
        response.headers["Access-Control-Allow-Origin"] = acao
        if acao != "*":
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
