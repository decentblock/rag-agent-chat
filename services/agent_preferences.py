"""Persisted user agent selection + JSON config."""

from __future__ import annotations

import json
from typing import Any

from extensions import db
from models import UserAgentPreference


def get_preference(user_id: str) -> dict[str, Any]:
    row = UserAgentPreference.query.filter_by(user_id=user_id).first()
    if not row:
        return {"agent_id": "rag_document_qa", "config": {}}
    try:
        cfg = json.loads(row.config_json or "{}")
        if not isinstance(cfg, dict):
            cfg = {}
    except json.JSONDecodeError:
        cfg = {}
    return {"agent_id": row.agent_id, "config": cfg}


def set_preference(user_id: str, agent_id: str, config: dict[str, Any]) -> dict[str, Any]:
    row = UserAgentPreference.query.filter_by(user_id=user_id).first()
    if not row:
        row = UserAgentPreference(user_id=user_id, agent_id=agent_id, config_json="{}")
        db.session.add(row)
    row.agent_id = agent_id.strip().lower()
    row.config_json = json.dumps(config or {})
    db.session.commit()
    return get_preference(user_id)
