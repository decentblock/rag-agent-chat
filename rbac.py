"""RBAC helpers and Flask decorators."""

from __future__ import annotations

from functools import wraps
from typing import TYPE_CHECKING

from flask import g, jsonify

if TYPE_CHECKING:
    from models import User


def iter_permission_codes(user: User):
    for role in user.roles:
        for perm in role.permissions:
            yield perm.code


def user_has_permission(user: User | None, code: str) -> bool:
    if user is None or not user.is_active:
        return False
    for p in iter_permission_codes(user):
        if p == "*" or p == code:
            return True
    return False


def roles_include_users_manage(roles) -> bool:
    """True if any assigned role grants wildcard or ``users:manage``."""
    for role in roles:
        for perm in getattr(role, "permissions", []) or []:
            code = getattr(perm, "code", "") or ""
            if code == "*" or code == "users:manage":
                return True
    return False


def permission_required(code: str):
    """Require authenticated principal with permission (use after login_required)."""

    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not user_has_permission(getattr(g, "current_user", None), code):
                return jsonify({"error": "Forbidden", "required_permission": code}), 403
            return view(*args, **kwargs)

        return wrapped

    return decorator
