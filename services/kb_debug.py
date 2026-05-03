"""Knowledge-base diagnostics: Chroma counts vs DB, retrieval probes, audit trail."""

from __future__ import annotations

import json
from typing import Any

from chroma_util import chroma_collection_name
from clients import get_embeddings_for_tenant
from config import CHROMA_DB_FILE_PATH, EMEDDING_MODEL
from extensions import db
from langchain_community.vectorstores import Chroma
from models import Document, KbAuditEvent, Tenant


def chroma_persist_path() -> str:
    return CHROMA_DB_FILE_PATH


def _count_chunks_via_metadata_get(coll, where_filter: dict) -> int:
    """Chroma versions differ: some reject ``count(where=…)``. Use paginated ``get``."""
    total = 0
    offset = 0
    page = 8000
    while True:
        try:
            batch = coll.get(where=where_filter, include=[], limit=page, offset=offset)
        except TypeError:
            batch = coll.get(where=where_filter, include=[], limit=max(page, 100_000))
            return len(batch.get("ids") or [])
        ids = batch.get("ids") or []
        total += len(ids)
        if len(ids) < page:
            break
        offset += page
    return total


def count_vectors_for_document_in_collection(
    tenant_id: str,
    collection_uuid: str,
    document_id: str,
) -> int:
    """Chunk rows in Chroma matching tenant + document (metadata filter)."""
    embeddings = get_embeddings_for_tenant(str(tenant_id))
    vectordb = Chroma(
        collection_name=physical,
        embedding_function=embeddings,
        persist_directory=chroma_persist_path(),
    )
    coll = vectordb._collection
    filt: dict[str, Any] = {
        "$and": [
            {"tenant_id": tenant_id},
            {"document_id": document_id},
        ]
    }
    try:
        return int(coll.count(where=filt))
    except TypeError:
        # e.g. chromadb where ``Collection.count()`` does not accept ``where``
        pass
    except Exception:
        return 0

    try:
        return _count_chunks_via_metadata_get(coll, filt)
    except Exception:
        return 0


def build_document_index_debug(document: Document) -> dict[str, Any]:
    """Compare DB ingest snapshot vs live Chroma for each linked collection."""
    tenant_id = document.tenant_id
    per_coll: list[dict[str, Any]] = []
    total_chroma = 0
    detail = {}
    try:
        if document.ingest_detail_json:
            detail = json.loads(document.ingest_detail_json)
    except (json.JSONDecodeError, TypeError):
        detail = {}

    db_count = document.indexed_chunk_count or 0
    multi = len(document.collections) > 1
    for coll in document.collections:
        n = count_vectors_for_document_in_collection(tenant_id, coll.id, document.id)
        total_chroma += n
        row_match = True if multi else (n == db_count if db_count else n > 0)
        per_coll.append(
            {
                "collection_id": coll.id,
                "collection_slug": coll.slug,
                "chroma_physical_name": chroma_collection_name(tenant_id, coll.id),
                "chroma_vector_count": n,
                "matches_db_indexed_count": row_match,
            }
        )

    warnings: list[str] = []
    if db_count and total_chroma != db_count:
        warnings.append(
            f"Chroma total chunk rows ({total_chroma}) differ from DB indexed_chunk_count ({db_count}). "
            "Possible re-ingest, partial delete, or multiple collections."
        )
    if total_chroma == 0 and db_count > 0:
        warnings.append(
            "No vectors found in Chroma for this document but DB shows chunks indexed. "
            "Check CHROMA_DB_FILE_PATH / CHROMA_DB_DIR matches across workers and restarts."
        )
    if total_chroma == 0 and db_count == 0:
        warnings.append(
            "Document has no indexed chunks in DB or Chroma. Upload may have failed before indexing completed."
        )

    return {
        "document_id": document.id,
        "tenant_id": tenant_id,
        "original_filename": document.original_filename,
        "module_tag": document.module_tag,
        "byte_size": document.byte_size,
        "db_indexed_chunk_count": db_count,
        "db_indexed_at": document.indexed_at.isoformat() + "Z" if document.indexed_at else None,
        "ingest_detail": detail,
        "chroma_persist_directory": chroma_persist_path(),
        "embedding_model_config": EMEDDING_MODEL,
        "collections": per_coll,
        "chroma_total_vectors_for_document": total_chroma,
        "health_ok": (total_chroma > 0)
        and ((db_count == 0) or (total_chroma == db_count)),
        "warnings": warnings,
        "troubleshooting": [
            "Embed keys can restrict retrieval to specific collections — probe all collections or match the key’s scope.",
            "Console Chat uses the collection dropdown; align scope with where documents were uploaded.",
            "Empty PDF text layers scan as zero chunks; try TXT or a text-based PDF.",
        ],
    }


def merged_similarity_probe(
    chroma_collection_names: list[str],
    query: str,
    *,
    tenant_id: str,
    k_per_collection: int = 8,
) -> list[dict[str, Any]]:
    """Top matches with similarity scores across physical Chroma collections."""
    if not chroma_collection_names or not (query or "").strip():
        return []
    embeddings = get_embeddings_for_tenant(str(tenant_id))
    persist = chroma_persist_path()
    scored: list[tuple[float, Any]] = []
    for name in chroma_collection_names:
        vs = Chroma(
            collection_name=name,
            persist_directory=persist,
            embedding_function=embeddings,
        )
        pairs = vs.similarity_search_with_score(query.strip(), k=k_per_collection)
        for doc, score in pairs:
            scored.append((float(score), doc))

    scored.sort(key=lambda x: x[0])
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    rank = 0
    cap = max(k_per_collection * len(chroma_collection_names), 12)
    for score, doc in scored[:cap]:
        meta = doc.metadata if hasattr(doc, "metadata") else {}
        text = (doc.page_content or "").strip()
        key = (text[:160], str(meta.get("source", "")))
        if key in seen:
            continue
        seen.add(key)
        rank += 1
        out.append(
            {
                "rank": rank,
                "distance": score,
                "text_preview": text[:2000] + ("…" if len(text) > 2000 else ""),
                "metadata": dict(meta) if isinstance(meta, dict) else {},
            }
        )
    return out


def record_kb_audit(
    *,
    tenant_id: str,
    actor_user_id: str | None,
    event_type: str,
    message: str,
    document_id: str | None = None,
    collection_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> KbAuditEvent:
    row = KbAuditEvent(
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        event_type=event_type,
        document_id=document_id,
        collection_id=collection_id,
        message=(message or "")[:512],
        payload_json=json.dumps(payload, default=str)[:12000] if payload else None,
    )
    db.session.add(row)
    return row


def audit_events_payload(tenant_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
    lim = max(1, min(limit, 200))
    rows = (
        KbAuditEvent.query.filter_by(tenant_id=tenant_id)
        .order_by(KbAuditEvent.created_at.desc())
        .limit(lim)
        .all()
    )
    return [
        {
            "id": r.id,
            "event_type": r.event_type,
            "message": r.message,
            "document_id": r.document_id,
            "collection_id": r.collection_id,
            "actor_user_id": r.actor_user_id,
            "created_at": r.created_at.isoformat() + "Z" if r.created_at else None,
            "payload": json.loads(r.payload_json) if r.payload_json else None,
        }
        for r in rows
    ]


def resolve_kb_admin_tenant_id(
    *,
    current_tenant_id: str,
    is_superuser: bool,
    requested_tenant_id: str | None,
) -> tuple[str | None, str | None]:
    """Return (effective_tenant_id, error_message). Superuser may target another org via requested_tenant_id."""
    own = (current_tenant_id or "").strip()
    if not is_superuser:
        return own, None
    tid = (requested_tenant_id or "").strip()
    if not tid or tid == own:
        return own, None
    if Tenant.query.filter_by(id=tid).first():
        return tid, None
    return None, "Unknown tenant_id (superuser scope)"


def get_document_for_tenant(document_id: str, tenant_id: str) -> Document | None:
    return Document.query.filter_by(id=document_id, tenant_id=tenant_id).first()
