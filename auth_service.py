"""Database-backed authentication."""

from __future__ import annotations

from werkzeug.security import check_password_hash

from models import Tenant, User


def authenticate_user(tenant_slug: str, username: str, password: str) -> tuple[User | None, str | None]:
    """
    Verify tenant slug + username + password.

    Returns (user, None) on success, or (None, error_code) where error_code is one of:
    invalid_credentials, tenant_suspended, registration_rejected.
    """
    slug = (tenant_slug or "").strip()
    uname = (username or "").strip()
    if not slug or not uname or not password:
        return None, "invalid_credentials"

    tenant = Tenant.query.filter_by(slug=slug).first()
    if not tenant:
        return None, "invalid_credentials"

    user = User.query.filter_by(tenant_id=tenant.id, username=uname).first()
    if not user or not user.is_active or not user.password_hash:
        return None, "invalid_credentials"

    if not check_password_hash(user.password_hash, password):
        return None, "invalid_credentials"

    st = (getattr(tenant, "registration_status", None) or "approved").strip().lower()
    if st not in ("approved", "pending_review", "rejected"):
        st = "approved"

    if not getattr(tenant, "is_active", True):
        if st == "rejected":
            return None, "registration_rejected"
        return None, "tenant_suspended"

    if st == "rejected":
        return None, "registration_rejected"

    return user, None
