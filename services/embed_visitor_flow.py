"""Embed widget public config and visitor lead validation."""

from __future__ import annotations

import re

from extensions import db
from logging_setup import logger
from models import EmbedVisitorLead, Tenant


def tenant_widget_public_dict(tenant: Tenant) -> dict:
    collect = bool(getattr(tenant, "embed_collect_visitor_contact", False))
    return {
        "agent_display_name": (tenant.embed_agent_display_name or "").strip() or None,
        "welcome_message": (tenant.embed_welcome_message or "").strip() or None,
        "collect_visitor_contact": collect,
    }


def _basic_email_ok(email: str) -> bool:
    if "@" not in email or email.startswith("@") or email.endswith("@"):
        return False
    return bool(re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", email))


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


_EMAIL_IN_TEXT = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def _extract_phone_candidate(text: str) -> str | None:
    """Best-effort phone substring for chat replies (not global validation)."""
    if not text or not str(text).strip():
        return None
    patterns = [
        r"\+\d{10,14}\b",
        r"\(?\d{3}\)[-.\s]?\d{3}[-.\s]?\d{4}\b",
        r"\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b",
        r"\b\d{10}\b",
        r"\b\d{11}\b",
    ]
    for p in patterns:
        m = re.search(p, text)
        if not m:
            continue
        s = m.group(0).strip()
        digits = re.sub(r"\D", "", s)
        if len(digits) >= 10:
            return s[:64]
    return None


def try_persist_visitor_lead_from_embed_chat(
    *,
    tenant_id: str,
    embed_key_id: str,
    visitor_session: str,
    chat_message: str,
) -> str | None:
    """
    If the visitor message looks like a contact follow-up (email and/or phone),
    persist to embed_visitor_leads and return a short acknowledgment for the chat UI.

    Returns None when no contact payload detected or validation fails (caller runs normal RAG).
    """
    raw = (chat_message or "").strip()
    if len(raw) > 400:
        return None

    em = _EMAIL_IN_TEXT.search(raw)
    email = em.group(0).strip() if em else ""
    if email and not _basic_email_ok(email):
        return None

    without_email = _EMAIL_IN_TEXT.sub(" ", raw)
    phone_guess = _extract_phone_candidate(without_email) or _extract_phone_candidate(raw)
    phone = (phone_guess or "").strip()

    name_candidate = without_email
    if phone_guess:
        name_candidate = name_candidate.replace(phone_guess, " ")
    name_candidate = " ".join(name_candidate.split()).strip()
    name = name_candidate[:255] if len(name_candidate) >= 2 else ""

    if not email and not phone:
        return None

    display_name = name if name else "Chat visitor"

    body = {
        "visitor_session": visitor_session,
        "name": display_name,
        "email": email,
        "phone": phone,
        "message": raw[:2000] if raw else None,
    }
    cleaned, verr = validate_visitor_lead_payload(body)
    if verr or not cleaned:
        return None

    try:
        persist_visitor_lead(
            tenant_id=str(tenant_id),
            embed_key_id=str(embed_key_id),
            cleaned=cleaned,
        )
    except Exception:
        logger.exception("visitor lead persist from embed chat failed")
        return None

    return (
        "Thank you — we have saved your contact details. Someone from the team will reach out soon."
    )


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
