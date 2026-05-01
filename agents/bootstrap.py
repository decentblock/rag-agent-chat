"""Register built-in agents on startup."""

from __future__ import annotations

from .builtin.rag_document_qa import RagDocumentQaAgent
from .builtin.rag_variants import ResearchSynthesizerAgent, SqlAnalystAgent, SupportRouterAgent
from .registry import registry


def register_builtin_agents(*, replace: bool = False) -> None:
    for agent in (
        RagDocumentQaAgent(),
        ResearchSynthesizerAgent(),
        SupportRouterAgent(),
        SqlAnalystAgent(),
    ):
        registry.register(agent, replace=replace)
