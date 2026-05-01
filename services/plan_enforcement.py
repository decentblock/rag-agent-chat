"""Enforce per-tenant plan limits (agents, quotas, seats, collections, embed keys)."""

from __future__ import annotations

from datetime import datetime, timezone

from extensions import db
from models import ApiKey, Collection, Tenant, User
from plans_catalog import get_plan_limits, normalize_plan_slug


def _tenant_plan_slug(tenant: Tenant) -> str:
    raw = getattr(tenant, "plan_slug", None)
    return normalize_plan_slug(raw) if raw else "growth"


def subscription_payload(tenant: Tenant) -> dict:
    """Dashboard / console JSON."""
    slug = _tenant_plan_slug(tenant)
    limits = get_plan_limits(slug)
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    count = tenant.usage_chat_count or 0
    if tenant.usage_chat_month != month:
        count = 0
    quota = limits.get("monthly_chat_quota")
    active_users = User.query.filter_by(tenant_id=tenant.id, is_active=True).count()
    cols = Collection.query.filter_by(tenant_id=tenant.id).count()
    embed_n = ApiKey.query.filter_by(tenant_id=tenant.id, is_active=True).count()

    return {
        "plan_slug": slug,
        "plan_label": limits.get("label", slug),
        "limits": {
            "max_users": limits.get("max_users"),
            "monthly_chat_quota": quota,
            "max_collections": limits.get("max_collections"),
            "max_embed_keys": limits.get("max_embed_keys"),
            "allowed_agent_ids": limits.get("allowed_agent_ids"),
        },
        "usage": {
            "chat_month": month,
            "chat_count_month": count,
            "users_active": active_users,
            "collections": cols,
            "embed_keys_active": embed_n,
        },
    }


def agent_allowed_on_plan(tenant: Tenant, agent_id: str) -> tuple[bool, str | None]:
    limits = get_plan_limits(_tenant_plan_slug(tenant))
    allowed = limits.get("allowed_agent_ids")
    aid = agent_id.strip().lower()
    if allowed is None:
        return True, None
    if aid in {x.strip().lower() for x in allowed}:
        return True, None
    return (
        False,
        f"Agent '{aid}' is not included in your plan ({limits.get('label')}). Upgrade to unlock more agents.",
    )


def chat_quota_blocked(tenant: Tenant) -> tuple[bool, str | None]:
    limits = get_plan_limits(_tenant_plan_slug(tenant))
    quota = limits.get("monthly_chat_quota")
    if quota is None:
        return False, None
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    count = tenant.usage_chat_count or 0
    if tenant.usage_chat_month != month:
        count = 0
    if count >= quota:
        return (
            True,
            f"Monthly chat quota ({quota}) reached for plan {limits.get('label')}. Upgrade or wait for next billing cycle.",
        )
    return False, None


def record_successful_chat_turn(tenant_id: str) -> None:
    tenant = Tenant.query.filter_by(id=tenant_id).first()
    if not tenant:
        return
    limits = get_plan_limits(_tenant_plan_slug(tenant))
    if limits.get("monthly_chat_quota") is None:
        return
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    if tenant.usage_chat_month != month:
        tenant.usage_chat_month = month
        tenant.usage_chat_count = 0
    tenant.usage_chat_count = (tenant.usage_chat_count or 0) + 1
    db.session.commit()


def check_can_add_user(tenant: Tenant) -> tuple[bool, str | None]:
    limits = get_plan_limits(_tenant_plan_slug(tenant))
    cap = limits.get("max_users")
    if cap is None:
        return True, None
    n = User.query.filter_by(tenant_id=tenant.id, is_active=True).count()
    if n >= cap:
        return False, f"User limit ({cap}) reached for plan {limits.get('label')}."
    return True, None


def check_can_add_collection(tenant: Tenant) -> tuple[bool, str | None]:
    limits = get_plan_limits(_tenant_plan_slug(tenant))
    cap = limits.get("max_collections")
    if cap is None:
        return True, None
    n = Collection.query.filter_by(tenant_id=tenant.id).count()
    if n >= cap:
        return (
            False,
            f"Collection limit ({cap}) reached for plan {limits.get('label')}.",
        )
    return True, None


def check_can_add_embed_key(tenant: Tenant) -> tuple[bool, str | None]:
    limits = get_plan_limits(_tenant_plan_slug(tenant))
    cap = limits.get("max_embed_keys")
    if cap is None:
        return True, None
    n = ApiKey.query.filter_by(tenant_id=tenant.id, is_active=True).count()
    if n >= cap:
        return (
            False,
            f"Embed API key limit ({cap}) reached for plan {limits.get('label')}.",
        )
    return True, None
