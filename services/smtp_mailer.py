"""Send plain-text email via SMTP using merged email settings."""

from __future__ import annotations

import smtplib
from email.mime.text import MIMEText
from typing import Any


def send_email(
    settings: dict[str, Any],
    *,
    to_addrs: list[str],
    subject: str,
    body_text: str,
) -> tuple[bool, str | None]:
    host = (settings.get("smtp_host") or "").strip()
    if not host:
        return False, "SMTP host is not configured"
    from_addr = (settings.get("smtp_from_email") or "").strip()
    if not from_addr:
        return False, "From address is not configured"
    if not to_addrs:
        return False, "No recipients"

    port = int(settings.get("smtp_port") or 587)
    user = (settings.get("smtp_username") or "").strip()
    password = settings.get("smtp_password") or ""
    use_tls = bool(settings.get("smtp_use_tls", True))
    use_ssl = bool(settings.get("smtp_use_ssl", False))

    msg = MIMEText(body_text, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = ", ".join(to_addrs)

    try:
        if use_ssl:
            server = smtplib.SMTP_SSL(host, port, timeout=30)
        else:
            server = smtplib.SMTP(host, port, timeout=30)
        try:
            server.ehlo()
            if use_tls and not use_ssl:
                server.starttls()
                server.ehlo()
            if user:
                server.login(user, password)
            server.sendmail(from_addr, to_addrs, msg.as_string())
        finally:
            server.quit()
    except Exception as exc:
        return False, str(exc)
    return True, None
