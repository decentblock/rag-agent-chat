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


def get_embeddings_for_openai(api_key: str, base_url: str | None = None) -> OpenAIEmbeddings:
    """Embeddings client using caller-supplied OpenAI-compatible credentials."""
    opts: dict = {
        "api_key": api_key,
        "model": EMEDDING_MODEL,
    }
    eff_base = (base_url or "").strip()
    if eff_base:
        opts["base_url"] = eff_base
    hc = _openai_http_client()
    if hc is not None:
        opts["http_client"] = hc
    return OpenAIEmbeddings(**opts)


def get_embeddings_for_tenant(tenant_id: str) -> OpenAIEmbeddings:
    from services.tenant_openai_credentials import tenant_openai_runtime_for_id

    key, base = tenant_openai_runtime_for_id(str(tenant_id))
    if key:
        return get_embeddings_for_openai(key, base)
    return get_embeddings()


def get_llm_for_tenant(tenant_id: str) -> ChatOpenAI:
    from services.tenant_openai_credentials import tenant_openai_runtime_for_id

    key, base = tenant_openai_runtime_for_id(str(tenant_id))
    if key:
        return get_llm_for_openai(key, base)
    return get_llm()


def get_llm_for_openai(api_key: str, base_url: str | None = None) -> ChatOpenAI:
    """Chat completion client using caller-supplied OpenAI-compatible credentials."""
    opts: dict = {
        "model": OPENAI_MODEL,
        "temperature": 0,
        "api_key": api_key,
    }
    eff_base = (base_url or "").strip()
    if eff_base:
        opts["base_url"] = eff_base
    hc = _openai_http_client()
    if hc is not None:
        opts["http_client"] = hc
    return ChatOpenAI(**opts)


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