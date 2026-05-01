"""SMTP / outbound email settings: env defaults + system_settings overrides (super admin)."""

from __future__ import annotations

from typing import Any

from extensions import db
from models import SystemSetting

from config import (
    SMTP_FROM_EMAIL,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_USE_SSL,
    SMTP_USE_TLS,
    SMTP_USERNAME,
)

EMAIL_SETTING_KEYS: tuple[str, ...] = (
    "smtp_host",
    "smtp_port",
    "smtp_username",
    "smtp_password",
    "smtp_use_tls",
    "smtp_use_ssl",
    "smtp_from_email",
    "email_password_reset_enabled",
)


def _env_defaults() -> dict[str, str]:
    return {
        "smtp_host": SMTP_HOST,
        "smtp_port": str(SMTP_PORT),
        "smtp_username": SMTP_USERNAME,
        "smtp_password": SMTP_PASSWORD,
        "smtp_use_tls": "true" if SMTP_USE_TLS else "false",
        "smtp_use_ssl": "true" if SMTP_USE_SSL else "false",
        "smtp_from_email": SMTP_FROM_EMAIL,
        "email_password_reset_enabled": "true",
    }


def merged_smtp_config() -> dict[str, Any]:
    """Effective SMTP dict for sending (password may be empty)."""
    base = _env_defaults()
    rows = SystemSetting.query.filter(SystemSetting.key.in_(EMAIL_SETTING_KEYS)).all()
    for r in rows:
        if r.key in base and (r.value or "").strip():
            base[r.key] = (r.value or "").strip()
    port_raw = base.get("smtp_port") or "587"
    try:
        port = int(port_raw)
    except ValueError:
        port = 587
    use_tls = str(base.get("smtp_use_tls", "true")).lower() in ("1", "true", "yes")
    use_ssl = str(base.get("smtp_use_ssl", "false")).lower() in ("1", "true", "yes")
    reset_on = str(base.get("email_password_reset_enabled", "true")).lower() in (
        "1",
        "true",
        "yes",
    )
    return {
        "smtp_host": (base.get("smtp_host") or "").strip(),
        "smtp_port": port,
        "smtp_username": (base.get("smtp_username") or "").strip(),
        "smtp_password": base.get("smtp_password") or "",
        "smtp_use_tls": use_tls,
        "smtp_use_ssl": use_ssl,
        "smtp_from_email": (base.get("smtp_from_email") or "").strip(),
        "email_password_reset_enabled": reset_on,
    }


def smtp_ready_for_sending() -> bool:
    c = merged_smtp_config()
    return bool(c["smtp_host"] and c["smtp_from_email"])


def password_reset_emails_enabled() -> bool:
    c = merged_smtp_config()
    return bool(c["email_password_reset_enabled"] and smtp_ready_for_sending())


def get_super_email_form_values() -> dict[str, str]:
    """Values for /super/email form: merged env + DB (password never echoed)."""
    m = merged_smtp_config()
    return {
        "smtp_host": m["smtp_host"],
        "smtp_port": str(m["smtp_port"]),
        "smtp_username": m["smtp_username"],
        "smtp_password": "",
        "smtp_use_tls": "true" if m["smtp_use_tls"] else "false",
        "smtp_use_ssl": "true" if m["smtp_use_ssl"] else "false",
        "smtp_from_email": m["smtp_from_email"],
        "email_password_reset_enabled": "true" if m["email_password_reset_enabled"] else "false",
    }


def email_env_defaults() -> dict[str, str]:
    return dict(_env_defaults())


def save_email_settings_from_form(form: dict[str, str]) -> None:
    """Upsert SystemSetting rows. Empty smtp_password clears override (fall back to env)."""
    bool_keys = frozenset(
        {"smtp_use_tls", "smtp_use_ssl", "email_password_reset_enabled"}
    )
    for key in EMAIL_SETTING_KEYS:
        raw = form.get(key)
        submitted = (raw if raw is not None else "").strip()
        if key in bool_keys and not submitted:
            submitted = "false"
        row = SystemSetting.query.filter_by(key=key).first()
        if key == "smtp_password" and not submitted:
            if row:
                db.session.delete(row)
            continue
        if not submitted and key not in bool_keys:
            if row:
                db.session.delete(row)
            continue
        if row:
            row.value = submitted
        else:
            db.session.add(SystemSetting(key=key, value=submitted))
    db.session.commit()
