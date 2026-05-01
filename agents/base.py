"""
Agent contracts for multi-tenant SaaS.

Agents are versioned, registered units of behaviour invoked with an explicit
tenant-scoped context. All future agents should implement Agent and register
via agents.registry.AgentRegistry.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class AgentInvocationContext:
    """Immutable per-request context — must be built after authn/authz."""

    tenant_id: str
    user_id: str
    session_id: str
    # Collections the caller is allowed to query (already intersected with RBAC/embed policy).
    allowed_collection_ids: tuple[str, ...] = ()
    # "tenant_llm" | "platform_llm" plus optional provider hints (filled by routing layer).
    llm_route: str = "platform_llm"
    llm_config_ref: str | None = None  # e.g. secret ref id for BYOK
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentRunInput:
    """Normalized input to an agent run."""

    messages: list[dict[str, str]] | None = None
    raw_prompt: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentRunResult:
    """Normalized output; extend `extra` for tool calls, citations, usage."""

    text: str
    citations: list[str] = field(default_factory=list)
    usage: dict[str, Any] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class Agent(Protocol):
    """Pluggable agent — implement in agents/builtin/ or a dedicated plugin package."""

    agent_id: str
    version: str
    description: str

    def run(self, ctx: AgentInvocationContext, inp: AgentRunInput) -> AgentRunResult:
        ...
