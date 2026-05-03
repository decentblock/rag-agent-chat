"""Tenant embed API keys: mint, verify, list."""

from __future__ import annotations

import json
import secrets
from typing import Any

from werkzeug.security import check_password_hash, generate_password_hash

from collections_service import normalize_collection_filter
from extensions import db
from models import ApiKey, Collection


def collection_slugs_for_allowed_ids(tenant_id: str, ids: list[str]) -> list[str]:
    """Map stored collection UUIDs to slugs (fallback to id if row missing)."""
    if not ids:
        return []
    rows = (
        Collection.query.filter_by(tenant_id=tenant_id)
        .filter(Collection.id.in_(ids))
        .all()
    )
    by_id = {r.id: r.slug for r in rows}
    return [by_id.get(i, i) for i in ids]


def mint_embed_key() -> tuple[str, str]:
    """Return (full_secret_key, unique_lookup_prefix)."""
    part = secrets.token_hex(6)
    secret = secrets.token_hex(24)
    full = f"nxemb_{part}_{secret}"
    prefix = f"nxemb_{part}"
    return full, prefix


def validate_allowed_collections_for_tenant(
    tenant_id: str, ids: list[str] | None
) -> tuple[list[str] | None, str | None]:
    """Normalize collection UUIDs for tenant; return (uuid_list or None for unrestricted, error)."""
    if not ids:
        return None, None
    if not isinstance(ids, list):
        return None, "allowed_collection_ids must be an array"
    raw_ids = [str(x).strip() for x in ids if str(x).strip()]
    unique_req = list(dict.fromkeys(raw_ids))
    normalized = normalize_collection_filter(tenant_id, tuple(unique_req))
    if len(normalized) != len(unique_req):
        return None, "One or more collection ids are invalid for this tenant"
    return list(normalized), None


def parse_allowed_embed_origins(row: ApiKey) -> list[str]:
    raw = getattr(row, "allowed_embed_origins_json", None)
    if not raw:
        return []
    try:
        data = json.loads(raw)
        if not isinstance(data, list):
            return []
        return [str(x).strip().rstrip("/") for x in data if str(x).strip()]
    except json.JSONDecodeError:
        return []


def normalize_allowed_embed_origins_payload(raw: list | None) -> tuple[list[str] | None, str | None]:
    """Normalize list from JSON body; empty list → None (store null → platform default CORS)."""
    if raw is None:
        return None, None
    if not isinstance(raw, list):
        return None, "allowed_embed_origins must be an array of strings"
    seen: set[str] = set()
    out: list[str] = []
    for item in raw:
        s = str(item).strip().rstrip("/")
        if not s:
            continue
        low = s.lower()
        if not (low.startswith("http://") or low.startswith("https://")):
            return None, f"Invalid origin (use https://… or http://…): {s}"
        if s not in seen:
            seen.add(s)
            out.append(s)
    return (out if out else None), None


def create_embed_api_key(
    tenant_id: str,
    *,
    name: str,
    allowed_collection_ids: list[str] | None,
    default_agent_id: str | None,
    default_agent_config: dict[str, Any] | None,
    allowed_embed_origins: list[str] | None = None,
) -> tuple[ApiKey, str]:
    """Persist key; returns (row, plaintext_secret_shown_once)."""
    allowed_norm, err = validate_allowed_collections_for_tenant(tenant_id, allowed_collection_ids)
    if err:
        raise ValueError(err)

    full, prefix = mint_embed_key()
    row = ApiKey(
        tenant_id=tenant_id,
        name=name.strip()[:255] or "Embed key",
        key_prefix=prefix,
        key_hash=generate_password_hash(full),
        allowed_collection_ids_json=json.dumps(allowed_norm) if allowed_norm else None,
        allowed_embed_origins_json=(
            json.dumps(allowed_embed_origins) if allowed_embed_origins else None
        ),
        default_agent_id=(default_agent_id or "").strip().lower() or None,
        agent_config_json=json.dumps(default_agent_config or {}),
        is_active=True,
    )
    db.session.add(row)
    db.session.flush()
    return row, full


def update_embed_key_origins(tenant_id: str, key_id: str, origins: list | None) -> tuple[bool, str | None]:
    """Set allowed_embed_origins_json from normalized list (None clears → platform default)."""
    row = ApiKey.query.filter_by(id=key_id, tenant_id=tenant_id).first()
    if not row:
        return False, "Key not found"
    norm, err = normalize_allowed_embed_origins_payload(origins)
    if err:
        return False, err
    row.allowed_embed_origins_json = json.dumps(norm) if norm else None
    db.session.commit()
    return True, None


def revoke_embed_api_key(tenant_id: str, key_id: str) -> bool:
    row = ApiKey.query.filter_by(id=key_id, tenant_id=tenant_id).first()
    if not row:
        return False
    row.is_active = False
    db.session.commit()
    return True


def list_embed_keys_payload(tenant_id: str) -> list[dict[str, Any]]:
    rows = (
        ApiKey.query.filter_by(tenant_id=tenant_id)
        .order_by(ApiKey.created_at.desc())
        .all()
    )
    out: list[dict[str, Any]] = []
    for r in rows:
        allowed = parse_allowed_ids(r)
        cfg = {}
        if r.agent_config_json:
            try:
                cfg = json.loads(r.agent_config_json)
                if not isinstance(cfg, dict):
                    cfg = {}
            except json.JSONDecodeError:
                cfg = {}
        slug_labels = collection_slugs_for_allowed_ids(tenant_id, allowed) if allowed else None
        cipher = getattr(r, "openai_api_key_cipher", None)
        api_base = getattr(r, "openai_api_base", None)
        out.append(
            {
                "id": r.id,
                "name": r.name,
                "key_prefix": r.key_prefix,
                "is_active": r.is_active,
                "allowed_collection_ids": allowed,
                "allowed_collection_slugs": slug_labels,
                "allowed_embed_origins": parse_allowed_embed_origins(r),
                "default_agent_id": r.default_agent_id,
                "default_agent_config": cfg,
                "has_openai_key": bool(cipher and str(cipher).strip()),
                "openai_api_base": ((api_base or "").strip() or None),
                "created_at": r.created_at.isoformat() + "Z",
            }
        )
    return out


def authenticate_embed_key(raw_token: str | None) -> ApiKey | None:
    if not raw_token:
        return None
    token = raw_token.strip()
    parts = token.split("_", 2)
    if len(parts) != 3 or parts[0] != "nxemb":
        return None
    lookup = f"{parts[0]}_{parts[1]}"
    row = ApiKey.query.filter_by(key_prefix=lookup, is_active=True).first()
    if not row or not check_password_hash(row.key_hash, token):
        return None
    return row


def extract_embed_token_from_request() -> str | None:
    from flask import request

    auth = request.headers.get("Authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return (request.headers.get("X-Nexura-Embed-Key") or "").strip() or None


def parse_allowed_ids(row: ApiKey) -> list[str] | None:
    if not row.allowed_collection_ids_json:
        return None
    try:
        data = json.loads(row.allowed_collection_ids_json)
        if not isinstance(data, list):
            return None
        out: list[str] = []
        for x in data:
            if x is None:
                continue
            s = str(x).strip()
            if not s or s.lower() == "none":
                continue
            out.append(s)
        return out if out else None
    except json.JSONDecodeError:
        return None


def normalize_embed_collection_scope(
    tenant_id: str, key_allowed_ids: list[str] | None, requested: tuple[str, ...]
) -> tuple[tuple[str, ...], str | None]:
    """
    key_allowed_ids None or empty list treated as unrestricted (full tenant).
    Non-empty key list restricts to those collections; requested must intersect when provided.
    """
    normalized_req = normalize_collection_filter(tenant_id, requested)
    if requested and not normalized_req:
        return (), "Invalid collection_ids for this tenant"

    if not key_allowed_ids:
        return normalized_req, None

    allowed_norm = normalize_collection_filter(tenant_id, tuple(key_allowed_ids))
    if not allowed_norm:
        return (), "Embed key has no valid collections"

    if not normalized_req:
        return tuple(sorted(allowed_norm)), None

    inter = tuple(sorted(set(normalized_req) & set(allowed_norm)))
    if not inter:
        return (), "collection_ids must fall within this embed key's allowed collections"
    return inter, None


def default_agent_config(row: ApiKey) -> dict[str, Any]:
    if not row.agent_config_json:
        return {}
    try:
        cfg = json.loads(row.agent_config_json)
        return cfg if isinstance(cfg, dict) else {}
    except json.JSONDecodeError:
        return {}
