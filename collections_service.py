"""Tenant-scoped collection helpers and Chroma name resolution."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from sqlalchemy import or_

from chroma_util import chroma_collection_name
from extensions import db
from models import Collection

if TYPE_CHECKING:
    from models import Tenant


def slugify(label: str) -> str:
    s = (label or "").strip().lower()
    s = re.sub(r"[^a-z0-9_-]+", "-", s)
    s = s.strip("-")[:220]
    return s or "collection"


def find_collection(tenant_id: str, slug_or_label: str) -> Collection | None:
    raw = (slug_or_label or "").strip()
    if not raw:
        return None
    slug = slugify(raw)
    q = Collection.query.filter_by(tenant_id=tenant_id)
    return (
        q.filter(Collection.slug == slug).first()
        or q.filter(Collection.slug == raw).first()
        or q.filter(Collection.name == raw).first()
    )


def create_collection(tenant_id: str, label: str) -> Collection:
    slug = slugify(label)
    base_slug = slug
    n = 1
    while Collection.query.filter_by(tenant_id=tenant_id, slug=slug).first():
        n += 1
        slug = f"{base_slug}-{n}"
    c = Collection(tenant_id=tenant_id, slug=slug, name=label.strip()[:255] or slug)
    db.session.add(c)
    db.session.flush()
    return c


def list_chroma_physical_names(tenant_id: str, allowed_collection_ids: tuple[str, ...]) -> list[str]:
    q = Collection.query.filter_by(tenant_id=tenant_id)
    if allowed_collection_ids:
        aids = list(allowed_collection_ids)
        q = q.filter(or_(Collection.id.in_(aids), Collection.slug.in_(aids)))
    cols = q.all()
    return [chroma_collection_name(tenant_id, c.id) for c in cols]


def normalize_collection_filter(tenant_id: str, requested: tuple[str, ...]) -> tuple[str, ...]:
    """Map caller-supplied collection ids/slugs to canonical collection UUID strings."""
    if not requested:
        return ()
    ids: list[str] = []
    for x in requested:
        c = Collection.query.filter_by(tenant_id=tenant_id).filter(
            or_(Collection.id == x, Collection.slug == x)
        ).first()
        if c:
            ids.append(c.id)
    return tuple(ids)


def list_collections_payload(tenant_id: str) -> list[dict]:
    rows = (
        Collection.query.filter_by(tenant_id=tenant_id)
        .order_by(Collection.slug.asc())
        .all()
    )
    return [
        {
            "id": c.id,
            "slug": c.slug,
            "name": c.name,
            "chroma_collection": chroma_collection_name(tenant_id, c.id),
        }
        for c in rows
    ]
