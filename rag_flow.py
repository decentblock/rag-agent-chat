from rag import (
    get_rag_chain_for_tenant,
    merged_similarity_documents,
    run_chain_with_memory_tenant,
)


def run_rag_only(
    question: str,
    session_id: str,
    tenant_id: str,
    chroma_collection_names: list[str],
) -> dict:
    docs = merged_similarity_documents(chroma_collection_names, question)
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
