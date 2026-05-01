"""
Marketplace catalog: metadata for agents shown on landing + in-app.

Runtime registry (agents.registry) defines what can execute; catalog defines
presentation, onboarding fields, and roadmap entries (available=False).
"""

from __future__ import annotations

from typing import Any

from agents.registry import registry


_COMMON_HINT_FIELDS: list[dict[str, Any]] = [
    {
        "key": "user_instructions",
        "label": "Extra instructions",
        "type": "textarea",
        "placeholder": "Tone, format, or constraints (bullets, brevity, audience).",
        "help": "Merged into every chat turn for this agent.",
    },
    {
        "key": "response_language",
        "label": "Preferred language",
        "type": "text",
        "placeholder": "e.g. English",
        "help": "Hint for the model; enforcement depends on LLM settings.",
    },
]


# Each entry: agent_id must match registry id when available=True.
MARKETPLACE_AGENTS: list[dict[str, Any]] = [
    {
        "agent_id": "rag_document_qa",
        "name": "Document Q&A",
        "tagline": "Grounded answers from your tenant knowledge base",
        "description": (
            "Retrieves relevant chunks across allowed collections, cites sources, "
            "and refuses when evidence is missing. Best for policies, manuals, and support docs."
        ),
        "category": "Knowledge",
        "icon": "layers",
        "available": True,
        "badge": "Popular",
        "config_fields": _COMMON_HINT_FIELDS,
    },
    {
        "agent_id": "research_synthesizer",
        "name": "Research synthesizer",
        "tagline": "Multi-source summaries with balanced framing",
        "description": (
            "Uses the same retrieval pipeline as Document Q&A but steers the model toward "
            "comparing sources, noting gaps, and keeping language neutral—ideal for briefs and prep."
        ),
        "category": "Research",
        "icon": "search",
        "available": True,
        "badge": "Live",
        "config_fields": _COMMON_HINT_FIELDS
        + [
            {
                "key": "synthesis_focus",
                "label": "Synthesis focus",
                "type": "text",
                "placeholder": "e.g. risks only · timeline · stakeholder impacts",
                "help": "Optional lens applied on top of the default research workflow.",
            },
        ],
    },
    {
        "agent_id": "support_router",
        "name": "Support router",
        "tagline": "Intent-aware replies from approved knowledge",
        "description": (
            "Infers intent from the user message and drafts macros or next steps using only "
            "retrieved snippets—call out when the KB does not cover the case."
        ),
        "category": "Support",
        "icon": "lifebuoy",
        "available": True,
        "badge": "Live",
        "config_fields": _COMMON_HINT_FIELDS
        + [
            {
                "key": "brand_voice",
                "label": "Brand voice",
                "type": "text",
                "placeholder": "e.g. concise, empathetic, no emojis",
                "help": "Short reminder wired into the support workflow block.",
            },
        ],
    },
    {
        "agent_id": "sql_analyst",
        "name": "SQL analyst",
        "tagline": "Read-only SELECT suggestions from documented schema",
        "description": (
            "Grounds proposed queries in indexed schema docs and policies. Emits SELECT-only "
            "SQL with disclaimers; execution against your warehouse is not performed here."
        ),
        "category": "Data",
        "icon": "table",
        "available": True,
        "badge": "Live",
        "config_fields": _COMMON_HINT_FIELDS
        + [
            {
                "key": "sql_dialect",
                "label": "SQL dialect",
                "type": "text",
                "placeholder": "e.g. PostgreSQL, BigQuery, Snowflake",
                "help": "Shapes syntax hints; tables/columns must still appear in retrieved docs.",
            },
            {
                "key": "schema_context",
                "label": "Schema notes",
                "type": "textarea",
                "placeholder": "Optional: key tables or naming conventions (also ingest these as documents for best results).",
                "help": "Merged into the workflow context when provided.",
            },
        ],
    },
]


def list_marketplace_payload() -> list[dict[str, Any]]:
    """Public-safe list merged with live registry versions."""
    out = []
    for row in MARKETPLACE_AGENTS:
        entry = {**row}
        rid = str(entry["agent_id"]).strip().lower()
        impl = registry.get(rid)
        entry["registered_version"] = impl.version if impl else None
        entry["installed"] = impl is not None and bool(entry.get("available"))
        out.append(entry)
    return out


def get_catalog_entry(agent_id: str) -> dict[str, Any] | None:
    aid = agent_id.strip().lower()
    for row in MARKETPLACE_AGENTS:
        if str(row["agent_id"]).strip().lower() == aid:
            return row
    return None


def validate_agent_choice(agent_id: str) -> tuple[bool, str | None]:
    """Returns (ok, error_message)."""
    aid = agent_id.strip().lower()
    cat = get_catalog_entry(aid)
    if not cat:
        return False, "Unknown agent"
    if not cat.get("available"):
        return False, "Agent not available yet"
    if registry.get(aid) is None:
        return False, "Agent not installed on this deployment"
    return True, None
