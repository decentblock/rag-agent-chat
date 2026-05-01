"""Enforce per-tenant plan limits (agents, quotas, seats, collections, embed keys)."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from extensions import db
from models import ApiKey, Collection, Tenant, User
from plans_catalog import get_plan_limits, normalize_plan_slug


def _tenant_plan_slug(tenant: Tenant) -> str:
    raw = getattr(tenant, "plan_slug", None)
    return normalize_plan_slug(raw) if raw else "growth"


def resolved_allowed_agent_ids(tenant: Tenant) -> list[str] | None:
    """Effective agent allowlist: plan default, optionally narrowed by tenant JSON override.

    - Plan ``allowed_agent_ids`` is ``None`` → any registered/marketplace agent unless tenant overrides.
    - Tenant ``allowed_agent_ids_json`` unset → use plan rule only.
    - Tenant JSON set → whitelist intersected with plan list when plan has a finite list;
      when plan is unrestricted (``None``), tenant list is used as-is (may be empty = block all).
    """
    slug = _tenant_plan_slug(tenant)
    limits = get_plan_limits(slug)
    plan_allowed = limits.get("allowed_agent_ids")

    raw = getattr(tenant, "allowed_agent_ids_json", None)
    if raw is None or str(raw).strip() == "":
        return plan_allowed

    try:
        arr = json.loads(raw)
        if not isinstance(arr, list):
            return plan_allowed
        tenant_list = [str(x).strip().lower() for x in arr if str(x).strip()]
    except json.JSONDecodeError:
        return plan_allowed

    if plan_allowed is None:
        return tenant_list

    plan_set = {str(x).strip().lower() for x in plan_allowed}
    return [x for x in tenant_list if x in plan_set]


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

    raw_override = getattr(tenant, "allowed_agent_ids_json", None)
    agents_overridden = bool(raw_override and str(raw_override).strip())
    eff_agents = resolved_allowed_agent_ids(tenant)

    return {
        "plan_slug": slug,
        "plan_label": limits.get("label", slug),
        "limits": {
            "max_users": limits.get("max_users"),
            "monthly_chat_quota": quota,
            "max_collections": limits.get("max_collections"),
            "max_embed_keys": limits.get("max_embed_keys"),
            "allowed_agent_ids": eff_agents,
            "agents_overridden_by_tenant": agents_overridden,
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
    allowed = resolved_allowed_agent_ids(tenant)
    aid = agent_id.strip().lower()
    if allowed is None:
        return True, None
    if aid in allowed:
        return True, None
    return (
        False,
        f"Agent '{aid}' is not enabled for this organisation ({limits.get('label')}).",
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
