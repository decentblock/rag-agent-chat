"""
Central registry for agents. Thread-safe enough for WSGI multi-process
(use separate registry population per process at startup; DB-backed catalog later).
"""

from __future__ import annotations

import threading

from .base import Agent, AgentInvocationContext, AgentRunInput, AgentRunResult


class AgentRegistry:
    def __init__(self) -> None:
        self._agents: dict[str, Agent] = {}
        self._lock = threading.Lock()

    def register(self, agent: Agent, *, replace: bool = False) -> None:
        key = agent.agent_id.strip().lower()
        if not key:
            raise ValueError("agent_id is required")
        with self._lock:
            if key in self._agents and not replace:
                raise ValueError(f"Agent already registered: {key}")
            self._agents[key] = agent

    def unregister(self, agent_id: str) -> None:
        key = agent_id.strip().lower()
        with self._lock:
            self._agents.pop(key, None)

    def get(self, agent_id: str) -> Agent | None:
        key = agent_id.strip().lower()
        with self._lock:
            return self._agents.get(key)

    def list_agents(self) -> list[dict[str, str]]:
        with self._lock:
            return [
                {
                    "agent_id": a.agent_id,
                    "version": a.version,
                    "description": a.description,
                }
                for a in self._agents.values()
            ]

    def invoke(
        self,
        agent_id: str,
        ctx: AgentInvocationContext,
        inp: AgentRunInput,
    ) -> AgentRunResult:
        agent = self.get(agent_id)
        if agent is None:
            raise KeyError(f"Unknown agent: {agent_id}")
        return agent.run(ctx, inp)


# Process-global registry — populate at app factory startup (see agents.bootstrap).
registry = AgentRegistry()
