"""Stable physical Chroma collection names per tenant + logical collection."""


def chroma_collection_name(tenant_id: str, collection_id: str) -> str:
    t = tenant_id.replace("-", "").lower()
    c = collection_id.replace("-", "").lower()
    return f"rag_{t}_{c}"
