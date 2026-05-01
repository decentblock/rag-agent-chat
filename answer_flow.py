from rag_flow import run_rag_only


def get_answer(
    question: str,
    session_id: str,
    tenant_id: str,
    chroma_collection_names: list[str],
):
    return run_rag_only(question, session_id, tenant_id, chroma_collection_names)
