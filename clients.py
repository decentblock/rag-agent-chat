from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from config import OPENAI_API_KEY, OPENAI_MODEL,EMEDDING_MODEL



def get_llm() -> ChatOpenAI:

    return ChatOpenAI(
        model=OPENAI_MODEL,
        temperature=0,
        api_key=OPENAI_API_KEY,

    )


def get_embeddings() -> OpenAIEmbeddings:

    return OpenAIEmbeddings(
        api_key=OPENAI_API_KEY,
        model=EMEDDING_MODEL
    )