"""Self-service password reset: OTP by email (tenant slug + email lookup)."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta

from sqlalchemy import func

from werkzeug.security import check_password_hash, generate_password_hash

from extensions import db
from models import PasswordResetOtp, Tenant, User

from services.email_settings import merged_smtp_config, password_reset_emails_enabled
from services.smtp_mailer import send_email

OTP_LEN = 6
OTP_TTL_MINUTES = 15
MAX_OTP_REQUESTS_PER_HOUR = 5
MIN_PASSWORD_LEN = 8

_GENERIC_OK = (
    "If an account exists with that organisation and email, we sent a verification code. "
    "Check your inbox."
)


def find_user_for_email_reset(tenant_slug: str, email: str) -> User | None:
    slug = (tenant_slug or "").strip().lower()
    em = (email or "").strip().lower()
    if not slug or not em:
        return None
    tenant = Tenant.query.filter(func.lower(Tenant.slug) == slug).first()
    if not tenant or not getattr(tenant, "is_active", True):
        return None
    return (
        User.query.filter(
            User.tenant_id == tenant.id,
            User.email.isnot(None),
            func.lower(User.email) == em,
            User.is_active.is_(True),  # noqa: E712
        ).first()
    )


def _otp_email_body(*, tenant_name: str, code: str, username: str) -> str:
    return (
        f"Hello {username},\n\n"
        f"Your Nexura password reset code for organisation \"{tenant_name}\" is:\n\n"
        f"  {code}\n\n"
        f"This code expires in {OTP_TTL_MINUTES} minutes.\n"
        "If you did not request a reset, ignore this email.\n"
    )


def request_otp_email(tenant_slug: str, email: str) -> tuple[bool, str]:
    """Always returns generic success message when returning ok=True for privacy."""
    PasswordResetOtp.query.filter(PasswordResetOtp.expires_at < datetime.utcnow()).delete()
    db.session.commit()

    if not password_reset_emails_enabled():
        return False, "Password reset by email is not available. Contact your administrator."

    user = find_user_for_email_reset(tenant_slug, email)
    if not user:
        return True, _GENERIC_OK

    since = datetime.utcnow() - timedelta(hours=1)
    recent = PasswordResetOtp.query.filter(
        PasswordResetOtp.user_id == user.id,
        PasswordResetOtp.created_at >= since,
    ).count()
    if recent >= MAX_OTP_REQUESTS_PER_HOUR:
        return True, _GENERIC_OK

    to_email = (user.email or "").strip()
    if not to_email:
        return True, _GENERIC_OK

    PasswordResetOtp.query.filter_by(user_id=user.id).delete()

    code = f"{secrets.randbelow(10**OTP_LEN):0{OTP_LEN}d}"
    row = PasswordResetOtp(
        user_id=user.id,
        code_hash=generate_password_hash(code),
        expires_at=datetime.utcnow() + timedelta(minutes=OTP_TTL_MINUTES),
    )
    db.session.add(row)
    db.session.commit()

    tenant = user.tenant
    subject = "Your Nexura password reset code"
    body = _otp_email_body(
        tenant_name=tenant.name if tenant else tenant_slug,
        code=code,
        username=user.username,
    )

    settings = merged_smtp_config()
    ok, err = send_email(
        settings,
        to_addrs=[to_email],
        subject=subject,
        body_text=body,
    )
    if not ok:
        PasswordResetOtp.query.filter_by(id=row.id).delete()
        db.session.commit()
        return False, err or "Failed to send email"

    return True, _GENERIC_OK


def complete_password_reset(
    tenant_slug: str,
    email: str,
    otp: str,
    new_password: str,
) -> tuple[bool, str | None]:
    user = find_user_for_email_reset(tenant_slug, email)
    if not user:
        return False, "Invalid or expired code."

    raw_otp = "".join(ch for ch in str(otp or "") if ch.isdigit())
    if len(raw_otp) != OTP_LEN:
        return False, "Enter the 6-digit code from your email."

    pw = str(new_password or "").strip()
    if len(pw) < MIN_PASSWORD_LEN:
        return False, f"Password must be at least {MIN_PASSWORD_LEN} characters."

    now = datetime.utcnow()
    rows = (
        PasswordResetOtp.query.filter(
            PasswordResetOtp.user_id == user.id,
            PasswordResetOtp.expires_at > now,
        )
        .order_by(PasswordResetOtp.created_at.desc())
        .all()
    )
    matched = None
    for row in rows:
        if check_password_hash(row.code_hash, raw_otp):
            matched = row
            break
    if not matched:
        return False, "Invalid or expired code."

    user.password_hash = generate_password_hash(pw)
    PasswordResetOtp.query.filter_by(user_id=user.id).delete()
    db.session.commit()
    return True, None
