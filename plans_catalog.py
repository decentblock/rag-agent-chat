"""Subscription plans: limits enforced per tenant (registration + runtime)."""

from __future__ import annotations

from typing import Any

# Ordered list for registration UI / API.
PLAN_ORDER: list[str] = ["starter", "growth", "enterprise"]

# None for a numeric limit means unlimited.
PLANS: dict[str, dict[str, Any]] = {
    "starter": {
        "label": "Starter",
        "description": "Single workflow, small team, tight quotas.",
        "max_users": 5,
        "monthly_chat_quota": 500,
        "max_collections": 3,
        "max_embed_keys": 1,
        # Only these marketplace agents may run / be saved as preference / embed default.
        "allowed_agent_ids": ["rag_document_qa"],
    },
    "growth": {
        "label": "Growth",
        "description": "Full agent marketplace, higher limits.",
        "max_users": 25,
        "monthly_chat_quota": 5000,
        "max_collections": 20,
        "max_embed_keys": 5,
        "allowed_agent_ids": None,  # None = all installed catalog agents
    },
    "enterprise": {
        "label": "Enterprise",
        "description": "No preset caps (fair use); all agents.",
        "max_users": None,
        "monthly_chat_quota": None,
        "max_collections": None,
        "max_embed_keys": None,
        "allowed_agent_ids": None,
    },
}


def normalize_plan_slug(slug: str | None) -> str:
    s = (slug or "").strip().lower()
    if s not in PLANS:
        return "starter"
    return s


def get_plan_limits(plan_slug: str) -> dict[str, Any]:
    return PLANS.get(normalize_plan_slug(plan_slug), PLANS["starter"])


def list_plans_public_payload() -> list[dict[str, Any]]:
    """Safe for unauthenticated /register UI (no secrets)."""
    out = []
    for slug in PLAN_ORDER:
        row = PLANS[slug]
        allowed = row.get("allowed_agent_ids")
        out.append(
            {
                "slug": slug,
                "label": row["label"],
                "description": row["description"],
                "max_users": row.get("max_users"),
                "monthly_chat_quota": row.get("monthly_chat_quota"),
                "max_collections": row.get("max_collections"),
                "max_embed_keys": row.get("max_embed_keys"),
                "agent_scope": "subset" if allowed else "all",
                "allowed_agent_ids": allowed,
            }
        )
    return out
