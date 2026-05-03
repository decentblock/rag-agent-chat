"""Tenant-scoped OpenAI credentials (exclusive BYOK for embeddings + chat)."""

from __future__ import annotations

from models import Tenant

from services.embed_openai_credentials import decrypt_openai_api_key, encrypt_openai_api_key


def tenant_openai_runtime_for_id(tenant_id: str) -> tuple[str | None, str | None]:
    """Return (api_key, base_url) when tenant has exclusive OpenAI enabled and a stored key."""
    row = Tenant.query.filter_by(id=str(tenant_id)).first()
    return tenant_openai_runtime(row)


def tenant_openai_runtime(tenant: Tenant | None) -> tuple[str | None, str | None]:
    if tenant is None:
        return None, None
    if not getattr(tenant, "use_exclusive_openai", False):
        return None, None
    plain = decrypt_openai_api_key(getattr(tenant, "openai_api_key_cipher", None))
    if not plain:
        return None, None
    base = getattr(tenant, "openai_api_base", None)
    base_s = (base or "").strip() or None
    return plain, base_s


def encrypt_tenant_openai_key(plaintext: str) -> str:
    return encrypt_openai_api_key(plaintext)
