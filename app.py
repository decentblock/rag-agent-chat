import os
from datetime import timedelta
from pathlib import Path

from flask import (
    Flask,
    abort,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import generate_password_hash
from werkzeug.utils import secure_filename

from agents import (
    register_builtin_agents,
    registry as agent_registry,
)
from auth import login_required, safe_next_path, superuser_required
from auth_service import authenticate_user
from collections_service import (
    create_collection,
    find_collection,
    list_chroma_physical_names,
    list_collections_payload,
    normalize_collection_filter,
)
from config import (
    ADMIN_BOOTSTRAP_PASSWORD,
    ADMIN_BOOTSTRAP_USERNAME,
    DATABASE_URL,
    DEFAULT_TENANT_SLUG,
    PORT,
    REGISTRATION_ENABLED,
    SESSION_SECRET,
)
from extensions import db
from logging_setup import logger
from models import Document, LeadInquiry, Role, Tenant, User
from principal import register_principal_loader
from rbac import permission_required, roles_include_users_manage, user_has_permission
from rag_ingestion import (
    delete_document_for_tenant,
    ingest_document_file,
    list_documents_db,
    preview_chunks_db,
)
from seed_database import seed_if_needed

app = Flask(__name__)
app.secret_key = SESSION_SECRET
app.permanent_session_lifetime = timedelta(days=14)
app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)
register_principal_loader(app)

UPLOAD_FOLDER = "uploads"
ALLOWED_EXTENSIONS = {"pdf", "txt"}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER


from services.embed_cors_settings import (
    apply_embed_cors_to_response,
    handle_embed_cors_preflight,
)


@app.before_request
def _nexura_embed_cors_preflight():
    return handle_embed_cors_preflight()


@app.after_request
def _nexura_embed_cors_headers(response):
    return apply_embed_cors_to_response(response)


register_builtin_agents(replace=True)

from agent_catalog import list_marketplace_payload, validate_agent_choice  # noqa: E402

_PROJECT_ROOT = Path(__file__).resolve().parent


def _markdown_extensions() -> list[str]:
    return [
        "markdown.extensions.extra",
        "markdown.extensions.nl2br",
        "markdown.extensions.sane_lists",
    ]


def _convert_markdown(raw: str) -> str:
    """HTML from Markdown, or escaped fallback when ``markdown`` is not installed."""
    import html as html_module

    try:
        import markdown
    except ImportError:
        return (
            '<p class="muted"><strong>Note:</strong> Install the <code>markdown</code> package '
            "for formatted docs (<code>pip install markdown</code>). Showing raw Markdown.</p>"
            + f'<pre class="docs-fallback">{html_module.escape(raw)}</pre>'
        )

    md = markdown.Markdown(extensions=_markdown_extensions())
    return md.convert(raw)


def _load_operator_guides_docs():
    """Return (summary_html, deployment_html, error_message) for FEATURES_SUMMARY + DEPLOYMENT.

    Used on the super-admin guides page only.
    """
    docs_dir = _PROJECT_ROOT / "docs"
    summary_path = docs_dir / "FEATURES_SUMMARY.md"
    deployment_path = docs_dir / "DEPLOYMENT.md"
    if not summary_path.is_file() or not deployment_path.is_file():
        return None, None, "Missing docs/FEATURES_SUMMARY.md or docs/DEPLOYMENT.md"
    summary_html = _convert_markdown(summary_path.read_text(encoding="utf-8"))
    deployment_html = _convert_markdown(deployment_path.read_text(encoding="utf-8"))
    return summary_html, deployment_html, None


def _load_technical_reference_html():
    """Return (technical_html, error_message). error_message when TECHNICAL.md is missing."""
    docs_dir = _PROJECT_ROOT / "docs"
    technical_path = docs_dir / "TECHNICAL.md"
    if not technical_path.is_file():
        return None, "Missing docs/TECHNICAL.md"
    return _convert_markdown(technical_path.read_text(encoding="utf-8")), None


def _ensure_tenant_plan_columns() -> None:
    """Best-effort ALTER for DBs created before plan / usage columns existed."""
    from sqlalchemy import inspect, text

    insp = inspect(db.engine)
    if not insp.has_table("tenants"):
        return
    existing = {c["name"] for c in insp.get_columns("tenants")}
    dialect = db.engine.dialect.name
    stmts: list[str] = []
    if "plan_slug" not in existing:
        if dialect == "sqlite":
            stmts.append(
                "ALTER TABLE tenants ADD COLUMN plan_slug VARCHAR(32) DEFAULT 'growth'"
            )
        elif dialect == "postgresql":
            stmts.append(
                "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS plan_slug VARCHAR(32) DEFAULT 'growth'"
            )
    if "usage_chat_month" not in existing:
        if dialect == "sqlite":
            stmts.append(
                "ALTER TABLE tenants ADD COLUMN usage_chat_month VARCHAR(7)"
            )
        elif dialect == "postgresql":
            stmts.append(
                "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS usage_chat_month VARCHAR(7)"
            )
    if "usage_chat_count" not in existing:
        if dialect == "sqlite":
            stmts.append(
                "ALTER TABLE tenants ADD COLUMN usage_chat_count INTEGER DEFAULT 0 NOT NULL"
            )
        elif dialect == "postgresql":
            stmts.append(
                "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS usage_chat_count INTEGER DEFAULT 0 NOT NULL"
            )
    if "is_active" not in existing:
        if dialect == "sqlite":
            stmts.append(
                "ALTER TABLE tenants ADD COLUMN is_active BOOLEAN DEFAULT 1 NOT NULL"
            )
        elif dialect == "postgresql":
            stmts.append(
                "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE NOT NULL"
            )
    if "billing_contact_email" not in existing:
        if dialect == "sqlite":
            stmts.append(
                "ALTER TABLE tenants ADD COLUMN billing_contact_email VARCHAR(255)"
            )
        elif dialect == "postgresql":
            stmts.append(
                "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS billing_contact_email VARCHAR(255)"
            )
    if "payment_provider_customer_id" not in existing:
        if dialect == "sqlite":
            stmts.append(
                "ALTER TABLE tenants ADD COLUMN payment_provider_customer_id VARCHAR(255)"
            )
        elif dialect == "postgresql":
            stmts.append(
                "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS payment_provider_customer_id VARCHAR(255)"
            )
    if "notes" not in existing:
        if dialect == "sqlite":
            stmts.append("ALTER TABLE tenants ADD COLUMN notes TEXT")
        elif dialect == "postgresql":
            stmts.append(
                "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS notes TEXT"
            )
    if "allowed_agent_ids_json" not in existing:
        if dialect == "sqlite":
            stmts.append(
                "ALTER TABLE tenants ADD COLUMN allowed_agent_ids_json TEXT"
            )
        elif dialect == "postgresql":
            stmts.append(
                "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS allowed_agent_ids_json TEXT"
            )
    for sql in stmts:
        db.session.execute(text(sql))
    if stmts:
        db.session.commit()


def _ensure_api_keys_columns() -> None:
    """Best-effort ALTER for api_keys rows created before embed agent columns existed."""
    from sqlalchemy import inspect, text

    insp = inspect(db.engine)
    if not insp.has_table("api_keys"):
        return
    existing = {c["name"] for c in insp.get_columns("api_keys")}
    dialect = db.engine.dialect.name
    stmts: list[str] = []

    def add(name: str, sqlite_sql: str, pg_sql: str) -> None:
        if name not in existing:
            if dialect == "sqlite":
                stmts.append(sqlite_sql)
            elif dialect == "postgresql":
                stmts.append(pg_sql)

    add(
        "allowed_collection_ids_json",
        "ALTER TABLE api_keys ADD COLUMN allowed_collection_ids_json TEXT",
        "ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS allowed_collection_ids_json TEXT",
    )
    add(
        "key_prefix",
        "ALTER TABLE api_keys ADD COLUMN key_prefix VARCHAR(32)",
        "ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS key_prefix VARCHAR(32)",
    )
    add(
        "default_agent_id",
        "ALTER TABLE api_keys ADD COLUMN default_agent_id VARCHAR(64)",
        "ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS default_agent_id VARCHAR(64)",
    )
    add(
        "agent_config_json",
        "ALTER TABLE api_keys ADD COLUMN agent_config_json TEXT",
        "ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS agent_config_json TEXT",
    )
    add(
        "is_active",
        "ALTER TABLE api_keys ADD COLUMN is_active BOOLEAN DEFAULT 1 NOT NULL",
        "ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE NOT NULL",
    )
    add(
        "created_at",
        "ALTER TABLE api_keys ADD COLUMN created_at DATETIME",
        "ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS created_at TIMESTAMP",
    )
    add(
        "allowed_embed_origins_json",
        "ALTER TABLE api_keys ADD COLUMN allowed_embed_origins_json TEXT",
        "ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS allowed_embed_origins_json TEXT",
    )

    for sql in stmts:
        db.session.execute(text(sql))
    if stmts:
        db.session.commit()


def _ensure_user_is_superuser_column() -> None:
    from sqlalchemy import inspect, text

    insp = inspect(db.engine)
    if not insp.has_table("users"):
        return
    existing = {c["name"] for c in insp.get_columns("users")}
    dialect = db.engine.dialect.name
    stmt = None
    if "is_superuser" not in existing:
        if dialect == "sqlite":
            stmt = "ALTER TABLE users ADD COLUMN is_superuser BOOLEAN DEFAULT 0 NOT NULL"
        elif dialect == "postgresql":
            stmt = (
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_superuser "
                "BOOLEAN DEFAULT FALSE NOT NULL"
            )
    if stmt:
        db.session.execute(text(stmt))
        db.session.commit()


def _ensure_documents_kb_columns() -> None:
    """Indexed chunk stats + ingest snapshot JSON on documents."""
    from sqlalchemy import inspect, text

    insp = inspect(db.engine)
    if not insp.has_table("documents"):
        return
    existing = {c["name"] for c in insp.get_columns("documents")}
    dialect = db.engine.dialect.name
    stmts: list[str] = []

    def add(name: str, sqlite_sql: str, pg_sql: str) -> None:
        if name not in existing:
            if dialect == "sqlite":
                stmts.append(sqlite_sql)
            elif dialect == "postgresql":
                stmts.append(pg_sql)

    add(
        "indexed_chunk_count",
        "ALTER TABLE documents ADD COLUMN indexed_chunk_count INTEGER DEFAULT 0 NOT NULL",
        "ALTER TABLE documents ADD COLUMN IF NOT EXISTS indexed_chunk_count INTEGER DEFAULT 0 NOT NULL",
    )
    add(
        "indexed_at",
        "ALTER TABLE documents ADD COLUMN indexed_at TIMESTAMP",
        "ALTER TABLE documents ADD COLUMN IF NOT EXISTS indexed_at TIMESTAMP",
    )
    add(
        "ingest_detail_json",
        "ALTER TABLE documents ADD COLUMN ingest_detail_json TEXT",
        "ALTER TABLE documents ADD COLUMN IF NOT EXISTS ingest_detail_json TEXT",
    )

    for sql in stmts:
        db.session.execute(text(sql))
    if stmts:
        db.session.commit()


def init_database() -> None:
    with app.app_context():
        db.create_all()
        _ensure_tenant_plan_columns()
        _ensure_api_keys_columns()
        _ensure_user_is_superuser_column()
        _ensure_documents_kb_columns()
        seed_if_needed(
            default_tenant_slug=DEFAULT_TENANT_SLUG,
            default_tenant_name="Default organization",
            admin_username=ADMIN_BOOTSTRAP_USERNAME,
            admin_password=ADMIN_BOOTSTRAP_PASSWORD,
        )


init_database()


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route("/")
def index():
    from services.marketing_settings import pricing_for_landing_template

    return render_template(
        "landing.html",
        logged_in=bool(session.get("user_id")),
        marketplace_agents=list_marketplace_payload(),
        registration_enabled=REGISTRATION_ENABLED,
        pricing=pricing_for_landing_template(),
    )


@app.route("/docs")
def docs_page():
    return render_template(
        "docs.html",
        openapi_spec_url=url_for("openapi_document"),
    )


@app.route("/api/openapi.json")
def openapi_document():
    from services.openapi_spec import build_openapi_spec

    root = request.url_root.rstrip("/")
    return jsonify(build_openapi_spec(server_url=root))


@app.route("/login", methods=["GET"])
def login_page():
    from services.email_settings import password_reset_emails_enabled

    if session.get("user_id"):
        return redirect(safe_next_path(request.args.get("next")))
    return render_template(
        "login.html",
        next_url=request.args.get("next") or "",
        error=None,
        default_tenant_slug=request.args.get("tenant_slug_hint") or DEFAULT_TENANT_SLUG,
        admin_bootstrap_username=ADMIN_BOOTSTRAP_USERNAME,
        registration_registered=request.args.get("registered") == "1",
        registration_enabled=REGISTRATION_ENABLED,
        forgot_password_enabled=password_reset_emails_enabled(),
    )


@app.route("/login", methods=["POST"])
def login_submit():
    from services.email_settings import password_reset_emails_enabled

    if session.get("user_id"):
        return redirect(safe_next_path(request.form.get("next") or request.args.get("next")))

    tenant_slug = (request.form.get("tenant_slug") or DEFAULT_TENANT_SLUG).strip()
    username = request.form.get("username", "")
    password = request.form.get("password", "")
    remember = request.form.get("remember") == "on"
    next_path = request.form.get("next") or request.args.get("next")

    user = authenticate_user(tenant_slug, username, password)
    if user:
        session.clear()
        session["user_id"] = user.id
        session["tenant_slug"] = user.tenant.slug
        session.permanent = remember
        return redirect(safe_next_path(next_path))

    return (
        render_template(
            "login.html",
            next_url=next_path or "",
            error="Invalid tenant, username, or password.",
            default_tenant_slug=tenant_slug or DEFAULT_TENANT_SLUG,
            admin_bootstrap_username=ADMIN_BOOTSTRAP_USERNAME,
            registration_registered=False,
            registration_enabled=REGISTRATION_ENABLED,
            forgot_password_enabled=password_reset_emails_enabled(),
        ),
        422,
    )


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password_page():
    from services.email_settings import password_reset_emails_enabled
    from services.password_reset_flow import request_otp_email

    enabled = password_reset_emails_enabled()
    if request.method == "POST":
        tenant_slug = request.form.get("tenant_slug", "").strip()
        email = request.form.get("email", "").strip()
        if not enabled:
            flash("Password reset by email is not configured on this server.", "error")
        elif tenant_slug and email:
            ok, msg = request_otp_email(tenant_slug, email)
            flash(msg, "success" if ok else "error")
        else:
            flash("Enter organisation slug and email.", "error")
        return redirect(url_for("forgot_password_page"))

    return render_template(
        "forgot_password.html",
        reset_enabled=enabled,
        default_tenant_slug=DEFAULT_TENANT_SLUG,
    )


@app.route("/reset-password", methods=["GET", "POST"])
def reset_password_page():
    from services.email_settings import password_reset_emails_enabled
    from services.password_reset_flow import complete_password_reset

    enabled = password_reset_emails_enabled()
    if request.method == "POST":
        tenant_slug = request.form.get("tenant_slug", "").strip()
        email = request.form.get("email", "").strip()
        otp = request.form.get("otp", "").strip()
        pw = request.form.get("password", "")
        pw2 = request.form.get("password_confirm", "")
        if not enabled:
            flash("Password reset by email is not configured on this server.", "error")
        elif pw != pw2:
            flash("Passwords do not match.", "error")
        else:
            ok, err = complete_password_reset(tenant_slug, email, otp, pw)
            if ok:
                flash("Password updated. You can sign in.", "success")
                return redirect(url_for("login_page", tenant_slug_hint=tenant_slug))
            flash(err or "Reset failed.", "error")
        return redirect(url_for("reset_password_page"))

    return render_template(
        "reset_password.html",
        reset_enabled=enabled,
        default_tenant_slug=DEFAULT_TENANT_SLUG,
    )


@app.route("/register", methods=["GET"])
def register_page():
    from plans_catalog import list_plans_public_payload

    if not REGISTRATION_ENABLED:
        return redirect(url_for("login_page"))
    if session.get("user_id"):
        return redirect(url_for("dashboard"))
    return render_template(
        "register.html",
        plans=list_plans_public_payload(),
        error=None,
        form=None,
    )


@app.route("/register", methods=["POST"])
def register_submit():
    from plans_catalog import list_plans_public_payload, normalize_plan_slug
    from services.tenant_provisioning import provision_new_organization

    if not REGISTRATION_ENABLED:
        abort(404)

    org_name = request.form.get("organization_name", "")
    org_slug = request.form.get("organization_slug", "")
    plan_slug = normalize_plan_slug(request.form.get("plan_slug", ""))
    admin_username = request.form.get("admin_username", "")
    admin_password = request.form.get("admin_password", "")
    admin_email = (request.form.get("admin_email") or "").strip()

    form_snapshot = {
        "organization_name": org_name,
        "organization_slug": org_slug,
        "plan_slug": plan_slug,
        "admin_username": admin_username,
        "admin_email": admin_email,
    }

    def rerender(msg: str):
        return (
            render_template(
                "register.html",
                plans=list_plans_public_payload(),
                error=msg,
                form=form_snapshot,
            ),
            422,
        )

    try:
        tenant = provision_new_organization(
            organization_name=org_name,
            organization_slug=org_slug,
            plan_slug=plan_slug,
            admin_username=admin_username,
            admin_password=admin_password,
            admin_email=admin_email or None,
        )
        return redirect(url_for("login_page", tenant_slug_hint=tenant.slug, registered="1"))
    except ValueError as ve:
        return rerender(str(ve))
    except Exception:
        logger.exception("registration failed")
        return rerender("Registration failed. Try again or contact support.")


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/app")
@login_required
def dashboard():
    root = request.url_root.rstrip("/")
    return render_template(
        "dashboard.html",
        username=g.current_user.username,
        tenant_slug=g.tenant.slug,
        current_tenant_id=g.tenant.id,
        app_origin=root,
        current_user_id=g.current_user.id,
        is_superuser=bool(getattr(g.current_user, "is_superuser", False)),
        can_manage_users=user_has_permission(g.current_user, "users:manage"),
        spa_tabs_enabled=True,
    )


def _lead_capture_page(*, kind: str, page_title: str, headline: str, intro: str):
    if request.method == "POST":
        if (request.form.get("_company_website") or "").strip():
            return redirect(url_for("lead_thanks_page", kind=kind))
        errors: dict[str, str] = {}
        name = (request.form.get("name") or "").strip()
        email = (request.form.get("email") or "").strip()
        company = (request.form.get("company") or "").strip()
        phone_raw = (request.form.get("phone") or "").strip()
        phone = phone_raw or None
        message = (request.form.get("message") or "").strip()
        if not name or len(name) > 255:
            errors["name"] = "Please enter your name (max 255 characters)."
        if not email or len(email) > 255 or "@" not in email:
            errors["email"] = "Please enter a valid email."
        if not company or len(company) > 255:
            errors["company"] = "Please enter your organisation name."
        if phone_raw and len(phone_raw) > 64:
            errors["phone"] = "Phone is too long."
        if not message or len(message) < 8:
            errors["message"] = "Please add a short message (at least a few words)."
        if len(message) > 8000:
            errors["message"] = "Message is too long (max 8000 characters)."
        if errors:
            return (
                render_template(
                    "lead_capture.html",
                    logged_in=bool(session.get("user_id")),
                    registration_enabled=REGISTRATION_ENABLED,
                    page_title=page_title,
                    headline=headline,
                    intro=intro,
                    form_kind=kind,
                    form_errors=errors,
                    form_values=request.form,
                ),
                422,
            )
        db.session.add(
            LeadInquiry(
                kind=kind,
                name=name,
                email=email,
                company=company,
                phone=phone,
                message=message,
            )
        )
        db.session.commit()
        logger.info("lead_inquiry submitted kind=%s email=%s", kind, email)
        return redirect(url_for("lead_thanks_page", kind=kind))
    return render_template(
        "lead_capture.html",
        logged_in=bool(session.get("user_id")),
        registration_enabled=REGISTRATION_ENABLED,
        page_title=page_title,
        headline=headline,
        intro=intro,
        form_kind=kind,
        form_errors=None,
        form_values=None,
    )


@app.route("/contact-sales", methods=["GET", "POST"])
def contact_sales_page():
    return _lead_capture_page(
        kind="contact_sales",
        page_title="Contact sales · Nexura",
        headline="Contact sales",
        intro="Tell us about your team and timing. We’ll follow up by email.",
    )


@app.route("/request-proposal", methods=["GET", "POST"])
def request_proposal_page():
    return _lead_capture_page(
        kind="request_proposal",
        page_title="Request proposal · Nexura",
        headline="Request a proposal",
        intro="Share scope, regions, and compliance needs. We’ll respond with next steps.",
    )


@app.route("/thanks")
def lead_thanks_page():
    kind = (request.args.get("kind") or "").strip()
    if kind not in ("contact_sales", "request_proposal"):
        kind = "contact_sales"
    return render_template(
        "lead_thanks.html",
        logged_in=bool(session.get("user_id")),
        registration_enabled=REGISTRATION_ENABLED,
        kind=kind,
    )


@app.route("/super/settings", methods=["GET", "POST"])
@login_required
@superuser_required
def super_settings_page():
    from services.marketing_settings import (
        MARKETING_SETTING_KEYS,
        get_super_admin_form_values,
        marketing_env_defaults,
        save_marketing_settings_from_form,
    )

    if request.method == "POST":
        from services.embed_cors_settings import save_embed_cors_from_form

        save_embed_cors_from_form(request.form.get("embed_cors_origins", ""))
        payload = {k: request.form.get(k, "") for k in MARKETING_SETTING_KEYS}
        save_marketing_settings_from_form(payload)
        flash(
            "Platform settings saved. Embed CORS updates apply immediately for /api/embed.",
            "success",
        )
        return redirect(url_for("super_settings_page"))

    from services.embed_cors_settings import (
        embed_cors_env_default_display,
        get_embed_cors_effective_raw,
    )

    return render_template(
        "super_settings.html",
        marketing=get_super_admin_form_values(),
        env_defaults=marketing_env_defaults(),
        embed_cors_origins=get_embed_cors_effective_raw(),
        embed_cors_env_hint=embed_cors_env_default_display(),
        username=g.current_user.username,
        tenant_slug=g.tenant.slug,
        is_superuser=True,
        spa_tabs_enabled=False,
        super_nav="settings",
        app_origin=request.url_root.rstrip("/"),
        leads=LeadInquiry.query.order_by(LeadInquiry.created_at.desc()).limit(100).all(),
    )


@app.route("/super/email", methods=["GET", "POST"])
@login_required
@superuser_required
def super_email_settings_page():
    from services.email_settings import (
        email_env_defaults,
        get_super_email_form_values,
        save_email_settings_from_form,
    )

    if request.method == "POST":
        payload = {
            "smtp_host": request.form.get("smtp_host", "").strip(),
            "smtp_port": request.form.get("smtp_port", "").strip(),
            "smtp_username": request.form.get("smtp_username", "").strip(),
            "smtp_password": request.form.get("smtp_password", "").strip(),
            "smtp_use_tls": "true" if request.form.get("smtp_use_tls") == "on" else "false",
            "smtp_use_ssl": "true" if request.form.get("smtp_use_ssl") == "on" else "false",
            "smtp_from_email": request.form.get("smtp_from_email", "").strip(),
            "email_password_reset_enabled": (
                "true" if request.form.get("email_password_reset_enabled") == "on" else "false"
            ),
        }
        save_email_settings_from_form(payload)
        flash("Email / SMTP settings saved.", "success")
        return redirect(url_for("super_email_settings_page"))

    return render_template(
        "super_email.html",
        email=get_super_email_form_values(),
        env_defaults=email_env_defaults(),
        username=g.current_user.username,
        tenant_slug=g.tenant.slug,
        is_superuser=True,
        spa_tabs_enabled=False,
        super_nav="email",
        app_origin=request.url_root.rstrip("/"),
    )


@app.route("/super/users")
@login_required
@superuser_required
def super_users_admin_page():
    return render_template(
        "super_users.html",
        username=g.current_user.username,
        tenant_slug=g.tenant.slug,
        current_user_id=g.current_user.id,
        is_superuser=True,
        spa_tabs_enabled=False,
        super_nav="users",
        app_origin=request.url_root.rstrip("/"),
    )


@app.route("/super/guides")
@login_required
@superuser_required
def super_guides_page():
    summary_html, deployment_html, guides_error = _load_operator_guides_docs()
    return render_template(
        "super_guides.html",
        summary_html=summary_html,
        deployment_html=deployment_html,
        guides_error=guides_error,
        username=g.current_user.username,
        tenant_slug=g.tenant.slug,
        is_superuser=True,
        spa_tabs_enabled=False,
        super_nav="guides",
        app_origin=request.url_root.rstrip("/"),
    )


@app.route("/super/technical")
@login_required
@superuser_required
def super_technical_page():
    technical_html, tech_err = _load_technical_reference_html()
    if tech_err:
        technical_html = f'<p class="muted" role="alert">{tech_err}</p>'
    return render_template(
        "super_technical.html",
        technical_html=technical_html,
        username=g.current_user.username,
        tenant_slug=g.tenant.slug,
        is_superuser=True,
        spa_tabs_enabled=False,
        super_nav="technical",
        app_origin=request.url_root.rstrip("/"),
    )


@app.route("/super/organisations")
@login_required
@superuser_required
def super_organisations_page():
    return render_template(
        "super_orgs.html",
        username=g.current_user.username,
        tenant_slug=g.tenant.slug,
        current_user_id=g.current_user.id,
        is_superuser=True,
        spa_tabs_enabled=False,
        super_nav="orgs",
        app_origin=request.url_root.rstrip("/"),
    )


@app.route("/api/super/tenants", methods=["GET"])
@login_required
@superuser_required
def api_super_list_tenants():
    from services import super_org_admin

    return jsonify({"tenants": super_org_admin.list_tenants_payload()})


@app.route("/api/super/tenants/<tenant_id>", methods=["GET"])
@login_required
@superuser_required
def api_super_get_tenant(tenant_id: str):
    from services import super_org_admin

    detail = super_org_admin.tenant_detail_payload(str(tenant_id))
    if not detail:
        return jsonify({"error": "Tenant not found"}), 404
    return jsonify(detail)


@app.route("/api/super/tenants/<tenant_id>", methods=["PATCH"])
@login_required
@superuser_required
def api_super_patch_tenant(tenant_id: str):
    from services import super_org_admin

    body = request.get_json(force=True, silent=True) or {}
    if not isinstance(body, dict):
        return jsonify({"error": "JSON body required"}), 400
    detail, err = super_org_admin.patch_tenant_super(str(tenant_id), body)
    if err:
        return jsonify({"error": err}), 400
    return jsonify(detail)


@app.route("/api/super/tenants/<tenant_id>/users", methods=["GET"])
@login_required
@superuser_required
def api_super_list_tenant_users(tenant_id: str):
    from services import super_org_admin

    users = super_org_admin.list_users_for_tenant(str(tenant_id))
    if users is None:
        return jsonify({"error": "Tenant not found"}), 404
    return jsonify({"users": users})


@app.route("/api/super/users/<user_id>", methods=["PATCH"])
@login_required
@superuser_required
def api_super_patch_user(user_id: str):
    from services import super_org_admin

    body = request.get_json(force=True, silent=True) or {}
    if not isinstance(body, dict):
        return jsonify({"error": "JSON body required"}), 400
    updated, err = super_org_admin.patch_user_super(
        str(user_id), body, str(g.current_user.id)
    )
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"user": updated})


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


@app.route("/api/public/plans", methods=["GET"])
def public_plans():
    from plans_catalog import list_plans_public_payload

    return jsonify({"plans": list_plans_public_payload()})


@app.route("/api/marketplace/agents", methods=["GET"])
def marketplace_agents_public():
    return jsonify({"agents": list_marketplace_payload()})


@app.route("/api/public/forgot-password", methods=["POST"])
def api_public_forgot_password():
    from services.password_reset_flow import request_otp_email

    body = request.get_json(force=True, silent=True) or {}
    tenant_slug = str(body.get("tenant_slug") or "").strip()
    email = str(body.get("email") or "").strip()
    if not tenant_slug or not email:
        return jsonify({"error": "tenant_slug and email are required"}), 400
    ok, msg = request_otp_email(tenant_slug, email)
    if not ok:
        return jsonify({"error": msg}), 503
    return jsonify({"ok": True, "message": msg}), 200


@app.route("/api/public/reset-password", methods=["POST"])
def api_public_reset_password():
    from services.password_reset_flow import complete_password_reset

    body = request.get_json(force=True, silent=True) or {}
    tenant_slug = str(body.get("tenant_slug") or "").strip()
    email = str(body.get("email") or "").strip()
    otp = str(body.get("otp") or "").strip()
    password = str(body.get("password") or "")
    if not tenant_slug or not email or not otp or not password:
        return (
            jsonify(
                {"error": "tenant_slug, email, otp, and password are required"},
            ),
            400,
        )
    ok, err = complete_password_reset(tenant_slug, email, otp, password)
    if ok:
        return jsonify({"ok": True}), 200
    return jsonify({"error": err}), 400


@app.route("/api/v1/tenant/subscription", methods=["GET"])
@login_required
def tenant_subscription():
    from services.plan_enforcement import subscription_payload

    return jsonify(subscription_payload(g.tenant))


@app.route("/api/v1/me/agent-preference", methods=["GET"])
@login_required
def get_my_agent_preference():
    from services.agent_preferences import get_preference

    return jsonify(get_preference(g.current_user.id))


@app.route("/api/v1/me/agent-preference", methods=["PUT"])
@login_required
def put_my_agent_preference():
    from services.agent_preferences import set_preference
    from services.plan_enforcement import agent_allowed_on_plan

    body = request.get_json(force=True, silent=True) or {}
    aid = str(body.get("agent_id") or "").strip().lower()
    cfg = body.get("config")
    if not aid:
        return jsonify({"error": "agent_id is required"}), 400
    if cfg is None:
        cfg = {}
    if not isinstance(cfg, dict):
        return jsonify({"error": "config must be an object"}), 400

    ok_choice, err = validate_agent_choice(aid)
    if not ok_choice:
        return jsonify({"error": err}), 400

    ok_plan, plan_err = agent_allowed_on_plan(g.tenant, aid)
    if not ok_plan:
        return jsonify({"error": plan_err}), 403

    saved = set_preference(str(g.current_user.id), aid, cfg)
    return jsonify(saved), 200


@app.route("/chat", methods=["POST"])
@login_required
@permission_required("chat:query")
def chat():
    from services.agent_preferences import get_preference
    from services.chat_execution import run_chat_turn
    from services.plan_enforcement import (
        agent_allowed_on_plan,
        chat_quota_blocked,
        record_successful_chat_turn,
    )

    payload = request.get_json(force=True, silent=True) or {}
    logger.info("Starting chat")
    chat_message = str(payload.get("chat_message", "")).strip()
    pref = get_preference(g.current_user.id)
    payload_agent = str(payload.get("agent_id") or "").strip().lower()
    agent_id = payload_agent or str(pref.get("agent_id") or "rag_document_qa").strip().lower()

    pref_cfg = dict(pref.get("config") or {})
    if not isinstance(pref_cfg, dict):
        pref_cfg = {}
    incoming_cfg = payload.get("agent_config")
    if isinstance(incoming_cfg, dict):
        merged_cfg = {**pref_cfg, **incoming_cfg}
    else:
        merged_cfg = pref_cfg

    raw_collections = payload.get("collection_ids")
    if isinstance(raw_collections, list):
        requested = tuple(str(x).strip() for x in raw_collections if str(x).strip())
    else:
        requested = ()

    normalized = normalize_collection_filter(str(g.tenant.id), requested)
    if requested and not normalized:
        return jsonify({"error": "Invalid collection_ids for this tenant"}), 400

    logger.info("Chat tenant=%s user=%s agent=%s", g.tenant.id, g.current_user.id, agent_id)

    blocked, qerr = chat_quota_blocked(g.tenant)
    if blocked:
        return jsonify({"error": qerr}), 429

    ok_plan, plan_err = agent_allowed_on_plan(g.tenant, agent_id)
    if not ok_plan:
        return jsonify({"error": plan_err}), 403

    try:
        result, err = run_chat_turn(
            tenant_id=str(g.tenant.id),
            user_id=str(g.current_user.id),
            session_id=str(g.current_user.id),
            agent_id=agent_id,
            merged_cfg=merged_cfg,
            allowed_collection_ids=normalized,
            chat_message=chat_message,
            llm_route=str(payload.get("llm_route", "platform_llm")),
            llm_config_ref=payload.get("llm_config_ref"),
            client_hint=payload.get("client_hint"),
        )
        if err:
            return jsonify({"error": err}), 400
        record_successful_chat_turn(str(g.tenant.id))
        return jsonify(result), 200
    except Exception as exc:
        logger.exception("chat failed")
        return jsonify({"error": str(exc)}), 500


@app.route("/api/embed/chat", methods=["POST"])
def embed_chat():
    """Cross-origin chat using tenant embed API key (Bearer or X-Nexura-Embed-Key)."""
    from services.chat_execution import run_chat_turn
    from services.embed_key_service import (
        authenticate_embed_key,
        default_agent_config,
        extract_embed_token_from_request,
        normalize_embed_collection_scope,
        parse_allowed_ids,
    )
    from services.plan_enforcement import (
        agent_allowed_on_plan,
        chat_quota_blocked,
        record_successful_chat_turn,
    )

    tok = extract_embed_token_from_request()
    row = authenticate_embed_key(tok)
    if not row:
        return jsonify({"error": "Invalid or inactive embed API key"}), 401

    origin_hdr = request.headers.get("Origin")
    from services.embed_cors_settings import validate_embed_post_origin

    if not validate_embed_post_origin(origin_hdr, row):
        return jsonify({"error": "Origin not allowed for this embed key"}), 403

    tenant_row = Tenant.query.filter_by(id=str(row.tenant_id)).first()
    if not tenant_row:
        return jsonify({"error": "Tenant not found"}), 500
    if not getattr(tenant_row, "is_active", True):
        return jsonify({"error": "Organisation suspended"}), 403

    payload = request.get_json(force=True, silent=True) or {}
    chat_message = str(payload.get("chat_message", "")).strip()

    key_cfg = default_agent_config(row)
    incoming_cfg = payload.get("agent_config")
    if isinstance(incoming_cfg, dict):
        merged_cfg = {**key_cfg, **incoming_cfg}
    else:
        merged_cfg = key_cfg

    agent_id = str(payload.get("agent_id") or row.default_agent_id or "rag_document_qa").strip().lower()

    raw_collections = payload.get("collection_ids")
    if isinstance(raw_collections, list):
        requested = tuple(str(x).strip() for x in raw_collections if str(x).strip())
    else:
        requested = ()

    allowed_from_key = parse_allowed_ids(row)
    normalized, scope_err = normalize_embed_collection_scope(
        str(row.tenant_id), allowed_from_key, requested
    )
    if scope_err:
        return jsonify({"error": scope_err}), 400

    chroma_targets = list_chroma_physical_names(str(row.tenant_id), normalized)
    logger.info(
        "embed_chat_scope tenant=%s key_id=%s resolved_collection_uuids=%s chroma_physical=%s requested_raw=%s key_restrict=%s",
        row.tenant_id,
        row.id,
        list(normalized),
        chroma_targets,
        list(requested),
        allowed_from_key,
    )

    visitor = str(payload.get("visitor_session") or "anon").strip()[:160] or "anon"
    session_key = f"embed:{row.id}:{visitor}"
    user_label = f"embed:{row.id}"

    logger.info("Embed chat tenant=%s key=%s agent=%s", row.tenant_id, row.id, agent_id)

    blocked, qerr = chat_quota_blocked(tenant_row)
    if blocked:
        return jsonify({"error": qerr}), 429

    ok_plan, plan_err = agent_allowed_on_plan(tenant_row, agent_id)
    if not ok_plan:
        return jsonify({"error": plan_err}), 403

    try:
        result, err = run_chat_turn(
            tenant_id=str(row.tenant_id),
            user_id=user_label,
            session_id=session_key,
            agent_id=agent_id,
            merged_cfg=merged_cfg,
            allowed_collection_ids=normalized,
            chat_message=chat_message,
            llm_route=str(payload.get("llm_route", "platform_llm")),
            llm_config_ref=payload.get("llm_config_ref"),
            client_hint=payload.get("client_hint"),
        )
        if err:
            return jsonify({"error": err}), 400
        record_successful_chat_turn(str(row.tenant_id))
        return jsonify(result), 200
    except Exception as exc:
        logger.exception("embed chat failed")
        return jsonify({"error": str(exc)}), 500


@app.route("/api/v1/embed-keys", methods=["GET"])
@login_required
@permission_required("embed:keys")
def list_embed_keys_route():
    from services.embed_key_service import list_embed_keys_payload

    return jsonify({"keys": list_embed_keys_payload(str(g.tenant.id))})


@app.route("/api/v1/embed-keys", methods=["POST"])
@login_required
@permission_required("embed:keys")
def create_embed_key_route():
    from services.embed_key_service import (
        create_embed_api_key,
        normalize_allowed_embed_origins_payload,
        parse_allowed_embed_origins,
        parse_allowed_ids,
    )
    from services.plan_enforcement import agent_allowed_on_plan, check_can_add_embed_key

    body = request.get_json(force=True, silent=True) or {}
    name = str(body.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400

    ok_key, key_err = check_can_add_embed_key(g.tenant)
    if not ok_key:
        return jsonify({"error": key_err}), 403

    daid = str(body.get("default_agent_id") or "").strip().lower()
    if daid:
        ok_agent, agent_err = validate_agent_choice(daid)
        if not ok_agent:
            return jsonify({"error": agent_err}), 400
        ok_plan, plan_err = agent_allowed_on_plan(g.tenant, daid)
        if not ok_plan:
            return jsonify({"error": plan_err}), 403

    dac = body.get("default_agent_config")
    if dac is not None and not isinstance(dac, dict):
        return jsonify({"error": "default_agent_config must be an object"}), 400

    embed_origins_kw: dict = {}
    if "allowed_embed_origins" in body:
        norm_o, oerr = normalize_allowed_embed_origins_payload(body.get("allowed_embed_origins"))
        if oerr:
            return jsonify({"error": oerr}), 400
        embed_origins_kw["allowed_embed_origins"] = norm_o

    try:
        row, secret = create_embed_api_key(
            str(g.tenant.id),
            name=name,
            allowed_collection_ids=body.get("allowed_collection_ids"),
            default_agent_id=daid or None,
            default_agent_config=dac if isinstance(dac, dict) else {},
            **embed_origins_kw,
        )
        db.session.commit()
        return (
            jsonify(
                {
                    "id": row.id,
                    "api_key": secret,
                    "key_prefix": row.key_prefix,
                    "allowed_collection_ids": parse_allowed_ids(row),
                    "allowed_embed_origins": parse_allowed_embed_origins(row),
                }
            ),
            201,
        )
    except ValueError as ve:
        db.session.rollback()
        return jsonify({"error": str(ve)}), 400


@app.route("/api/v1/embed-keys/<key_id>", methods=["PATCH"])
@login_required
@permission_required("embed:keys")
def patch_embed_key_route(key_id: str):
    from services.embed_key_service import parse_allowed_embed_origins, update_embed_key_origins

    body = request.get_json(force=True, silent=True) or {}
    if "allowed_embed_origins" not in body:
        return (
            jsonify(
                {
                    "error": "allowed_embed_origins required (JSON array of https:// origins, or [] for platform default)"
                }
            ),
            400,
        )

    ok, err = update_embed_key_origins(
        str(g.tenant.id), key_id, body.get("allowed_embed_origins")
    )
    if not ok:
        status = 404 if err == "Key not found" else 400
        return jsonify({"error": err or "Update failed"}), status

    row = ApiKey.query.filter_by(id=key_id, tenant_id=str(g.tenant.id)).first()
    return jsonify({"ok": True, "allowed_embed_origins": parse_allowed_embed_origins(row)}), 200


@app.route("/api/v1/embed-keys/<key_id>", methods=["DELETE"])
@login_required
@permission_required("embed:keys")
def revoke_embed_key_route(key_id: str):
    from services.embed_key_service import revoke_embed_api_key

    if revoke_embed_api_key(str(g.tenant.id), key_id):
        return jsonify({"ok": True}), 200
    return jsonify({"error": "Key not found"}), 404


@app.route("/upload-document", methods=["POST"])
@login_required
@permission_required("documents:write")
def upload_document():
    from services.plan_enforcement import check_can_add_collection

    try:
        file = request.files.get("file")
        collection_label = request.form.get("collection_name")
        module = request.form.get("module", "DEFAULT")

        if not file:
            return jsonify({"error": "No file uploaded"}), 400

        if not collection_label:
            return jsonify({"error": "Collection name is required"}), 400

        if not allowed_file(file.filename):
            return jsonify({"error": "Only PDF and TXT files are supported"}), 400

        tenant_id = str(g.tenant.id)
        coll = find_collection(tenant_id, collection_label)
        if not coll:
            if not user_has_permission(g.current_user, "collections:manage"):
                return jsonify({"error": "Unknown collection; Editor cannot auto-create"}), 404
            ok_col, cerr = check_can_add_collection(g.tenant)
            if not ok_col:
                return jsonify({"error": cerr}), 403
            coll = create_collection(tenant_id, collection_label)
            db.session.commit()

        filename = secure_filename(file.filename)
        document = Document(
            tenant_id=tenant_id,
            uploaded_by_id=g.current_user.id,
            original_filename=filename,
            storage_path="pending",
            mime_type=file.mimetype,
            module_tag=module,
        )
        document.collections.append(coll)
        db.session.add(document)
        db.session.flush()

        tenant_upload_dir = os.path.join(app.config["UPLOAD_FOLDER"], tenant_id)
        os.makedirs(tenant_upload_dir, exist_ok=True)
        file_path = os.path.join(tenant_upload_dir, f"{document.id}_{filename}")
        file.save(file_path)
        document.storage_path = file_path
        document.byte_size = os.path.getsize(file_path)

        try:
            result = ingest_document_file(
                file_path=file_path,
                tenant_id=tenant_id,
                collection=coll,
                document=document,
                module=module,
                actor_user_id=g.current_user.id,
            )
        except Exception:
            db.session.rollback()
            if os.path.isfile(file_path):
                try:
                    os.remove(file_path)
                except OSError:
                    pass
            raise

        db.session.commit()

        return jsonify(
            {
                "message": "Document uploaded and indexed successfully",
                "result": result,
            }
        )

    except Exception as e:
        logger.exception("upload failed")
        db.session.rollback()
        from services.openai_user_errors import format_openai_exception

        return jsonify({"error": format_openai_exception(e)}), 500


@app.route("/delete-document", methods=["DELETE"])
@login_required
@permission_required("documents:write")
def delete_document():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "JSON body required"}), 400

        collection_name = data.get("collection_name")
        file_name = data.get("file_name")

        if not collection_name or not file_name:
            return jsonify({"error": "collection_name and file_name are required"}), 400

        result = delete_document_for_tenant(
            tenant_id=str(g.tenant.id),
            collection_slug=collection_name,
            file_name=file_name,
        )

        coll_del = find_collection(str(g.tenant.id), collection_name)
        from services.kb_debug import record_kb_audit

        record_kb_audit(
            tenant_id=str(g.tenant.id),
            actor_user_id=g.current_user.id,
            event_type="document_deleted",
            message=f"Deleted document {file_name} from collection {collection_name}",
            collection_id=coll_del.id if coll_del else None,
            payload={"file_name": file_name, "collection_slug": collection_name},
        )
        db.session.commit()

        return jsonify(
            {
                "message": "Document deleted successfully",
                "result": result,
            }
        )

    except ValueError as ve:
        return jsonify({"error": str(ve)}), 404
    except Exception as e:
        logger.exception("delete failed")
        return jsonify({"error": str(e)}), 500


@app.route("/api/collections", methods=["GET"])
@login_required
@permission_required("documents:read")
def get_collections():
    try:
        return jsonify({"collections": list_collections_payload(str(g.tenant.id))})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/documents", methods=["GET"])
@login_required
@permission_required("documents:read")
def get_documents():
    try:
        collection_name = request.args.get("collection_name")

        if not collection_name:
            return jsonify({"error": "collection_name is required"}), 400

        return jsonify(
            {"documents": list_documents_db(str(g.tenant.id), collection_name)}
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/chunks", methods=["GET"])
@login_required
@permission_required("documents:read")
def get_chunks():
    try:
        collection_name = request.args.get("collection_name")
        file_name = request.args.get("file_name")

        if not collection_name or not file_name:
            return jsonify({"error": "collection_name and file_name are required"}), 400

        return jsonify(
            {
                "chunks": preview_chunks_db(
                    str(g.tenant.id), collection_name, file_name
                )
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/v1/kb/documents/<document_id>/index-debug", methods=["GET"])
@login_required
@permission_required("documents:read")
def kb_document_index_debug(document_id: str):
    from services.kb_debug import (
        build_document_index_debug,
        get_document_for_tenant,
        resolve_kb_admin_tenant_id,
    )

    is_super = bool(getattr(g.current_user, "is_superuser", False))
    tid, err = resolve_kb_admin_tenant_id(
        current_tenant_id=str(g.tenant.id),
        is_superuser=is_super,
        requested_tenant_id=request.args.get("tenant_id"),
    )
    if err:
        return jsonify({"error": err}), 400

    doc = get_document_for_tenant(document_id, tid)
    if not doc:
        return jsonify({"error": "Document not found"}), 404

    return jsonify(build_document_index_debug(doc))


@app.route("/api/v1/kb/retrieval-probe", methods=["POST"])
@login_required
@permission_required("documents:read")
def kb_retrieval_probe():
    from collections_service import list_chroma_physical_names, normalize_collection_filter

    from services.kb_debug import merged_similarity_probe, record_kb_audit, resolve_kb_admin_tenant_id

    body = request.get_json(force=True, silent=True) or {}
    query = (body.get("query") or "").strip()
    if not query:
        return jsonify({"error": "query is required"}), 400

    is_super = bool(getattr(g.current_user, "is_superuser", False))
    req_tid = body.get("tenant_id") if isinstance(body.get("tenant_id"), str) else None
    tid, err = resolve_kb_admin_tenant_id(
        current_tenant_id=str(g.tenant.id),
        is_superuser=is_super,
        requested_tenant_id=req_tid,
    )
    if err:
        return jsonify({"error": err}), 400

    raw_scope = body.get("collection_slugs") or body.get("collection_ids")
    allowed: tuple[str, ...] = ()
    if isinstance(raw_scope, list) and raw_scope:
        allowed = normalize_collection_filter(tid, tuple(str(x) for x in raw_scope))
        if not allowed:
            return jsonify({"error": "No matching collections for scope"}), 400

    names = list_chroma_physical_names(tid, allowed)
    try:
        k_per = int(body.get("k_per_collection") or 8)
    except (TypeError, ValueError):
        k_per = 8
    hits = merged_similarity_probe(names, query, k_per_collection=max(2, min(k_per, 24)))

    record_kb_audit(
        tenant_id=tid,
        actor_user_id=g.current_user.id,
        event_type="retrieval_probe",
        message=f"Retrieval probe — {len(hits)} hit(s)",
        payload={
            "query_preview": query[:240],
            "collections_requested": raw_scope if isinstance(raw_scope, list) else None,
            "chroma_collections": names,
            "hit_count": len(hits),
        },
    )
    db.session.commit()

    return jsonify(
        {
            "query": query,
            "tenant_id": tid,
            "chroma_collections_searched": names,
            "hits": hits,
            "hint_if_empty": (
                "No chunks matched. Confirm collection scope matches embed key restrictions, "
                "documents finished indexing (see Index debug), and embeddings are configured."
                if not hits
                else None
            ),
        }
    )


@app.route("/api/v1/kb/audit-events", methods=["GET"])
@login_required
@permission_required("documents:read")
def kb_audit_events_list():
    from services.kb_debug import audit_events_payload, resolve_kb_admin_tenant_id

    is_super = bool(getattr(g.current_user, "is_superuser", False))
    tid, err = resolve_kb_admin_tenant_id(
        current_tenant_id=str(g.tenant.id),
        is_superuser=is_super,
        requested_tenant_id=request.args.get("tenant_id"),
    )
    if err:
        return jsonify({"error": err}), 400

    try:
        lim = int(request.args.get("limit", "40"))
    except ValueError:
        lim = 40

    return jsonify({"tenant_id": tid, "events": audit_events_payload(tid, limit=lim)})


@app.route("/api/agents", methods=["GET"])
@login_required
@permission_required("documents:read")
def list_agents():
    return jsonify({"agents": agent_registry.list_agents()}), 200


@app.route("/api/v1/roles", methods=["GET"])
@login_required
@permission_required("users:manage")
def list_tenant_roles():
    roles = (
        Role.query.filter_by(tenant_id=g.tenant.id)
        .order_by(Role.name.asc())
        .all()
    )
    return jsonify({"roles": [r.name for r in roles]})


@app.route("/api/v1/users", methods=["GET"])
@login_required
@permission_required("users:manage")
def list_tenant_users():
    users = User.query.filter_by(tenant_id=g.tenant.id).order_by(User.username).all()
    return jsonify(
        [
            {
                "id": u.id,
                "username": u.username,
                "email": u.email,
                "is_active": u.is_active,
                "roles": [r.name for r in u.roles],
            }
            for u in users
        ]
    )


@app.route("/api/v1/users", methods=["POST"])
@login_required
@permission_required("users:manage")
def create_tenant_user():
    from services.plan_enforcement import check_can_add_user

    body = request.get_json(force=True, silent=True) or {}
    username = str(body.get("username", "")).strip()
    password = str(body.get("password", ""))
    email_raw = str(body.get("email") or "").strip()
    role_names = body.get("roles") or ["Viewer"]
    if not isinstance(role_names, list):
        role_names = ["Viewer"]

    if not username or not password:
        return jsonify({"error": "username and password are required"}), 400

    ok_user, uerr = check_can_add_user(g.tenant)
    if not ok_user:
        return jsonify({"error": uerr}), 403

    if User.query.filter_by(tenant_id=g.tenant.id, username=username).first():
        return jsonify({"error": "User already exists"}), 409

    roles = Role.query.filter(
        Role.tenant_id == g.tenant.id,
        Role.name.in_(role_names),
    ).all()
    if not roles:
        return jsonify({"error": "No valid roles matched"}), 400

    user = User(
        tenant_id=g.tenant.id,
        username=username,
        password_hash=generate_password_hash(password),
        email=(email_raw[:255] if email_raw else None),
        is_active=True,
    )
    user.roles = roles
    db.session.add(user)
    db.session.commit()
    return jsonify({"id": user.id, "username": user.username}), 201


@app.route("/api/v1/users/<user_id>", methods=["PATCH"])
@login_required
@permission_required("users:manage")
def patch_tenant_user(user_id: str):
    body = request.get_json(force=True, silent=True) or {}
    user = User.query.filter_by(id=user_id, tenant_id=g.tenant.id).first()
    if not user:
        return jsonify({"error": "User not found"}), 404

    if "is_active" in body:
        active = bool(body["is_active"])
        if not active and user.id == g.current_user.id:
            return jsonify({"error": "Cannot disable yourself"}), 400
        user.is_active = active

    db.session.commit()
    return jsonify({"id": user.id, "is_active": user.is_active}), 200


@app.route("/api/v1/users/<user_id>/roles", methods=["PUT"])
@login_required
@permission_required("users:manage")
def put_tenant_user_roles(user_id: str):
    body = request.get_json(force=True, silent=True) or {}
    role_names = body.get("roles")
    if not isinstance(role_names, list) or not role_names:
        return jsonify({"error": "roles array required"}), 400

    user = User.query.filter_by(id=user_id, tenant_id=g.tenant.id).first()
    if not user:
        return jsonify({"error": "User not found"}), 404

    uniq = list(dict.fromkeys(role_names))
    roles = Role.query.filter(
        Role.tenant_id == g.tenant.id,
        Role.name.in_(uniq),
    ).all()
    if len(roles) != len(uniq):
        return jsonify({"error": "One or more unknown roles"}), 400

    if user.id == g.current_user.id and not roles_include_users_manage(roles):
        return jsonify(
            {"error": "You cannot remove your own access to manage users"}
        ), 400

    user.roles = roles
    db.session.commit()
    return jsonify({"id": user.id, "roles": [r.name for r in user.roles]}), 200


if __name__ == "__main__":
    if ADMIN_BOOTSTRAP_PASSWORD == "changeme":
        logger.warning(
            "Default ADMIN_BOOTSTRAP_PASSWORD in use; set ADMIN_BOOTSTRAP_USERNAME/PASSWORD."
        )
    app.run(host="0.0.0.0", port=PORT, debug=True)
