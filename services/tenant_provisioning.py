"""Create a new tenant (organisation) with RBAC roles and first admin user."""

from __future__ import annotations

from werkzeug.security import generate_password_hash

from collections_service import slugify
from extensions import db
from models import Role, Tenant, User
from plans_catalog import normalize_plan_slug
from seed_database import ROLE_MATRIX, ensure_default_collection, ensure_permissions

from .plan_enforcement import check_can_add_user


def normalize_org_slug(raw: str) -> str:
    s = slugify(raw or "")
    if len(s) < 2:
        raise ValueError("Organisation URL slug must be at least 2 characters.")
    return s[:64]


def provision_new_organization(
    *,
    organization_name: str,
    organization_slug: str,
    plan_slug: str,
    admin_username: str,
    admin_password: str,
    admin_email: str | None = None,
) -> Tenant:
    """
    Create tenant, clone standard roles for that tenant, admin user, default collection.
    Caller must commit surrounding transaction or rely on this function's commit.
    """
    name = (organization_name or "").strip()
    if len(name) < 2:
        raise ValueError("Organisation name is required.")

    slug = normalize_org_slug(organization_slug)
    if Tenant.query.filter_by(slug=slug).first():
        raise ValueError("That organisation URL is already taken. Choose another slug.")

    uname = (admin_username or "").strip()
    if len(uname) < 2:
        raise ValueError("Admin username is required.")
    if len(admin_password or "") < 8:
        raise ValueError("Password must be at least 8 characters.")

    perm_map = ensure_permissions()
    db.session.flush()

    tenant = Tenant(
        name=name[:255],
        slug=slug,
        plan_slug=normalize_plan_slug(plan_slug),
        usage_chat_month=None,
        usage_chat_count=0,
    )
    db.session.add(tenant)
    db.session.flush()

    for role_name, codes in ROLE_MATRIX.items():
        role = Role(tenant_id=tenant.id, name=role_name)
        role.permissions = [perm_map[c] for c in codes]
        db.session.add(role)
    db.session.flush()

    admin_role = Role.query.filter_by(tenant_id=tenant.id, name="Admin").first()
    if not admin_role:
        db.session.rollback()
        raise RuntimeError("Admin role missing after provisioning.")

    # Synthetic check: new tenant should always allow first admin.
    ok, err = check_can_add_user(tenant)
    if not ok:
        db.session.rollback()
        raise ValueError(err or "Cannot add admin user under plan limits.")

    user = User(
        tenant_id=tenant.id,
        username=uname[:128],
        password_hash=generate_password_hash(admin_password),
        email=(admin_email or "").strip()[:255] or None,
        is_active=True,
    )
    user.roles = [admin_role]
    db.session.add(user)

    ensure_default_collection(tenant.id)

    db.session.commit()
    return tenant
