"""Marketplace agents sharing document-grounded RAG with distinct workflow prompts."""

from __future__ import annotations

from ..base import AgentInvocationContext, AgentRunInput, AgentRunResult
from .rag_shared import run_tenant_rag


def _cfg(ctx: AgentInvocationContext) -> dict:
    raw = ctx.metadata.get("agent_config") if isinstance(ctx.metadata, dict) else {}
    return raw if isinstance(raw, dict) else {}


_WORKFLOW_RESEARCH_BASE = (
    "Act as a research synthesizer. Use only the retrieved document excerpts. "
    "Produce a neutral summary that reconciles agreements and tensions across sources. "
    "Call out uncertainty where evidence is thin. Surface citations implicitly via "
    "the retrieval layer; reference document themes explicitly when helpful."
)

_WORKFLOW_SUPPORT_BASE = (
    "Act as a support routing assistant. Infer likely customer intent from the message. "
    "Suggest a concise reply macro or next-step checklist grounded strictly in the "
    "retrieved knowledge base (approved snippets, policies, FAQs). "
    "If the KB lacks coverage, say what is missing and recommend escalation paths "
    "without inventing policy."
)

_WORKFLOW_SQL_BASE = (
    "Act as a read-only SQL analyst. Propose SELECT-only queries (no INSERT/UPDATE/DELETE). "
    "Ground table and column names in the retrieved documentation only—do not invent schema. "
    "Prefix each SQL block with -- READ ONLY SUGGESTION. "
    "Explain assumptions briefly. This deployment does not execute SQL against a warehouse."
)


def _research_block(ctx: AgentInvocationContext) -> str:
    parts = [_WORKFLOW_RESEARCH_BASE]
    focus = str(_cfg(ctx).get("synthesis_focus") or "").strip()
    if focus:
        parts.append(f"Pay particular attention to: {focus}")
    return " ".join(parts)


def _support_block(ctx: AgentInvocationContext) -> str:
    parts = [_WORKFLOW_SUPPORT_BASE]
    voice = str(_cfg(ctx).get("brand_voice") or "").strip()
    if voice:
        parts.append(f"Match this voice: {voice}")
    return " ".join(parts)


def _sql_block(ctx: AgentInvocationContext) -> str:
    cfg = _cfg(ctx)
    parts = [_WORKFLOW_SQL_BASE]
    dialect = str(cfg.get("sql_dialect") or "").strip()
    if dialect:
        parts.append(f"Target SQL dialect: {dialect}.")
    schema = str(cfg.get("schema_context") or "").strip()
    if schema:
        parts.append(f"Additional schema context from operator (verify against retrieved docs): {schema}")
    return " ".join(parts)


class ResearchSynthesizerAgent:
    agent_id = "research_synthesizer"
    version = "1.0.0"
    description = "Multi-source synthesis with citations over tenant documents."

    def run(self, ctx: AgentInvocationContext, inp: AgentRunInput) -> AgentRunResult:
        return run_tenant_rag(
            ctx,
            inp,
            workflow_block=_research_block(ctx),
            agent_id_for_extra=self.agent_id,
        )


class SupportRouterAgent:
    agent_id = "support_router"
    version = "1.0.0"
    description = "Intent-aware support suggestions grounded in tenant snippets and policies."

    def run(self, ctx: AgentInvocationContext, inp: AgentRunInput) -> AgentRunResult:
        return run_tenant_rag(
            ctx,
            inp,
            workflow_block=_support_block(ctx),
            agent_id_for_extra=self.agent_id,
        )


class SqlAnalystAgent:
    agent_id = "sql_analyst"
    version = "1.0.0"
    description = "Schema-aware read-only SQL suggestions from documented warehouse context."

    def run(self, ctx: AgentInvocationContext, inp: AgentRunInput) -> AgentRunResult:
        return run_tenant_rag(
            ctx,
            inp,
            workflow_block=_sql_block(ctx),
            agent_id_for_extra=self.agent_id,
        )
