from langchain_classic.memory import ConversationBufferWindowMemory


store: dict[str, ConversationBufferWindowMemory] = {}


def get_memory(session_id: str):
    if session_id not in store:
        store[session_id] = ConversationBufferWindowMemory(
            k=0,
            return_messages=True,
            memory_key="history",
        )
    return store[session_id]