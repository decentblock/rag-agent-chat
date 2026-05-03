"""Shared tenant-scoped RAG execution for multiple marketplace agents."""

from __future__ import annotations

from collections_service import list_chroma_physical_names, normalize_collection_filter

from clients import get_llm, get_llm_for_openai, get_llm_for_tenant

from ..base import AgentInvocationContext, AgentRunInput, AgentRunResult


def extract_user_question(inp: AgentRunInput) -> str:
    question = (inp.raw_prompt or "").strip()
    if inp.messages:
        for msg in reversed(inp.messages):
            if msg.get("role") == "user":
                question = (msg.get("content") or "").strip()
                break
    return question


def apply_user_config_hints(question: str, ctx: AgentInvocationContext) -> str:
    cfg = ctx.metadata.get("agent_config") if isinstance(ctx.metadata, dict) else {}
    if not isinstance(cfg, dict):
        cfg = {}
    hints: list[str] = []
    lang = str(cfg.get("response_language") or "").strip()
    instr = str(cfg.get("user_instructions") or "").strip()
    if lang:
        hints.append(f"Prefer responding in {lang}.")
    if instr:
        hints.append(instr)
    if hints:
        return "[Agent preferences]\n" + "\n".join(hints) + "\n\n[User question]\n" + question
    return question


def compose_question(
    ctx: AgentInvocationContext,
    inp: AgentRunInput,
    *,
    workflow_block: str,
) -> str | None:
    raw = extract_user_question(inp)
    if not raw:
        return None
    q = apply_user_config_hints(raw, ctx)
    wb = (workflow_block or "").strip()
    if wb:
        return "[Agent workflow]\n" + wb + "\n\n" + q
    return q


def run_tenant_rag(
    ctx: AgentInvocationContext,
    inp: AgentRunInput,
    *,
    workflow_block: str,
    agent_id_for_extra: str,
) -> AgentRunResult:
    from answer_flow import get_answer

    question = compose_question(ctx, inp, workflow_block=workflow_block)
    if not question:
        return AgentRunResult(text="", citations=[], extra={"error": "empty_input"})

    normalized = normalize_collection_filter(ctx.tenant_id, tuple(ctx.allowed_collection_ids))
    if ctx.allowed_collection_ids and not normalized:
        return AgentRunResult(
            text="",
            citations=[],
            extra={"error": "invalid_collection_scope"},
        )

    chroma_names = list_chroma_physical_names(ctx.tenant_id, normalized)
    meta = ctx.metadata if isinstance(ctx.metadata, dict) else {}
    e_key = meta.get("embed_openai_api_key")
    e_base = meta.get("embed_openai_api_base")
    llm = (
        get_llm_for_openai(str(e_key).strip(), (str(e_base).strip() if e_base else None) or None)
        if e_key and str(e_key).strip()
        else get_llm_for_tenant(str(ctx.tenant_id))
    )
    raw = get_answer(
        question,
        ctx.session_id or ctx.user_id,
        ctx.tenant_id,
        chroma_names,
        llm=llm,
    )

    if isinstance(raw, dict):
        return AgentRunResult(
            text=str(raw.get("answer", "")),
            citations=list(raw.get("citations") or []),
            extra={"agent_id": agent_id_for_extra},
        )
    return AgentRunResult(text=str(raw), citations=[], extra={"agent_id": agent_id_for_extra})
