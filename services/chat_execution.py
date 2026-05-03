"""Shared chat execution for session-authenticated /chat and embed API."""

from __future__ import annotations

from typing import Any

from agents import AgentInvocationContext, AgentRunInput
from agents.registry import registry as agent_registry

from agent_catalog import validate_agent_choice

# Keys stored in preference/config JSON for UI only — never passed into agent workflows.
_UI_ONLY_AGENT_CONFIG_KEYS = frozenset({"agent_display_names"})


def _agent_config_for_invoke(cfg: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(cfg, dict):
        return {}
    return {k: v for k, v in cfg.items() if k not in _UI_ONLY_AGENT_CONFIG_KEYS}


def run_chat_turn(
    *,
    tenant_id: str,
    user_id: str,
    session_id: str,
    agent_id: str,
    merged_cfg: dict[str, Any],
    allowed_collection_ids: tuple[str, ...],
    chat_message: str,
    llm_route: str = "platform_llm",
    llm_config_ref: Any = None,
    client_hint: Any = None,
):
    ok_agent, agent_err = validate_agent_choice(agent_id)
    if not ok_agent:
        return None, agent_err

    if not (chat_message or "").strip():
        return None, "chat_message is required"

    invoke_cfg = _agent_config_for_invoke(merged_cfg)

    ctx = AgentInvocationContext(
        tenant_id=str(tenant_id),
        user_id=str(user_id),
        session_id=str(session_id),
        allowed_collection_ids=allowed_collection_ids,
        llm_route=str(llm_route),
        llm_config_ref=llm_config_ref,
        metadata={
            "agent_config": invoke_cfg,
            "payload_hint": client_hint,
        },
    )
    inp = AgentRunInput(raw_prompt=chat_message.strip())
    try:
        result = agent_registry.invoke(agent_id, ctx, inp)
    except KeyError:
        return None, f"Unknown agent_id: {agent_id}"

    return (
        {
            "answer": result.text,
            "citations": result.citations,
            "agent_id": agent_id,
            "usage": result.usage,
            "extra": result.extra,
        },
        None,
    )
