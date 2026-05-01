"""Database-backed authentication."""

from __future__ import annotations

from werkzeug.security import check_password_hash

from models import Tenant, User


def authenticate_user(tenant_slug: str, username: str, password: str) -> User | None:
    slug = (tenant_slug or "").strip()
    uname = (username or "").strip()
    if not slug or not uname or not password:
        return None

    tenant = Tenant.query.filter_by(slug=slug).first()
    if not tenant:
        return None
    if not getattr(tenant, "is_active", True):
        return None

    user = User.query.filter_by(tenant_id=tenant.id, username=uname).first()
    if not user or not user.is_active or not user.password_hash:
        return None

    if check_password_hash(user.password_hash, password):
        return user
    return None
