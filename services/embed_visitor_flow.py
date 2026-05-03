"""Embed widget public config and visitor lead validation."""

from __future__ import annotations

import re

from extensions import db
from models import EmbedVisitorLead, Tenant


def tenant_widget_public_dict(tenant: Tenant) -> dict:
    raw_collect = getattr(tenant, "embed_collect_visitor_contact", None)
    collect = True if raw_collect is None else bool(raw_collect)
    return {
        "agent_display_name": (tenant.embed_agent_display_name or "").strip() or None,
        "welcome_message": (tenant.embed_welcome_message or "").strip() or None,
        "collect_visitor_contact": collect,
    }


def validate_visitor_lead_payload(body: dict) -> tuple[dict | None, str | None]:
    name = str(body.get("name") or "").strip()
    email = str(body.get("email") or "").strip()
    phone = str(body.get("phone") or "").strip()
    message = str(body.get("message") or "").strip() or None
    visitor = str(body.get("visitor_session") or "").strip()[:160]

    if not name or len(name) > 255:
        return None, "name is required (max 255 characters)"
    if not visitor:
        return None, "visitor_session is required"
    if len(email) > 255:
        return None, "email is too long"
    if phone and len(phone) > 64:
        return None, "phone is too long"

    has_phone = bool(phone)
    email_norm = email
    has_email = bool(email_norm)

    if has_email and not _basic_email_ok(email_norm):
        if has_phone:
            email_norm = ""
            has_email = False
        else:
            return None, "email format looks invalid"

    if not has_email and not has_phone:
        return None, "email or phone is required"

    return {
        "name": name,
        "email": email_norm if has_email else "",
        "phone": phone if has_phone else None,
        "initial_message": message,
        "visitor_session": visitor,
    }, None


def _basic_email_ok(email: str) -> bool:
    if "@" not in email or email.startswith("@") or email.endswith("@"):
        return False
    return bool(re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", email))


def persist_visitor_lead(
    *,
    tenant_id: str,
    embed_key_id: str | None,
    cleaned: dict,
) -> EmbedVisitorLead:
    row = EmbedVisitorLead(
        tenant_id=tenant_id,
        embed_key_id=embed_key_id,
        visitor_session=cleaned["visitor_session"],
        name=cleaned["name"],
        email=cleaned["email"] or "",
        phone=cleaned.get("phone"),
        initial_message=cleaned.get("initial_message"),
    )
    db.session.add(row)
    db.session.commit()
    return row
