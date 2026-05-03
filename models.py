"""Multi-tenant SQLAlchemy models (Postgres-ready; SQLite-friendly)."""

from __future__ import annotations

import uuid
from datetime import datetime

from extensions import db

role_permissions = db.Table(
    "role_permissions",
    db.Column("role_id", db.String(36), db.ForeignKey("roles.id"), primary_key=True),
    db.Column("permission_id", db.String(36), db.ForeignKey("permissions.id"), primary_key=True),
)

user_roles = db.Table(
    "user_roles",
    db.Column("user_id", db.String(36), db.ForeignKey("users.id"), primary_key=True),
    db.Column("role_id", db.String(36), db.ForeignKey("roles.id"), primary_key=True),
)

document_collections = db.Table(
    "document_collections",
    db.Column("document_id", db.String(36), db.ForeignKey("documents.id"), primary_key=True),
    db.Column("collection_id", db.String(36), db.ForeignKey("collections.id"), primary_key=True),
)


def _uuid() -> str:
    return str(uuid.uuid4())


class Tenant(db.Model):
    __tablename__ = "tenants"

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    name = db.Column(db.String(255), nullable=False)
    slug = db.Column(db.String(64), nullable=False, unique=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    # Billing / limits (see plans_catalog.py).
    plan_slug = db.Column(db.String(32), nullable=False, default="growth")
    usage_chat_month = db.Column(db.String(7), nullable=True)  # UTC "YYYY-MM"
    usage_chat_count = db.Column(db.Integer, nullable=False, default=0)
    # Platform operator (super admin): suspend org — blocks login and APIs for tenant users.
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    # Billing stubs until Stripe (or similar) integration — editable by superusers only.
    billing_contact_email = db.Column(db.String(255), nullable=True)
    payment_provider_customer_id = db.Column(db.String(255), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    # JSON array of agent_id strings; when null/empty string, plan_catalog allowlist applies as-is.
    # Non-empty JSON overrides allowed agents for this tenant (whitelist).
    allowed_agent_ids_json = db.Column(db.Text, nullable=True)


class Permission(db.Model):
    __tablename__ = "permissions"

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    code = db.Column(db.String(128), nullable=False, unique=True)


class Role(db.Model):
    __tablename__ = "roles"

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    tenant_id = db.Column(db.String(36), db.ForeignKey("tenants.id"), nullable=False, index=True)
    name = db.Column(db.String(64), nullable=False)
    permissions = db.relationship(
        "Permission",
        secondary=role_permissions,
        lazy="selectin",
    )
    __table_args__ = (db.UniqueConstraint("tenant_id", "name", name="uq_roles_tenant_name"),)


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    tenant_id = db.Column(db.String(36), db.ForeignKey("tenants.id"), nullable=False, index=True)
    username = db.Column(db.String(128), nullable=False)
    password_hash = db.Column(db.String(255), nullable=True)
    email = db.Column(db.String(255), nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    # Platform operator (can edit /super/settings). Independent of tenant Admin role.
    is_superuser = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    tenant = db.relationship("Tenant", backref=db.backref("users", lazy="dynamic"))
    roles = db.relationship("Role", secondary=user_roles, lazy="selectin")

    __table_args__ = (db.UniqueConstraint("tenant_id", "username", name="uq_users_tenant_username"),)


class PasswordResetOtp(db.Model):
    """Email OTP for self-service password reset (tenant-scoped user lookup)."""

    __tablename__ = "password_reset_otps"

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    user_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False, index=True)
    code_hash = db.Column(db.String(255), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    user = db.relationship("User", backref=db.backref("password_reset_otps", lazy="dynamic"))


class SystemSetting(db.Model):
    """Global key/value overrides (e.g. landing pricing). Editable by superusers."""

    __tablename__ = "system_settings"

    key = db.Column(db.String(128), primary_key=True)
    value = db.Column(db.Text, nullable=False, default="")
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class LeadInquiry(db.Model):
    """Public marketing form submissions (contact sales / request proposal)."""

    __tablename__ = "lead_inquiries"

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    kind = db.Column(db.String(32), nullable=False, index=True)  # contact_sales | request_proposal
    name = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(255), nullable=False)
    company = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(64), nullable=True)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)


class Collection(db.Model):
    __tablename__ = "collections"

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    tenant_id = db.Column(db.String(36), db.ForeignKey("tenants.id"), nullable=False, index=True)
    name = db.Column(db.String(255), nullable=False)
    slug = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    tenant = db.relationship("Tenant", backref=db.backref("collections", lazy="dynamic"))

    __table_args__ = (db.UniqueConstraint("tenant_id", "slug", name="uq_collections_tenant_slug"),)


class Document(db.Model):
    __tablename__ = "documents"

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    tenant_id = db.Column(db.String(36), db.ForeignKey("tenants.id"), nullable=False, index=True)
    uploaded_by_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=True)
    original_filename = db.Column(db.String(512), nullable=False)
    storage_path = db.Column(db.String(1024), nullable=False)
    mime_type = db.Column(db.String(128), nullable=True)
    byte_size = db.Column(db.BigInteger, default=0)
    status = db.Column(db.String(32), default="ready", nullable=False)
    module_tag = db.Column(db.String(128), default="DEFAULT", nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    tenant = db.relationship("Tenant", backref=db.backref("documents", lazy="dynamic"))
    uploader = db.relationship("User", backref=db.backref("documents_uploaded", lazy="dynamic"))
    collections = db.relationship(
        "Collection",
        secondary=document_collections,
        lazy="selectin",
    )


class UserAgentPreference(db.Model):
    """Per-user selected marketplace agent + JSON configuration."""

    __tablename__ = "user_agent_preferences"

    user_id = db.Column(db.String(36), db.ForeignKey("users.id"), primary_key=True)
    agent_id = db.Column(db.String(64), nullable=False, index=True)
    config_json = db.Column(db.Text, nullable=False, default="{}")
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    user = db.relationship("User", backref=db.backref("agent_preference", uselist=False))


class ApiKey(db.Model):
    """Long-lived keys for embedded chat / API access (tenant-scoped)."""

    __tablename__ = "api_keys"

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    tenant_id = db.Column(db.String(36), db.ForeignKey("tenants.id"), nullable=False, index=True)
    name = db.Column(db.String(255), nullable=False)
    key_prefix = db.Column(db.String(32), nullable=False, unique=True, index=True)
    key_hash = db.Column(db.String(255), nullable=False)
    allowed_collection_ids_json = db.Column(db.Text, nullable=True)
    # JSON array of https:// origins allowed for browser embed when using this key; empty/null → platform embed CORS (env / super settings).
    allowed_embed_origins_json = db.Column(db.Text, nullable=True)
    default_agent_id = db.Column(db.String(64), nullable=True)
    agent_config_json = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    tenant = db.relationship("Tenant", backref=db.backref("api_keys", lazy="dynamic"))
