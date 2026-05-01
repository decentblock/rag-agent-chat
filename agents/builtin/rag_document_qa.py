"""
Default document-grounded chat agent — tenant + collection scoped retrieval.
"""

from __future__ import annotations

from ..base import AgentInvocationContext, AgentRunInput, AgentRunResult
from .rag_shared import run_tenant_rag


class RagDocumentQaAgent:
    agent_id = "rag_document_qa"
    version = "1.0.0"
    description = "Grounded Q&A over tenant documents via merged Chroma retrieval."

    def run(self, ctx: AgentInvocationContext, inp: AgentRunInput) -> AgentRunResult:
        return run_tenant_rag(
            ctx,
            inp,
            workflow_block="",
            agent_id_for_extra=self.agent_id,
        )
