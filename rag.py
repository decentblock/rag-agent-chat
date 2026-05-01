from pathlib import Path

from langchain_community.vectorstores import Chroma
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnableLambda, RunnablePassthrough

from config import  SEARCH_K,CHROMA_DB_DIR,DEFAULT_COLLECTION_NAME
from clients import get_embeddings, get_llm
from memory_store import get_memory



def get_chroma_db_path() -> str:
    Path(CHROMA_DB_DIR).mkdir(parents=True, exist_ok=True)
    return CHROMA_DB_DIR


def format_doc(doc):
    return "\n\n".join([
        f"{d.metadata.get('source', '?')}\n{d.page_content}"
        for d in doc
    ])


def format_doc_bound_tool_flow(doc) -> str:
    chunks = []

    for idx, doc in enumerate(doc, start=1):
        text = (doc.page_content or "").strip()
        source = ""

        if getattr(doc, "metadata", None):
            source = doc.metadata.get("source", "")

        prefix = f"[Chunk {idx}]"
        if source:
            prefix += f"[Source: {source}]"

        chunks.append(f"{prefix}\n{text}")

    return "\n\n".join(chunks).strip()






def build_vectorstore_from_DB(
    embedding_function,
    collection_name: str = DEFAULT_COLLECTION_NAME,
):
    return Chroma(
        collection_name=collection_name,
        persist_directory=get_chroma_db_path(),
        embedding_function=embedding_function,
    )


def make_retriever(vectorstore, module=None, k: int = SEARCH_K):
    search_kwargs = {
        "k": k,
        "fetch_k": 20,
        "lambda_mult": 0.5,
    }

    if module:
        search_kwargs["filter"] = {"module": module}

    retriever = vectorstore.as_retriever(
        search_type="mmr",
        search_kwargs=search_kwargs,
    )

    return retriever


def format_docs(docs) -> str:
    chunks = []

    for idx, doc in enumerate(docs, start=1):
        text = (doc.page_content or "").strip()
        source = ""

        if getattr(doc, "metadata", None):
            source = doc.metadata.get("source", "")

        prefix = f"[Chunk {idx}]"
        if source:
            prefix += f" [Source: {source}]"

        chunks.append(f"{prefix}\n{text}")

    return "\n\n".join(chunks).strip()


def make_rag_prompt() -> ChatPromptTemplate:
    system_message = """
You are a careful assistant.

Answer ONLY from the provided GUIDELINES.
Do not use outside knowledge.
Do not guess.
Do not repeat the user's question.

If the answer is not found in the GUIDELINES, respond exactly:
i dont have enough information in the provided documents
""".strip()

    human_message = """
GUIDELINES:
{guidelines}

QUESTION:
{question}
""".strip()

    return ChatPromptTemplate.from_messages([
        ("system", system_message),
        MessagesPlaceholder(variable_name="history"),
        ("human", human_message),
    ])


def build_rag_chain(llm, retriever, memory):
    prompt = make_rag_prompt()

    extractor = RunnableLambda(
        lambda x: x["question"]
        if isinstance(x, dict) and "question" in x
        else (x if isinstance(x, str) else str(x))
    )

    guidelines_lambda = extractor | retriever | RunnableLambda(format_doc)

    chain = (
        {
            "guidelines": guidelines_lambda,
            "question": RunnablePassthrough(),
            "history": RunnableLambda(
                lambda x: x.get("history", []) if isinstance(x, dict) else []
            ),
        }
        | prompt
        | llm
    )

    return chain


def build_rag_chain_with_memory(llm, retriever, memory):
    prompt = make_rag_prompt()

    extractor = RunnableLambda(
        lambda x: x["question"]
        if isinstance(x, dict) and "question" in x
        else (x if isinstance(x, str) else str(x))
    )

    guidelines_lambda = extractor | retriever | RunnableLambda(format_doc)

    chain = (
        {
            "guidelines": guidelines_lambda,
            "question": RunnablePassthrough(),
            "history": RunnableLambda(
                lambda x: memory.load_memory_variables({}).get("history", [])
                if isinstance(x, dict)
                else []
            ),
        }
        | prompt
        | llm
    )

    return chain


def run_chain_with_memory(chain, question, session_id):
    memory = get_memory(session_id=session_id)

    memory_vars = memory.load_memory_variables({})
    history = memory_vars.get("history", [])

    result = chain.invoke({
        "question": question,
        "history": history,
    })

    memory.save_context(
        {"input": question},
        {"output": getattr(result, "content", str(result))},
    )

    return result




def get_retriever(module=None):
    embeddings = get_embeddings()
    vectorstore = build_vectorstore_from_DB(embeddings)

    retriever = make_retriever(vectorstore, module)
    return retriever


def get_rag_chain(module=None):
    llm = get_llm()
    retriever = get_retriever(module)
    memory = get_memory("default-session")

    rag_chain = build_rag_chain_with_memory(llm, retriever, memory)
    return rag_chain