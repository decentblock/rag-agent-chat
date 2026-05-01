import hmac
from functools import wraps

from flask import g, jsonify, redirect, request, session, url_for


def verify_credentials(username: str, password: str, auth_username: str, auth_password: str) -> bool:
    u = (username or "").strip()
    p = password or ""
    return bool(auth_username and auth_password) and (
        hmac.compare_digest(u, auth_username.strip())
        and hmac.compare_digest(p, auth_password)
    )


def safe_next_path(candidate: str | None) -> str:
    if candidate and candidate.startswith("/") and not candidate.startswith("//"):
        return candidate
    return url_for("dashboard")


def login_required(view):
    """Require authenticated DB user (principal loaded in before_request)."""

    @wraps(view)
    def wrapped(*args, **kwargs):
        if getattr(g, "current_user", None) is not None:
            return view(*args, **kwargs)

        if request.path.startswith("/api/") or request.path in (
            "/chat",
            "/upload-document",
            "/delete-document",
        ):
            return jsonify({"error": "Unauthorized"}), 401

        return redirect(url_for("login_page", next=request.full_path))

    return wrapped
