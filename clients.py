import httpx
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from config import (
    EMEDDING_MODEL,
    OPENAI_API_BASE,
    OPENAI_API_KEY,
    OPENAI_MODEL,
    VERIFY_SSL,
)


def _openai_http_client() -> httpx.Client | None:
    """Return a client only when TLS verification should be disabled (see VERIFY_SSL)."""
    if VERIFY_SSL:
        return None
    return httpx.Client(verify=False)


def get_llm() -> ChatOpenAI:
    opts: dict = {
        "model": OPENAI_MODEL,
        "temperature": 0,
        "api_key": OPENAI_API_KEY,
    }
    if OPENAI_API_BASE:
        opts["base_url"] = OPENAI_API_BASE
    hc = _openai_http_client()
    if hc is not None:
        opts["http_client"] = hc
    return ChatOpenAI(**opts)


def get_embeddings() -> OpenAIEmbeddings:
    opts: dict = {
        "api_key": OPENAI_API_KEY,
        "model": EMEDDING_MODEL,
    }
    if OPENAI_API_BASE:
        opts["base_url"] = OPENAI_API_BASE
    hc = _openai_http_client()
    if hc is not None:
        opts["http_client"] = hc
    return OpenAIEmbeddings(**opts)