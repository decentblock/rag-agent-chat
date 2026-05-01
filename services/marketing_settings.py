"""Landing page marketing copy & pricing: config defaults + DB overrides (SystemSetting)."""

from __future__ import annotations

from typing import Any

from flask import url_for

from extensions import db
from models import SystemSetting

from config import (
    MARKETING_GROWTH_ANNUAL_BLURB,
    MARKETING_GROWTH_MONTHLY_BLURB,
    MARKETING_PRICE_GROWTH_ANNUAL_EQUIV,
    MARKETING_PRICE_GROWTH_MONTHLY,
    MARKETING_PRICE_STARTER_DISPLAY,
)

# Keys persisted in system_settings (super admin UI / optional DB overrides).
MARKETING_SETTING_KEYS: tuple[str, ...] = (
    "marketing_price_starter_display",
    "marketing_price_growth_monthly",
    "marketing_price_growth_annual_equiv",
    "marketing_growth_monthly_blurb",
    "marketing_growth_annual_blurb",
)


def _config_defaults() -> dict[str, str]:
    return {
        "marketing_price_starter_display": MARKETING_PRICE_STARTER_DISPLAY,
        "marketing_price_growth_monthly": MARKETING_PRICE_GROWTH_MONTHLY,
        "marketing_price_growth_annual_equiv": MARKETING_PRICE_GROWTH_ANNUAL_EQUIV,
        "marketing_growth_monthly_blurb": MARKETING_GROWTH_MONTHLY_BLURB,
        "marketing_growth_annual_blurb": MARKETING_GROWTH_ANNUAL_BLURB,
    }


def merged_marketing_strings() -> dict[str, str]:
    """All marketing keys with config defaults overlaid by non-empty DB values."""
    out = _config_defaults()
    rows = SystemSetting.query.filter(SystemSetting.key.in_(MARKETING_SETTING_KEYS)).all()
    for r in rows:
        if r.key in out and (r.value or "").strip():
            out[r.key] = (r.value or "").strip()
    return out


def pricing_for_landing_template() -> dict[str, Any]:
    """Structured dict for Jinja landing pricing section."""
    m = merged_marketing_strings()
    return {
        "starter_display": m["marketing_price_starter_display"],
        "growth_monthly": m["marketing_price_growth_monthly"],
        "growth_annual_equiv": m["marketing_price_growth_annual_equiv"],
        "growth_monthly_blurb": m["marketing_growth_monthly_blurb"],
        "growth_annual_blurb": m["marketing_growth_annual_blurb"],
        "url_contact_sales": url_for("contact_sales_page"),
        "url_request_proposal": url_for("request_proposal_page"),
    }


def get_super_admin_form_values() -> dict[str, str]:
    """Current effective strings for the super settings form (defaults + DB)."""
    return merged_marketing_strings()


def marketing_env_defaults() -> dict[str, str]:
    """Read-only env/config defaults (shown as hints in super admin UI)."""
    return dict(_config_defaults())


def save_marketing_settings_from_form(form: dict[str, str]) -> None:
    """Upsert SystemSetting rows from POST body. Empty value removes override (env/default wins)."""
    for key in MARKETING_SETTING_KEYS:
        submitted = (form.get(key) or "").strip()
        row = SystemSetting.query.filter_by(key=key).first()
        if not submitted:
            if row:
                db.session.delete(row)
            continue
        if row:
            row.value = submitted
        else:
            db.session.add(SystemSetting(key=key, value=submitted))
    db.session.commit()
