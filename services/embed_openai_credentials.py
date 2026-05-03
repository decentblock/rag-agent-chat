"""Encrypt/decrypt per-embed OpenAI API keys at rest (Fernet, key derived from SESSION_SECRET)."""

from __future__ import annotations

import base64
import binascii
import hashlib

from config import SESSION_SECRET


def _fernet():
    try:
        from cryptography.fernet import Fernet
    except ImportError as exc:
        raise RuntimeError(
            "The cryptography package is required to store embed OpenAI keys. "
            "Install dependencies: pip install -r requirements-dev.txt"
        ) from exc

    key = base64.urlsafe_b64encode(hashlib.sha256(SESSION_SECRET.encode("utf-8")).digest())
    return Fernet(key)


def encrypt_openai_api_key(plaintext: str) -> str:
    """Encrypt non-empty API key string for storage."""
    pt = (plaintext or "").strip()
    if not pt:
        raise ValueError("openai_api_key is empty")
    return _fernet().encrypt(pt.encode("utf-8")).decode("ascii")


def decrypt_openai_api_key(ciphertext: str | None) -> str | None:
    if not ciphertext or not str(ciphertext).strip():
        return None
    try:
        raw = _fernet().decrypt(str(ciphertext).strip().encode("ascii"))
        return raw.decode("utf-8").strip() or None
    except (binascii.Error, ValueError, TypeError):
        return None


def openai_runtime_for_embed_row(row: object) -> tuple[str | None, str | None]:
    """Return (api_key, base_url) for chat completion when configured on this embed key."""
    plain = decrypt_openai_api_key(getattr(row, "openai_api_key_cipher", None))
    if not plain:
        return None, None
    base = getattr(row, "openai_api_base", None)
    base_s = (base or "").strip() or None
    return plain, base_s
