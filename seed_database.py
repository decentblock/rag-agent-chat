"""Idempotent bootstrap: permissions, default tenant, roles, admin user."""

from __future__ import annotations

from werkzeug.security import generate_password_hash

from config import BOOTSTRAP_SUPERUSER
from extensions import db
from models import Collection, Permission, Role, Tenant, User

PERMISSION_CODES = [
    "*",
    "documents:read",
    "documents:write",
    "collections:manage",
    "chat:query",
    "users:manage",
    "embed:keys",
]

ROLE_MATRIX = {
    "Admin": ["*"],
    "Editor": [
        "documents:read",
        "documents:write",
        "collections:manage",
        "chat:query",
        "embed:keys",
    ],
    "Viewer": [
        "documents:read",
        "chat:query",
    ],
}


def ensure_permissions() -> dict[str, Permission]:
    out: dict[str, Permission] = {}
    for code in PERMISSION_CODES:
        p = Permission.query.filter_by(code=code).first()
        if not p:
            p = Permission(code=code)
            db.session.add(p)
            db.session.flush()
        out[code] = p
    return out


def seed_if_needed(
    *,
    default_tenant_slug: str,
    default_tenant_name: str,
    admin_username: str,
    admin_password: str,
) -> None:
    perm_map = ensure_permissions()
    db.session.flush()

    tenant = Tenant.query.filter_by(slug=default_tenant_slug).first()
    if not tenant:
        tenant = Tenant(name=default_tenant_name, slug=default_tenant_slug)
        db.session.add(tenant)
        db.session.flush()

    for role_name, codes in ROLE_MATRIX.items():
        role = Role.query.filter_by(tenant_id=tenant.id, name=role_name).first()
        if role:
            continue
        role = Role(tenant_id=tenant.id, name=role_name)
        role.permissions = [perm_map[c] for c in codes]
        db.session.add(role)
    db.session.flush()

    admin_role = Role.query.filter_by(tenant_id=tenant.id, name="Admin").first()
    user = User.query.filter_by(tenant_id=tenant.id, username=admin_username).first()
    if not user:
        user = User(
            tenant_id=tenant.id,
            username=admin_username,
            password_hash=generate_password_hash(admin_password),
            is_active=True,
            is_superuser=True,
        )
        user.roles = [admin_role] if admin_role else []
        db.session.add(user)

    ensure_default_collection(tenant.id)

    boot_admin = User.query.filter_by(tenant_id=tenant.id, username=admin_username).first()
    if boot_admin:
        if BOOTSTRAP_SUPERUSER:
            boot_admin.is_superuser = True
        elif not User.query.filter_by(is_superuser=True).first():
            boot_admin.is_superuser = True

    db.session.commit()

    grant_embed_keys_to_existing_editors(perm_map.get("embed:keys"))


def grant_embed_keys_to_existing_editors(embed_perm: Permission | None) -> None:
    """Attach embed:keys to Editor roles created before this permission existed."""
    if not embed_perm:
        return
    for role in Role.query.filter_by(name="Editor").all():
        if embed_perm not in role.permissions:
            role.permissions.append(embed_perm)
    db.session.commit()


def ensure_default_collection(tenant_id: str, slug: str = "general", name: str = "General") -> Collection:
    c = Collection.query.filter_by(tenant_id=tenant_id, slug=slug).first()
    if c:
        return c
    c = Collection(tenant_id=tenant_id, slug=slug, name=name)
    db.session.add(c)
    db.session.flush()
    return c
