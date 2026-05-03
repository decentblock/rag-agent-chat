"""Attach tenant-scoped principal to each request."""

from __future__ import annotations

from flask import Flask, g, session

from models import Tenant, User


def register_principal_loader(app: Flask) -> None:
    @app.before_request
    def load_principal() -> None:
        g.current_user = None
        g.tenant = None
        g.registration_pending = False
        uid = session.get("user_id")
        if not uid:
            return
        user = User.query.filter_by(id=uid).first()
        if not user or not user.is_active:
            session.pop("user_id", None)
            return
        tenant = Tenant.query.filter_by(id=user.tenant_id).first()
        if not tenant or not getattr(tenant, "is_active", True):
            session.pop("user_id", None)
            return
        g.registration_pending = False
        st = (getattr(tenant, "registration_status", None) or "approved").strip().lower()
        if st == "pending_review" and not getattr(user, "is_superuser", False):
            g.registration_pending = True
        g.current_user = user
        g.tenant = tenant
