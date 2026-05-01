"""Agent registry and contracts — extend via agents.builtin or tenant plugins."""

from .base import (
    Agent,
    AgentInvocationContext,
    AgentRunInput,
    AgentRunResult,
)
from .bootstrap import register_builtin_agents
from .registry import AgentRegistry, registry

__all__ = [
    "Agent",
    "AgentInvocationContext",
    "AgentRunInput",
    "AgentRunResult",
    "AgentRegistry",
    "registry",
    "register_builtin_agents",
]
