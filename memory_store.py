try:
    from langchain.memory import ConversationBufferWindowMemory
except ImportError:
    from langchain_classic.memory import ConversationBufferWindowMemory  # type: ignore

_store: dict[str, ConversationBufferWindowMemory] = {}


def memory_session_key(tenant_id: str, session_id: str) -> str:
    return f"{tenant_id}:{session_id}"


def get_memory(tenant_id: str, session_id: str) -> ConversationBufferWindowMemory:
    key = memory_session_key(tenant_id, session_id)
    if key not in _store:
        _store[key] = ConversationBufferWindowMemory(
            k=0,
            return_messages=True,
            memory_key="history",
        )
    return _store[key]
