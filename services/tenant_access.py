"""Tenant lifecycle gates (registration review, suspension)."""

from __future__ import annotations

from models import Tenant

REGISTRATION_APPROVED = "approved"
REGISTRATION_PENDING_REVIEW = "pending_review"
REGISTRATION_REJECTED = "rejected"


def registration_status(tenant: Tenant | None) -> str:
    raw = getattr(tenant, "registration_status", None) if tenant else None
    s = (raw or REGISTRATION_APPROVED).strip().lower()
    if s in (REGISTRATION_APPROVED, REGISTRATION_PENDING_REVIEW, REGISTRATION_REJECTED):
        return s
    return REGISTRATION_APPROVED


def tenant_embed_public_allowed(tenant: Tenant | None) -> bool:
    """Embed widget endpoints (widget-config, visitor-contact, chat)."""
    if not tenant or not getattr(tenant, "is_active", True):
        return False
    return registration_status(tenant) == REGISTRATION_APPROVED
