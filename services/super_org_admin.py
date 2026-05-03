"""Platform superuser operations across tenants (organisations)."""

from __future__ import annotations

import json
from typing import Any

from werkzeug.security import generate_password_hash

from extensions import db
from models import Tenant, User
from plans_catalog import PLANS, PLAN_ORDER, get_plan_limits, normalize_plan_slug
from services.tenant_access import (
    REGISTRATION_APPROVED,
    REGISTRATION_PENDING_REVIEW,
    REGISTRATION_REJECTED,
)


def _tenant_is_active(tenant: Tenant) -> bool:
    return bool(getattr(tenant, "is_active", True))


def list_tenants_payload() -> list[dict[str, Any]]:
    rows = Tenant.query.order_by(Tenant.slug.asc()).all()
    out = []
    for t in rows:
        n_users = User.query.filter_by(tenant_id=t.id).count()
        out.append(
            {
                "id": t.id,
                "name": t.name,
                "slug": t.slug,
                "plan_slug": t.plan_slug,
                "is_active": _tenant_is_active(t),
                "registration_status": (
                    getattr(t, "registration_status", None) or "approved"
                ).strip().lower(),
                "users_count": n_users,
                "created_at": t.created_at.isoformat() + "Z" if t.created_at else None,
            }
        )
    return out


def _parse_allowed_override(raw: str | None) -> list[str] | None:
    """Return None if unset (caller uses plan); list if explicit override (may be empty)."""
    if raw is None or not str(raw).strip():
        return None
    try:
        arr = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(arr, list):
        return None
    return [str(x).strip().lower() for x in arr if str(x).strip()]


def tenant_detail_payload(tenant_id: str) -> dict[str, Any] | None:
    t = Tenant.query.filter_by(id=tenant_id).first()
    if not t:
        return None
    slug = normalize_plan_slug(t.plan_slug)
    plan_limits = get_plan_limits(slug)
    ov = _parse_allowed_override(getattr(t, "allowed_agent_ids_json", None))
    reg = (getattr(t, "registration_status", None) or "approved").strip().lower()
    return {
        "tenant": {
            "id": t.id,
            "name": t.name,
            "slug": t.slug,
            "plan_slug": t.plan_slug,
            "is_active": _tenant_is_active(t),
            "registration_status": reg,
            "billing_contact_email": getattr(t, "billing_contact_email", None),
            "payment_provider_customer_id": getattr(t, "payment_provider_customer_id", None),
            "notes": getattr(t, "notes", None),
            "allowed_agent_ids_override": ov,
            "has_agent_override": getattr(t, "allowed_agent_ids_json", None)
            and str(getattr(t, "allowed_agent_ids_json", "") or "").strip() != "",
        },
        "plan_allowed_agent_ids": plan_limits.get("allowed_agent_ids"),
        "plan_options": [
            {
                "slug": slug_opt,
                "label": PLANS[slug_opt]["label"],
                "allowed_agent_ids": get_plan_limits(slug_opt).get("allowed_agent_ids"),
            }
            for slug_opt in PLAN_ORDER
        ],
    }


def patch_tenant_super(tenant_id: str, body: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    t = Tenant.query.filter_by(id=tenant_id).first()
    if not t:
        return None, "Tenant not found"

    if "name" in body:
        name = str(body.get("name") or "").strip()
        if not name:
            return None, "name cannot be empty"
        t.name = name[:255]

    if "plan_slug" in body:
        slug = normalize_plan_slug(str(body.get("plan_slug") or ""))
        if slug not in PLANS:
            return None, "Unknown plan_slug"
        t.plan_slug = slug

    if "is_active" in body:
        t.is_active = bool(body["is_active"])

    if "billing_contact_email" in body:
        em = str(body.get("billing_contact_email") or "").strip()
        t.billing_contact_email = em[:255] if em else None

    if "payment_provider_customer_id" in body:
        pid = str(body.get("payment_provider_customer_id") or "").strip()
        t.payment_provider_customer_id = pid[:255] if pid else None

    if "notes" in body:
        notes = str(body.get("notes") or "").strip()
        t.notes = notes if notes else None

    if "allowed_agent_ids" in body:
        val = body.get("allowed_agent_ids")
        if val is None:
            t.allowed_agent_ids_json = None
        elif isinstance(val, list):
            cleaned = [str(x).strip().lower() for x in val if str(x).strip()]
            eff_slug = normalize_plan_slug(t.plan_slug)
            limits = get_plan_limits(eff_slug)
            plan_allowed = limits.get("allowed_agent_ids")
            if plan_allowed is not None:
                ps = {str(x).strip().lower() for x in plan_allowed}
                cleaned = [x for x in cleaned if x in ps]
            t.allowed_agent_ids_json = json.dumps(cleaned)
        else:
            return None, "allowed_agent_ids must be an array or null"

    if "registration_status" in body:
        raw = str(body.get("registration_status") or "").strip().lower()
        if raw not in (
            REGISTRATION_APPROVED,
            REGISTRATION_PENDING_REVIEW,
            REGISTRATION_REJECTED,
        ):
            return None, "registration_status must be approved, pending_review, or rejected"
        t.registration_status = raw
        if raw == REGISTRATION_REJECTED:
            t.is_active = False
        elif raw == REGISTRATION_APPROVED:
            t.is_active = True
        elif raw == REGISTRATION_PENDING_REVIEW:
            t.is_active = True

    db.session.commit()
    detail = tenant_detail_payload(tenant_id)
    return detail or {}, None


def list_users_for_tenant(tenant_id: str) -> list[dict[str, Any]] | None:
    if not Tenant.query.filter_by(id=tenant_id).first():
        return None
    users = User.query.filter_by(tenant_id=tenant_id).order_by(User.username.asc()).all()
    return [
        {
            "id": u.id,
            "username": u.username,
            "email": u.email,
            "is_active": u.is_active,
            "is_superuser": bool(getattr(u, "is_superuser", False)),
            "roles": [r.name for r in u.roles],
        }
        for u in users
    ]


_SUPER_PASSWORD_MIN_LEN = 8


def patch_user_super(user_id: str, body: dict[str, Any], actor_user_id: str) -> tuple[dict[str, Any] | None, str | None]:
    user = User.query.filter_by(id=user_id).first()
    if not user:
        return None, "User not found"

    pwd_changed = False
    if "password" in body:
        pw = body.get("password")
        if pw is None:
            return None, "password is required when present"
        if not isinstance(pw, str):
            return None, "password must be a string"
        pw = pw.strip()
        if len(pw) < _SUPER_PASSWORD_MIN_LEN:
            return None, f"password must be at least {_SUPER_PASSWORD_MIN_LEN} characters"
        user.password_hash = generate_password_hash(pw)
        pwd_changed = True

    if "is_active" in body:
        active = bool(body["is_active"])
        if not active and user.id == actor_user_id:
            return None, "Cannot disable your own account"
        user.is_active = active

    db.session.commit()
    return (
        {
            "id": user.id,
            "tenant_id": user.tenant_id,
            "username": user.username,
            "is_active": user.is_active,
            "password_updated": pwd_changed,
        },
        None,
    )
