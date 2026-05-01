import os
from datetime import timedelta
from pathlib import Path

from flask import (
    Flask,
    abort,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_cors import CORS
from werkzeug.security import generate_password_hash
from werkzeug.utils import secure_filename

from agents import (
    register_builtin_agents,
    registry as agent_registry,
)
from auth import login_required, safe_next_path
from auth_service import authenticate_user
from collections_service import (
    create_collection,
    find_collection,
    list_collections_payload,
    normalize_collection_filter,
)
from config import (
    ADMIN_BOOTSTRAP_PASSWORD,
    ADMIN_BOOTSTRAP_USERNAME,
    DATABASE_URL,
    DEFAULT_TENANT_SLUG,
    EMBED_CORS_ORIGINS,
    PORT,
    REGISTRATION_ENABLED,
    SESSION_SECRET,
)
from extensions import db
from logging_setup import logger
from models import Document, Role, Tenant, User
from principal import register_principal_loader
from rbac import permission_required, user_has_permission
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


def _embed_cors_origins():
    raw = (EMBED_CORS_ORIGINS or "").strip()
    if raw == "*":
        return "*"
    parts = [x.strip() for x in raw.split(",") if x.strip()]
    return parts if parts else "*"


CORS(
    app,
    resources={
        r"/api/embed/*": {
            "origins": _embed_cors_origins(),
            "methods": ["POST", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization", "X-Nexura-Embed-Key"],
            "max_age": 86400,
        }
    },
)

register_builtin_agents(replace=True)

from agent_catalog import list_marketplace_payload, validate_agent_choice  # noqa: E402

_PROJECT_ROOT = Path(__file__).resolve().parent


def _load_rendered_docs():
    """Return (summary_html, technical_html, deployment_html, error_message).

    error_message is set only when required Markdown files are missing. If the ``markdown``
    package is not installed, raw Markdown is shown escaped inside ``<pre>`` blocks.
    """
    import html as html_module

    docs_dir = _PROJECT_ROOT / "docs"
    summary_path = docs_dir / "FEATURES_SUMMARY.md"
    technical_path = docs_dir / "TECHNICAL.md"
    deployment_path = docs_dir / "DEPLOYMENT.md"
    required = (summary_path, technical_path, deployment_path)
    if not all(p.is_file() for p in required):
        return None, None, None, (
            "Missing one or more of: docs/FEATURES_SUMMARY.md, docs/TECHNICAL.md, docs/DEPLOYMENT.md"
        )

    summary_raw = summary_path.read_text(encoding="utf-8")
    technical_raw = technical_path.read_text(encoding="utf-8")
    deployment_raw = deployment_path.read_text(encoding="utf-8")

    try:
        import markdown
    except ImportError:
        note = (
            '<p class="muted"><strong>Note:</strong> Install the <code>markdown</code> package '
            "for formatted docs (<code>pip install markdown</code>). Showing raw Markdown.</p>"
        )
        esc_summary = html_module.escape(summary_raw)
        esc_technical = html_module.escape(technical_raw)
        esc_deploy = html_module.escape(deployment_raw)
        return (
            note + f'<pre class="docs-fallback">{esc_summary}</pre>',
            f'<pre class="docs-fallback">{esc_technical}</pre>',
            f'<pre class="docs-fallback">{esc_deploy}</pre>',
            None,
        )

    md = markdown.Markdown(
        extensions=[
            "markdown.extensions.extra",
            "markdown.extensions.nl2br",
            "markdown.extensions.sane_lists",
        ]
    )
    summary_html = md.convert(summary_raw)
    md.reset()
    technical_html = md.convert(technical_raw)
    md.reset()
    deployment_html = md.convert(deployment_raw)
    return summary_html, technical_html, deployment_html, None


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

    for sql in stmts:
        db.session.execute(text(sql))
    if stmts:
        db.session.commit()


def init_database() -> None:
    with app.app_context():
        db.create_all()
        _ensure_tenant_plan_columns()
        _ensure_api_keys_columns()
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
    return render_template(
        "landing.html",
        logged_in=bool(session.get("user_id")),
        marketplace_agents=list_marketplace_payload(),
        registration_enabled=REGISTRATION_ENABLED,
    )


@app.route("/docs")
def docs_page():
    summary_html, technical_html, deployment_html, docs_error = _load_rendered_docs()
    return render_template(
        "docs.html",
        summary_html=summary_html,
        technical_html=technical_html,
        deployment_html=deployment_html,
        docs_error=docs_error,
    )


@app.route("/login", methods=["GET"])
def login_page():
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
    )


@app.route("/login", methods=["POST"])
def login_submit():
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
        ),
        422,
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
        app_origin=root,
    )


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

    tenant_row = Tenant.query.filter_by(id=str(row.tenant_id)).first()
    if not tenant_row:
        return jsonify({"error": "Tenant not found"}), 500

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
    from services.embed_key_service import create_embed_api_key, parse_allowed_ids
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

    try:
        row, secret = create_embed_api_key(
            str(g.tenant.id),
            name=name,
            allowed_collection_ids=body.get("allowed_collection_ids"),
            default_agent_id=daid or None,
            default_agent_config=dac if isinstance(dac, dict) else {},
        )
        db.session.commit()
        return (
            jsonify(
                {
                    "id": row.id,
                    "api_key": secret,
                    "key_prefix": row.key_prefix,
                    "allowed_collection_ids": parse_allowed_ids(row),
                }
            ),
            201,
        )
    except ValueError as ve:
        db.session.rollback()
        return jsonify({"error": str(ve)}), 400


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


@app.route("/api/agents", methods=["GET"])
@login_required
@permission_required("documents:read")
def list_agents():
    return jsonify({"agents": agent_registry.list_agents()}), 200


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

    user.roles = roles
    db.session.commit()
    return jsonify({"id": user.id, "roles": [r.name for r in user.roles]}), 200


if __name__ == "__main__":
    if ADMIN_BOOTSTRAP_PASSWORD == "changeme":
        logger.warning(
            "Default ADMIN_BOOTSTRAP_PASSWORD in use; set ADMIN_BOOTSTRAP_USERNAME/PASSWORD."
        )
    app.run(host="0.0.0.0", port=PORT, debug=True)
