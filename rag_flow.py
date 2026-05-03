from rag import (
    get_rag_chain_for_tenant,
    merged_similarity_documents,
    run_chain_with_memory_tenant,
)
from logging_setup import logger


def run_rag_only(
    question: str,
    session_id: str,
    tenant_id: str,
    chroma_collection_names: list[str],
) -> dict:
    docs = merged_similarity_documents(chroma_collection_names, question)

    logger.info(
        "rag_turn tenant=%s chroma_collections=%s retrieved_chunks=%s",
        tenant_id,
        chroma_collection_names,
        len(docs),
    )
    if not chroma_collection_names:
        logger.warning(
            "rag_turn_no_chroma_collections tenant=%s session_prefix=%s",
            tenant_id,
            (session_id or "")[:48],
        )
    elif not docs:
        logger.warning(
            "rag_turn_empty_retrieval tenant=%s chroma_collections=%s question_len=%s",
            tenant_id,
            chroma_collection_names,
            len(question or ""),
        )

    chain = get_rag_chain_for_tenant(chroma_collection_names, tenant_id, session_id)
    result = run_chain_with_memory_tenant(chain, question, tenant_id, session_id)
    answer = getattr(result, "content", str(result))

    citations: list[str] = []
    seen: set[str] = set()
    for doc in docs:
        metadata = doc.metadata if hasattr(doc, "metadata") else {}
        source = metadata.get("source", "")
        if source and source not in seen:
            citations.append(source)
            seen.add(source)

    return {"answer": answer, "citations": citations}
