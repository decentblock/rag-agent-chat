"""Persist and list chat query/answer audit rows (sources retained server-side only)."""

from __future__ import annotations

import json
from typing import Any

from extensions import db
from models import ApiKey, ChatQueryAudit

_MAX_TEXT = 400_000
_MAX_ERR = 8000


def chat_response_for_client(result: dict[str, Any]) -> dict[str, Any]:
    """Strip citations from API payloads shown to browsers/embeds."""
    out = dict(result)
    out["citations"] = []
    return out


def record_chat_query_audit(
    *,
    tenant_id: str,
    channel: str,
    actor_user_id: str | None,
    actor_username: str | None,
    embed_key_id: str | None,
    visitor_session: str | None,
    agent_id: str,
    query_text: str,
    answer_text: str,
    sources: list[Any],
    error_message: str | None,
    collection_ids: list[str] | tuple[str, ...] | None,
) -> None:
    src_list = [str(s) for s in (sources or []) if s is not None]
    try:
        sj = json.dumps(src_list)
    except (TypeError, ValueError):
        sj = json.dumps([repr(x) for x in src_list])
    if len(sj) > _MAX_TEXT:
        sj = sj[:_MAX_TEXT]

    cid_json = None
    if collection_ids:
        try:
            cid_json = json.dumps([str(x) for x in collection_ids])
        except (TypeError, ValueError):
            cid_json = None
        if cid_json and len(cid_json) > 65535:
            cid_json = cid_json[:65535]

    err = (error_message or "").strip() or None
    if err and len(err) > _MAX_ERR:
        err = err[:_MAX_ERR]

    row = ChatQueryAudit(
        tenant_id=str(tenant_id),
        channel=str(channel).strip().lower()[:16] or "console",
        actor_user_id=str(actor_user_id) if actor_user_id else None,
        actor_username=(actor_username or "")[:128] or None,
        embed_key_id=str(embed_key_id) if embed_key_id else None,
        visitor_session=(visitor_session or "")[:160] or None,
        agent_id=str(agent_id).strip().lower()[:64],
        query_text=(query_text or "")[:_MAX_TEXT],
        answer_text=(answer_text or "")[:_MAX_TEXT],
        sources_json=sj or None,
        error_message=err,
        collection_ids_json=cid_json,
    )
    db.session.add(row)
    db.session.commit()


def delete_audit_row(*, tenant_id: str, audit_id: str) -> bool:
    row = ChatQueryAudit.query.filter_by(id=str(audit_id), tenant_id=str(tenant_id)).first()
    if not row:
        return False
    db.session.delete(row)
    db.session.commit()
    return True


def list_audits_payload(
    *,
    tenant_id: str,
    limit: int,
    offset: int,
    embed_key_filter: str | None,
) -> dict[str, Any]:
    """
    embed_key_filter:
      None or '' or 'all' → no filter
      'console' → embed_key_id IS NULL
      else → UUID of embed api_keys row
    """
    tid = str(tenant_id)
    base = ChatQueryAudit.query.filter_by(tenant_id=tid)
    fk = (embed_key_filter or "").strip().lower()
    if fk and fk not in ("all", "*"):
        if fk == "console":
            base = base.filter(ChatQueryAudit.embed_key_id.is_(None))
        else:
            base = base.filter(ChatQueryAudit.embed_key_id == fk)

    total = base.count()
    rows = (
        db.session.query(ChatQueryAudit, ApiKey.name.label("embed_key_name"))
        .outerjoin(ApiKey, ChatQueryAudit.embed_key_id == ApiKey.id)
        .filter(ChatQueryAudit.tenant_id == tid)
    )
    if fk and fk not in ("all", "*"):
        if fk == "console":
            rows = rows.filter(ChatQueryAudit.embed_key_id.is_(None))
        else:
            rows = rows.filter(ChatQueryAudit.embed_key_id == fk)

    rows = rows.order_by(ChatQueryAudit.created_at.desc()).offset(offset).limit(limit).all()

    def parse_sources(raw: str | None) -> list[str]:
        if not raw:
            return []
        try:
            data = json.loads(raw)
            return [str(x) for x in data] if isinstance(data, list) else []
        except json.JSONDecodeError:
            return []

    def parse_cols(raw: str | None) -> list[str]:
        if not raw:
            return []
        try:
            data = json.loads(raw)
            return [str(x) for x in data] if isinstance(data, list) else []
        except json.JSONDecodeError:
            return []

    items = []
    for r, key_name in rows:
        items.append(
            {
                "id": r.id,
                "created_at": r.created_at.isoformat() + "Z" if r.created_at else None,
                "channel": r.channel,
                "actor_username": r.actor_username,
                "embed_key_id": r.embed_key_id,
                "embed_key_name": key_name or None,
                "visitor_session": r.visitor_session,
                "agent_id": r.agent_id,
                "query_text": r.query_text or "",
                "answer_text": r.answer_text or "",
                "sources": parse_sources(r.sources_json),
                "collection_ids": parse_cols(r.collection_ids_json),
                "error_message": r.error_message,
            }
        )

    return {
        "tenant_id": tid,
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": items,
    }
