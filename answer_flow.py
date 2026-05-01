from rag_flow import run_rag_only


def get_answer(question: str, session_id: str) -> str:
    return run_rag_only(question, session_id)