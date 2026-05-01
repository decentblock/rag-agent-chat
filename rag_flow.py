from rag import get_rag_chain, run_chain_with_memory,get_retriever


def detect_module_from_query(query: str):
    query_lower = query.lower()

    if "hr policies" in query_lower or "hr" in query_lower:
        return "HRPolcies.pdf"

    elif "security policy" in query_lower or "security" in query_lower:
        return "SecurityPolicies.pdf"

    return None


def run_rag_only(question: str, session_id: str) -> str:
    module = detect_module_from_query(question)
    retriever=get_retriever(module)
    docs=retriever.invoke(question)
    chain = get_rag_chain(module)
    result = run_chain_with_memory(chain, question, session_id)
    answer=getattr(result, "content", str(result))
    citations=[]
    seen=set()
    for doc in docs:
        metadata=doc.metadata if hasattr(doc,'meatadata') else {}
        source=metadata.get("source","")
        if source and source not in seen:
            citations.append(source)
            seen.add(source)

    return {
        "answer":answer,
        "citations":citations
    }