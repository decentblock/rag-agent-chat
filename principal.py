"""Attach tenant-scoped principal to each request."""

from __future__ import annotations

from flask import Flask, g, session

from models import User


def register_principal_loader(app: Flask) -> None:
    @app.before_request
    def load_principal() -> None:
        g.current_user = None
        g.tenant = None
        uid = session.get("user_id")
        if not uid:
            return
        user = User.query.filter_by(id=uid).first()
        if user and user.is_active:
            g.current_user = user
            g.tenant = user.tenant
