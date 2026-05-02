# Nexura — technical documentation

This document describes the **latest_rag_application** codebase: architecture, configuration, data model, security, RAG pipeline, agents, and every HTTP route.

---

## Table of contents

1. [Architecture overview](#1-architecture-overview)  
2. [Technology stack](#2-technology-stack)  
3. [Runtime bootstrap](#3-runtime-bootstrap)  
4. [Configuration reference](#4-configuration-reference)  
5. [Data model (SQLAlchemy)](#5-data-model-sqlalchemy)  
6. [Authentication & sessions](#6-authentication--sessions)  
7. [Principal loading](#7-principal-loading)  
8. [RBAC](#8-rbac)  
9. [Multi-tenancy & collections](#9-multi-tenancy--collections)  
10. [Chroma physical naming](#10-chroma-physical-naming)  
11. [Document ingestion](#11-document-ingestion)  
12. [Retrieval & chat (RAG flow)](#12-retrieval--chat-rag-flow)  
13. [Conversation memory](#13-conversation-memory)  
14. [Agents framework](#14-agents-framework)  
15. [Marketplace catalog](#15-marketplace-catalog)  
16. [User agent preferences](#16-user-agent-preferences)  
17. [HTTP API reference](#17-http-api-reference)  
    - [§17.16 — Platform super APIs](#1716-platform-super-apis-apisuper)  
    - [Marketplace agents — operator summary](#marketplace-agents--operator-summary-super-admin)  
18. [HTML / UI routes](#18-html--ui-routes)  
19. [Static frontend](#19-static-frontend)  
20. [Logging](#20-logging)  
21. [Security checklist](#21-security-checklist)  
22. [Extension points](#22-extension-points)  
23. [Deployment (companion guide)](#23-deployment-companion-guide)  
24. [Plans, registration & quotas](#24-plans-registration--quotas)  

---

## 1. Architecture overview

High-level request flow:

```
Browser (console) ──► Flask (app.py)
              ├── before_request: load_principal() → g.current_user, g.tenant
              ├── Session cookie (user_id, tenant_slug)
              ├── Routes: HTML pages + JSON APIs
              │
              ├── SQLAlchemy ──► SQLite (default) or Postgres (DATABASE_URL)
              │
              └── Chat / agents ──► services.chat_execution.run_chat_turn()
                        └── agent_registry.invoke()
                              └── rag_shared / variants ──► answer_flow.get_answer()

Customer site widget ──► POST /api/embed/chat (+ Flask-CORS on /api/embed/*)
              └── Authorization: Bearer <ApiKey> → tenant + collection scope from api_keys row
```

- **Authoritative business data** (users, tenants, collections, documents) lives in the **SQL database**.  
- **Embeddings** live in **Chroma** on disk (`CHROMA_DB_FILE_PATH`).  
- **Agents** are Python classes registered at import time in **`agents/bootstrap.py`**.  
- **Marketplace presentation** (`agent_catalog.py`) is merged with the live registry for API/UI lists.  
- **Embeddable chat** uses **`ApiKey`** rows + **`POST /api/embed/chat`**; **`flask-cors`** exposes **`/api/embed/*`** according to **`EMBED_CORS_ORIGINS`** (`config.py`).

---

## 2. Technology stack

| Layer | Components |
|-------|------------|
| Web | Flask, Jinja2 templates, static JS/CSS, **`flask-cors`** (embed routes only) |
| ORM | Flask-SQLAlchemy, SQLAlchemy 2.x |
| Auth | Werkzeug password hashing, Flask sessions; **embed API keys** (`services/embed_key_service.py`) for `/api/embed/chat` |
| LLM / RAG | LangChain, LangChain-OpenAI, ChromaDB |
| Embeddings | Configurable via `clients.py` / OpenAI (`EMEDDING_MODEL`) |
| Documents | PyPDF, text loaders, RecursiveCharacterTextSplitter |

Dependencies are listed in **`requirements-dev.txt`**.

---

## 3. Runtime bootstrap

On application load (`app.py`):

1. Flask app created; `SESSION_SECRET`, `SQLALCHEMY_DATABASE_URI` set.  
2. `db.init_app(app)`, `register_principal_loader(app)`.  
3. **`flask_cors.CORS`** registered for **`/api/embed/*`** using **`EMBED_CORS_ORIGINS`**.  
4. `register_builtin_agents(replace=True)` registers all built-in agents.  
5. **`init_database()`** runs: `db.create_all()`, **`_ensure_tenant_plan_columns()`** (adds **`plan_slug`**, **`usage_chat_month`**, **`usage_chat_count`**, and — when missing — **`tenants.is_active`**, **`billing_contact_email`**, **`payment_provider_customer_id`**, **`notes`**, **`allowed_agent_ids_json`** on SQLite / Postgres), **`_ensure_api_keys_columns()`** (adds embed-related **`api_keys`** columns such as **`default_agent_id`**, **`agent_config_json`**, **`key_prefix`** when missing), **`_ensure_user_is_superuser_column()`** (adds **`users.is_superuser`** when missing), then **`seed_if_needed(...)`** (permissions including **`embed:keys`**, default tenant, roles, bootstrap admin, default collection; **`grant_embed_keys_to_existing_editors`** backfills Editors created before that permission existed). **`system_settings`** rows override landing marketing values when present — see **`services/marketing_settings.py`**.  

The dev server entrypoint warns if `ADMIN_BOOTSTRAP_PASSWORD == "changeme"`.

---

## 4. Configuration reference

All keys live in **`config.py`** unless noted. Environment variables override defaults.

| Symbol | Env var | Default / notes |
|--------|---------|------------------|
| `OPENAI_API_KEY` | `OPENAI_API_KEY` | Empty string — must be set for LLM/embeddings |
| `OPENAI_API_BASE` | `OPENAI_API_BASE` | Empty — set to an **OpenAI-compatible** base URL if public **`api.openai.com`** is blocked (corporate gateway); LangChain passes this as **`base_url`** |
| `OPENAI_MODEL` | `OPENAI_MODEL` | `gpt-4.1-mini` |
| `EMEDDING_MODEL` | `EMEDDING_MODEL` | `text-embedding-3-small` (note typo `EMEDDING` in code) |
| `SEARCH_K` | `SEARCH_K` | `3` — retrieval breadth (used in RAG layer) |
| `LOG_DIR` | `LOG_DIR` | `<project>/logs` |
| `PORT` | `PORT` | `5000` |
| `CHROMA_DB_DIR` | `CHROMA_DB_DIR` | `<project>/chroma-db` |
| `CHROMA_DB_FILE_PATH` | `CHROMA_DB_FILE_PATH` | Same as dir by default; Chroma persist path |
| `DEFAULT_COLLECTION_NAME` | — | Legacy placeholder; empty |
| `DEFAULT_TENANT_ID` | `DEFAULT_TENANT_ID` | `default` — comment references migration |
| `VERIFY_SSL` | `VERIFY_SSL` | `false` — when **false**, **`clients.get_llm` / `get_embeddings`** pass **`httpx.Client(verify=False)`** to LangChain (fixes **`CERTIFICATE_VERIFY_FAILED`** behind TLS proxies); set **`true`** when connections should use default certificate verification |
| `SESSION_SECRET` | `SESSION_SECRET` | Dev fallback string — **set in production** |
| `ADMIN_BOOTSTRAP_USERNAME` | `ADMIN_BOOTSTRAP_USERNAME` | `admin` |
| `ADMIN_BOOTSTRAP_PASSWORD` | `ADMIN_BOOTSTRAP_PASSWORD` | `changeme` |
| `DATABASE_URL` | `DATABASE_URL` | `sqlite:///<project>/rag_platform.db` |
| `DEFAULT_TENANT_SLUG` | `DEFAULT_TENANT_SLUG` | `default` |
| `REGISTRATION_ENABLED` | `REGISTRATION_ENABLED` | `true` — when enabled, **`GET`/`POST /register`** allow creating a new **`Tenant`** + first admin; disable with `false` / `0` / `no` |
| `EMBED_CORS_ORIGINS` | `EMBED_CORS_ORIGINS` | Default **`*`**. For production embeds, set a comma-separated list of allowed **`Origin`** values (e.g. `https://www.customer.com,https://customer.com`). Applies only to **`/api/embed/*`** (methods **`POST`**, **`OPTIONS`**); headers allowed include **`Content-Type`**, **`Authorization`**, **`X-Nexura-Embed-Key`**. |
| `BOOTSTRAP_SUPERUSER` | `BOOTSTRAP_SUPERUSER` | `false` — when **`true`**, the seeded bootstrap admin (**`ADMIN_BOOTSTRAP_*`**) gets **`users.is_superuser=True`** so they can open **`/super/settings`**, **`/super/organisations`**, **`/super/guides`**, and **`/super/technical`** |
| `MARKETING_PRICE_*` | `MARKETING_PRICE_STARTER_DISPLAY`, `MARKETING_PRICE_GROWTH_MONTHLY`, `MARKETING_PRICE_GROWTH_ANNUAL_EQUIV` | Strings shown on the landing pricing cards (defaults in **`config.py`**) |
| `MARKETING_GROWTH_*_BLURB` | `MARKETING_GROWTH_MONTHLY_BLURB`, `MARKETING_GROWTH_ANNUAL_BLURB` | Short subtitles under Growth tier pricing |
| — | — | **Contact sales** / **Request proposal** on the landing page link to **`/contact-sales`** and **`/request-proposal`** (forms → **`lead_inquiries`**). There are no URL env vars for those CTAs. |

Upload directory: **`uploads/`**, with per-tenant subfolders `uploads/<tenant_id>/`.

---

## 5. Data model (SQLAlchemy)

Defined in **`models.py`**.

### 5.1 `tenants`

| Column | Purpose |
|--------|---------|
| `id` | UUID string PK |
| `name`, `slug` | Display name; unique `slug` for login |
| `created_at` | UTC timestamp |
| `plan_slug` | Subscription tier key (`starter`, `growth`, `enterprise`) — see **`plans_catalog.py`** |
| `usage_chat_month` | UTC `YYYY-MM` for monthly chat counter rollover |
| `usage_chat_count` | Successful chat turns counted this month when plan has a **`monthly_chat_quota`** |
| `is_active` | When **`false`**, the organisation is **suspended**: tenant users cannot authenticate or load a principal; **`POST /api/embed/chat`** returns **403**; session is cleared if they were already logged in |
| `billing_contact_email` | Optional billing contact (stub until payment integration) |
| `payment_provider_customer_id` | Optional external customer reference (e.g. Stripe id) |
| `notes` | Free-form operator notes |
| `allowed_agent_ids_json` | Optional JSON array of **`agent_id`** strings — narrows which agents are effective for this tenant (see **`resolved_allowed_agent_ids`** in **`services/plan_enforcement.py`**); **`NULL`/unset** means “follow plan catalogue only” |

### 5.2 `permissions`

Global permission catalog (`code` unique), e.g. `documents:read`, `chat:query`, `*`.

### 5.3 `roles`

Per-tenant roles (`tenant_id` + `name` unique). Many-to-many with `permissions` via **`role_permissions`**.

### 5.4 `users`

| Column | Purpose |
|--------|---------|
| `tenant_id`, `username` | Unique together |
| `password_hash` | Werkzeug hash; nullable if external auth added later |
| `email`, `is_active` | Profile / gate login |
| `is_superuser` | When **`true`**, platform operator — console links under **Organisations**, **Platform settings**, **Product & deployment**, **Technical reference**; unrelated to tenant RBAC roles |
| `roles` | Many-to-many via **`user_roles`** |

### 5.5 `collections`

Logical KB buckets per tenant (`name`, `slug`, unique per tenant).

### 5.6 `documents`

File metadata: `original_filename`, `storage_path`, `mime_type`, `byte_size`, `status`, `module_tag`. Many-to-many with **`collections`** via **`document_collections`**.

### 5.7 `user_agent_preferences`

One row per user (PK `user_id`): `agent_id`, `config_json` (JSON text), `updated_at`.

### 5.8 `system_settings`

Key/value overrides for platform-wide UI (landing marketing). **`key`** PK (strings such as **`marketing_price_starter_display`** — see **`MARKETING_SETTING_KEYS`** in **`services/marketing_settings.py`**), **`value`** text, **`updated_at`**. Empty form fields on **`POST /super/settings`** delete the row so env defaults apply again.

### 5.9 `lead_inquiries`

Public marketing form posts (**`kind`**: `contact_sales` or `request_proposal`): **`name`**, **`email`**, **`company`**, optional **`phone`**, **`message`**, **`created_at`**. Listed on **`/super/settings`** for superusers.

### 5.10 `api_keys`

Tenant-scoped **embed / integration keys**: `name`, unique **`key_prefix`** (public lookup fragment), **`key_hash`** (Werkzeug hash of full secret), optional **`allowed_collection_ids_json`** (restrict retrieval; omit or empty = all tenant collections), optional **`default_agent_id`** / **`agent_config_json`** for widget defaults, **`is_active`**.

Issued secrets look like **`nxemb_<12 hex>_<48 hex>`** — shown **once** at creation. **`POST /api/embed/chat`** validates the Bearer / header token against this table (`authenticate_embed_key`).

**Schema upgrades:** SQLAlchemy **`create_all()`** does not migrate every additive change automatically beyond **`_ensure_tenant_plan_columns()`**, **`_ensure_api_keys_columns()`**, and **`_ensure_user_is_superuser_column()`**. New tables such as **`system_settings`** and **`lead_inquiries`** appear on **`create_all()`** for new databases; for existing deployments without a table, restart after deploy or run migrations. For other columns, use a fresh DB for development or run explicit **`ALTER TABLE`** / migrations in production.

---

## 6. Authentication & sessions

### 6.1 Login (`POST /login`)

Form fields:

- `tenant_slug` — resolves `Tenant`. **Suspended** tenants (**`tenants.is_active = false`**) cause authentication to fail (same as unknown tenant / bad password).  
- `username`, `password` — `User` in that tenant.  
- Optional `remember` — `on` sets `session.permanent` (14-day lifetime from `permanent_session_lifetime`).  
- Optional `next` — internal redirect path (must start with `/`, not `//`).

On success: `session.clear()`, then `session["user_id"]`, `session["tenant_slug"]`.

On failure: HTTP **422**, re-rendered login with error.

### 6.2 Logout (`POST /logout`)

Clears session; redirects to **`/`** (landing).

### 6.3 API vs HTML unauthenticated behaviour

**`login_required`** (`auth.py`):

- For `/api/*`, `/chat`, `/upload-document`, `/delete-document`: **401** JSON `{"error":"Unauthorized"}`.  
- Else: redirect to `/login?next=...`.

### 6.4 Platform superuser (`superuser_required`)

Users with **`users.is_superuser`** may:

- **`GET`/`POST /super/settings`** — marketing overrides + lead inbox  
- **`GET /super/organisations`** — console UI to list tenants, edit **plan**, **suspension**, **billing stubs**, **per-tenant agent allowlist**, and toggle **user `is_active`** (cross-tenant)  
- **`GET /super/guides`** — **`FEATURES_SUMMARY.md`** + **`DEPLOYMENT.md`**  
- **`GET /super/technical`** — **`TECHNICAL.md`**  

JSON APIs under **`/api/super/…`** (same guards) are documented in §17.16. Non-superusers receive **403** JSON on API-style paths or a redirect to the dashboard for HTML.

Grant the flag via **`BOOTSTRAP_SUPERUSER=true`** on first seed, or **`UPDATE users SET is_superuser = 1 WHERE …`** on existing databases.

---

## 7. Principal loading

**`principal.register_principal_loader`**: before each request:

- Sets `g.current_user = None`, `g.tenant = None`.  
- If `session["user_id"]` present, loads `User` by id. **Inactive users** or **missing users** → **`session.pop("user_id")`** and return (logged out).  
- Loads **`Tenant`** by **`user.tenant_id`**. **Inactive tenant** (**`tenants.is_active = false`**) → **`session.pop("user_id")`** and return — avoids redirect loops when an org is suspended after login.  
- Otherwise sets `g.current_user` and `g.tenant`.

---

## 8. RBAC

### 8.1 Permission codes (seeded)

From **`seed_database.PERMISSION_CODES`**:

- `*`, `documents:read`, `documents:write`, `collections:manage`, `chat:query`, `users:manage`, **`embed:keys`**

### 8.2 Role matrix (seeded)

| Role | Permissions |
|------|-------------|
| Admin | `*` |
| Editor | `documents:read`, `documents:write`, `collections:manage`, `chat:query`, **`embed:keys`** |
| Viewer | `documents:read`, `chat:query` |

### 8.3 Checking permissions

- **`user_has_permission(user, code)`** — true if any role yields `code` or `*`.  
- **`permission_required(code)`** — returns **403** JSON with `required_permission` if missing.

---

## 9. Multi-tenancy & collections

- **`collections_service.find_collection(tenant_id, slug_or_label)`** — matches slug or name within tenant.  
- **`create_collection`** — slugifies label; de-duplicates slug with numeric suffix.  
- **`normalize_collection_filter(tenant_id, requested_tuple)`** — maps each entry (collection UUID or slug) to canonical **collection UUID strings**; unknown IDs omitted.  
- **`list_chroma_physical_names(tenant_id, allowed_collection_ids)`** — if tuple empty, loads **all** tenant collections; else filters by UUID/slug membership then maps to Chroma names.

Upload behaviour (`upload_document`): if collection missing, **Editors without `collections:manage`** get **404** “cannot auto-create”; users with **`collections:manage`** create the collection.

---

## 10. Chroma physical naming

**`chroma_util.chroma_collection_name(tenant_id, collection_id)`** produces:

```text
rag_<tenant_id_without_dashes>_<collection_id_without_dashes>
```

Names are lowercased. Hyphens are removed from tenant and collection IDs before concatenation, so physical names stay stable and tenant-scoped.

---

## 11. Document ingestion

**`rag_ingestion.load_and_chunk`**:

- `.txt` → `TextLoader`; `.pdf` → `PyPDFLoader`.  
- Metadata on each LangChain doc: `module`, `source` (basename).  
- Split: `RecursiveCharacterTextSplitter` chunk_size **1000**, overlap **200**.

**`insert_into_chroma`**:

- Uses **`get_embeddings()`** from `clients.py`.  
- `Chroma.from_documents(..., persist_directory=CHROMA_DB_FILE_PATH)`.  
- **`persist()`** called after insert.

**`ingest_document_file`** adds metadata per chunk: `tenant_id`, `document_id`, `collection_id`, `source`, `module`.

---

## 12. Retrieval & chat (RAG flow)

**`answer_flow.get_answer`** → **`rag_flow.run_rag_only`**:

1. **`merged_similarity_documents(chroma_collection_names, question)`** — similarity search across named physical collections.  
2. Builds tenant/session-scoped chain via **`get_rag_chain_for_tenant`**.  
3. **`run_chain_with_memory_tenant`** — runs LLM with conversation memory.  
4. Response text + citation list built from doc metadata `source` (deduped).

Chat route passes **question** that may include prefixed blocks from agents (preferences + workflow). See agents section.

---

## 13. Conversation memory

**`memory_store.py`** — in-process **`ConversationBufferWindowMemory`** keyed by **`tenant_id:session_id`**. Console **`POST /chat`** uses **`session_id = str(current_user.id)`**, so memory is per logged-in user within the process. **`POST /api/embed/chat`** uses **`session_id = embed:<api_key_id>:<visitor_session>`** (widget sends **`visitor_session`** or defaults internally), so each visitor partition is separate per embed key.

**Note:** Multi-worker deployments do not share this memory unless replaced with Redis or similar.

---

## 14. Agents framework

### 14.1 Contracts (`agents/base.py`)

- **`AgentInvocationContext`** — `tenant_id`, `user_id`, `session_id`, `allowed_collection_ids`, `llm_route`, `llm_config_ref`, `metadata`.  
- **`AgentRunInput`** — `messages`, `raw_prompt`, `extra`.  
- **`AgentRunResult`** — `text`, `citations`, `usage`, `extra`.  
- **`Agent`** protocol — `agent_id`, `version`, `description`, `run(ctx, inp)`.

### 14.2 Registry (`agents/registry.py`)

- **`registry.register(agent, replace=False)`** — lowercased `agent_id`.  
- **`invoke(agent_id, ctx, inp)`** — dispatch.

### 14.3 Registration (`agents/bootstrap.py`)

Registers instances of:

- `RagDocumentQaAgent`  
- `ResearchSynthesizerAgent`  
- `SupportRouterAgent`  
- `SqlAnalystAgent`  

### 14.4 Shared RAG runner (`agents/builtin/rag_shared.py`)

1. **`extract_user_question`** — last user message from `messages` or `raw_prompt`.  
2. **`apply_user_config_hints`** — reads `ctx.metadata["agent_config"]`; applies `response_language`, `user_instructions` → wraps as `[Agent preferences]` + `[User question]`.  
3. **`compose_question`** — prepends `[Agent workflow]\n{workflow_block}\n\n` when non-empty.  
4. **`run_tenant_rag`** — validates collections, resolves Chroma names, calls **`get_answer`**.

### 14.5 Built-in behaviour summary

| `agent_id` | Workflow flavour | Extra `agent_config` keys (beyond shared) |
|------------|------------------|---------------------------------------------|
| `rag_document_qa` | None (plain grounded Q&A) | — |
| `research_synthesizer` | Neutral synthesis | `synthesis_focus` |
| `support_router` | Support / macros | `brand_voice` |
| `sql_analyst` | SELECT-only SQL hints | `sql_dialect`, `schema_context` |

Shared keys documented in catalog: `user_instructions`, `response_language`.

---

## 15. Marketplace catalog

**`agent_catalog.py`** defines **`MARKETPLACE_AGENTS`**: presentation fields (`name`, `tagline`, `description`, `category`, `icon`, `badge`, `available`, `config_fields`).

**`list_marketplace_payload()`** augments each row with:

- `registered_version` — from registry agent `version` if present  
- `installed` — `registry.get(id)` exists **and** `available` is true  

**`validate_agent_choice(agent_id)`** — ensures catalog entry exists, `available`, and registry has implementation.

Public JSON: **`GET /api/marketplace/agents`** → `{ "agents": [ ... ] }`.

---

## 16. User agent preferences

**`services/agent_preferences.py`**:

- **`get_preference(user_id)`** — defaults to `{ "agent_id": "rag_document_qa", "config": {} }`.  
- **`set_preference(user_id, agent_id, config)`** — upserts `UserAgentPreference`, stores `config` as JSON object.

Chat merges saved `config` with optional per-request `agent_config` (request overrides keys).

---

## 17. HTTP API reference

Unless stated, JSON bodies use `Content-Type: application/json`. Authenticated routes expect session cookie from login.

### 17.1 `GET /health`

- **Auth:** none  
- **Response:** `200` `{ "status": "ok" }`

### 17.2 `GET /api/marketplace/agents`

- **Auth:** none  
- **Response:** `200` `{ "agents": list_marketplace_payload() }`

### 17.2a `GET /api/public/plans`

- **Auth:** none  
- **Response:** `200` `{ "plans": list_plans_public_payload() }` — marketing-safe limits copy for registration UI

### 17.3 `GET /api/v1/me/agent-preference`

- **Auth:** session  
- **Response:** `200` `{ "agent_id": string, "config": object }`

### 17.3a `GET /api/v1/tenant/subscription`

- **Auth:** session  
- **Response:** `200` — **`subscription_payload(tenant)`**: current **`plan_slug`**, **`limits`** (caps + effective **`allowed_agent_ids`** — `null` means all agents allowed for that plan tier), boolean **`agents_overridden_by_tenant`** when **`allowed_agent_ids_json`** is set on the tenant, and **`usage`** (monthly chat count, seat/collection/embed-key counts). Effective agents come from **`resolved_allowed_agent_ids`** (plan defaults intersected with optional tenant JSON whitelist when the plan defines a finite list).

### 17.4 `PUT /api/v1/me/agent-preference`

- **Auth:** session  
- **Body:** `{ "agent_id": string (required), "config": object (optional, default {}) }`  
- **Validation:** `validate_agent_choice` · plan allow-list via **`agent_allowed_on_plan`**  
- **Errors:** `400` if missing `agent_id`, invalid `config` type, or invalid agent · **`403`** if agent not allowed on tenant plan  
- **Response:** `200` saved preference object  

#### `POST /api/embed/chat`

- **Auth:** `Authorization: Bearer <nxemb_…>` **or** header **`X-Nexura-Embed-Key: <nxemb_…>`**  
- **Body:** same shape as **`POST /chat`** (`chat_message` required; optional `agent_id`, `agent_config`, `collection_ids`, `visitor_session`, `llm_route`, …).  
- **Agent defaults:** if `agent_id` omitted, uses the key’s **`default_agent_id`** (or **`rag_document_qa`**). Config merges key **`agent_config_json`** with request **`agent_config`**.  
- **Collections:** if the key defines **`allowed_collection_ids`**, retrieval is limited to that set; when the client omits `collection_ids`, **all allowed key collections** are used (not the whole tenant). Requested IDs must intersect the key allow-list.  
- **Memory:** `session_id` is derived as `embed:<key_id>:<visitor_session>` (default visitor label `anon`) so LangChain memory partitions per visitor per key.  
- **Plan / metering:** same **`Tenant`** as the key — inactive tenant → **`403`** `Organisation suspended`; **`chat_quota_blocked`** → **`429`**, **`agent_allowed_on_plan`** → **`403`**; **`record_successful_chat_turn`** after a successful **`run_chat_turn`**.  
- **Errors:** `401` invalid key · **`403`** suspended org / agent not enabled · `400` validation / scope  

#### `GET /api/v1/embed-keys` · `POST /api/v1/embed-keys` · `DELETE /api/v1/embed-keys/<key_id>`

- **Auth:** session · **Permission:** **`embed:keys`** (Admin has `*`; Editors receive **`embed:keys`** from seed / backfill).  
- **`GET`:** **`200`** `{ "keys": [ { id, name, key_prefix, is_active, allowed_collection_ids, default_agent_id, default_agent_config, created_at }, ... ] }` — response omits secret hashes and never returns full **`api_key`**.  
- **`POST` body:** `{ "name": string (required), "allowed_collection_ids"?: string[] (collection UUIDs; omit or empty = unrestricted tenant scope), "default_agent_id"?: string, "default_agent_config"?: object }` — **`POST`** also enforces **`check_can_add_embed_key`** (**`403`** at **`max_embed_keys`**) and **`agent_allowed_on_plan`** for **`default_agent_id`** when set (**`403`**).  
- **`POST` response `201`:** `{ id, api_key, key_prefix, allowed_collection_ids }` — **`api_key`** plaintext **shown once**.  
- **`DELETE`:** **`200`** `{ ok: true }` — sets **`is_active = false`** (soft revoke).  

Static widget script: **`GET /static/embed/nexura-chat.js`** — register with **`defer`**, **`data-api-key`**, **`data-base-url`**; optional **`data-title`**, **`data-accent`** (6-digit `#RRGGBB`). Snippet is generated on the console **Embed** tab (**`/app`**).

### 17.5 `POST /chat`

- **Auth:** session  
- **Permission:** `chat:query`  
- **Plan:** **`chat_quota_blocked`** → **`429`** · **`agent_allowed_on_plan`** → **`403`**  
- **Metering:** **`record_successful_chat_turn`** after a successful **`run_chat_turn`** when the plan defines **`monthly_chat_quota`**  
- **Body:**

```json
{
  "chat_message": "string (required)",
  "agent_id": "optional override; default from saved preference",
  "agent_config": { "optional": "merged over saved config" },
  "collection_ids": ["uuid-or-slug", "..."],
  "llm_route": "optional, default platform_llm",
  "llm_config_ref": "optional",
  "client_hint": "optional → metadata.payload_hint"
}
```

- **Behaviour:**  
  - Resolves `agent_id` from body or DB preference (fallback `rag_document_qa`).  
  - Merges configs (request wins on key collision).  
  - `collection_ids` normalized; empty tuple → agent retrieves across **all** tenant collections (see `list_chroma_physical_names`).  
  - If non-empty `collection_ids` provided but none resolve → **400** `Invalid collection_ids for this tenant`.  
- **Success:** `200`  

```json
{
  "answer": "string",
  "citations": ["source strings"],
  "agent_id": "string",
  "usage": {},
  "extra": {}
}
```

- **Errors:** `400` validation; `401`; `403`; `429` quota; `500` with message

### 17.6 `POST /upload-document`

- **Auth:** session  
- **Permission:** `documents:write`  
- **Content-Type:** `multipart/form-data`  
- **Fields:**  
  - `file` — PDF or TXT  
  - `collection_name` — required  
  - `module` — optional, default `DEFAULT`  
- **Success:** `200` JSON with `message`, `result` (chunk counts, ids, chroma name, etc.)  
- **Errors:** `400` validation; `404` unknown collection for Editor; **`403`** when creating a new collection would exceed **`max_collections`**; `500`

### 17.7 `DELETE /delete-document`

- **Auth:** session  
- **Permission:** `documents:write`  
- **Body:** `{ "collection_name": "...", "file_name": "..." }`  
- **Success:** `200` message + result  
- **Errors:** `400`, `404` ValueError → JSON error; `500`

### 17.8 `GET /api/collections`

- **Auth:** session  
- **Permission:** `documents:read`  
- **Response:** `{ "collections": [ { id, slug, name, chroma_collection }, ... ] }`

### 17.9 `GET /api/documents`

- **Auth:** session  
- **Permission:** `documents:read`  
- **Query:** `collection_name` **required**  
- **Response:** `{ "documents": [...] }` or `400` if missing param

### 17.10 `GET /api/chunks`

- **Auth:** session  
- **Permission:** `documents:read`  
- **Query:** `collection_name`, `file_name` **required**  
- **Response:** `{ "chunks": [...] }`

### 17.11 `GET /api/agents`

- **Auth:** session  
- **Permission:** `documents:read` (current app grouping)  
- **Response:** `{ "agents": [ { agent_id, version, description }, ... ] }` from registry

### 17.11a `GET /api/v1/roles`

- **Auth:** session  
- **Permission:** `users:manage`  
- **Response:** `{ "roles": ["Admin", "Editor", "Viewer", ...] }` — role names for this tenant

### 17.12 `GET /api/v1/users`

- **Auth:** session  
- **Permission:** `users:manage`  
- **Response:** JSON array of `{ id, username, email, is_active, roles }`

### 17.13 `POST /api/v1/users`

- **Auth:** session  
- **Permission:** `users:manage`  
- **Body:** `{ "username", "password", "roles": ["Viewer", ...], "email"?: string }`  
- **Success:** `201` `{ id, username }`  
- **Errors:** `400` missing fields / no roles matched; **`403`** at **`max_users`**; `409` duplicate user

### 17.14 `PATCH /api/v1/users/<user_id>`

- **Body:** optional `{ "is_active": boolean }`  
- **Cannot** disable self  
- **Response:** `200` `{ id, is_active }` or `404`

### 17.15 `PUT /api/v1/users/<user_id>/roles`

- **Body:** `{ "roles": ["Admin", ...] }` — unique role names in tenant  
- **Response:** `200` `{ id, roles }` or `400`/`404`  
- **Guard:** cannot remove your own **`users:manage`** / **`*`** access (must keep at least one role that grants user administration).

### 17.16 Platform super APIs (`/api/super/*`)

All routes: **session** cookie · **`superuser_required`** ( **`403`** if not platform superuser).

| Method | Path | Body / notes | Response |
|--------|------|----------------|----------|
| `GET` | `/api/super/tenants` | — | `{ "tenants": [ { id, name, slug, plan_slug, is_active, users_count, created_at }, ... ] }` |
| `GET` | `/api/super/tenants/<tenant_id>` | — | `{ "tenant": { … }, "plan_allowed_agent_ids": list \| null, "plan_options": [ { slug, label, allowed_agent_ids }, … ] }` — each **`plan_options`** row mirrors **`plans_catalog`** for that slug ( **`allowed_agent_ids`** may be **`null`** = all agents). **`plan_allowed_agent_ids`** reflects the tenant’s **current** plan. |
| `PATCH` | `/api/super/tenants/<tenant_id>` | JSON: optional **`name`** (display name, non-empty string), **`plan_slug`**, **`is_active`**, **`billing_contact_email`**, **`payment_provider_customer_id`**, **`notes`**, **`allowed_agent_ids`** (`null` = clear tenant override; array is stored **after** dropping any ids not allowed by the **new** plan finite list—same rule as enforcement) | Updated detail object · **`400`** on unknown plan, empty name, or bad payload |
| `GET` | `/api/super/tenants/<tenant_id>/users` | — | `{ "users": [ { id, username, email, is_active, is_superuser, roles }, … ] }` |
| `PATCH` | `/api/super/users/<user_id>` | `{ "is_active"?: boolean, "password"?: string }` — password minimum **8** characters (same as self-service signup); hashes with Werkzeug (`generate_password_hash`). Cannot disable **your own** account (**`400`**). | `{ "user": { id, tenant_id, username, is_active, password_updated?: boolean } }` — **`password_updated`** is **`true`** when **`password`** was present in the body |

Implementation: **`services/super_org_admin.py`**. Console page **`/super/organisations`** uses **`static/js/super_orgs.js`**.

#### Marketplace agents — operator summary (super admin)

Use this when explaining **how marketplace rows relate to live chat** and **what you can customise per organisation** from **`/super/organisations`**.

1. **Catalog vs runnable code** — **`agent_catalog.MARKETPLACE_AGENTS`** drives listing copy, categories, and **`config_fields`** for the UI. **`GET /api/marketplace/agents`** merges that with the **registry** (see **§15**): each row is **`installed`** only when **`available`** is true **and** an **`Agent`** with the same **`agent_id`** was registered at startup (**`agents/bootstrap.py`** → **`registry.register`**).

2. **How tenants use agents** — In-app chat picks **`agent_id`** (and merges **`config`**) from **`UserAgentPreference`** unless the request overrides (**§16**, **`PUT /api/v1/me/agent-preference`**). **Embed** widgets default from **`ApiKey.default_agent_id`** and **`agent_config_json`**, merged with per-request JSON. Execution always goes through **`services/chat_execution.run_chat_turn`** → **`registry.invoke`** after **`plan_enforcement.agent_allowed_on_plan`** rejects disallowed ids.

3. **What you control as platform operator**  
   - **Plan** (**`plan_slug`** on the tenant) — each tier’s **`allowed_agent_ids`** in **`plans_catalog.PLANS`** is either a **finite list** (e.g. Starter often **`["rag_document_qa"]`**) or **`null`** meaning **all installed** marketplace agents for that tier (**§24**).  
   - **Per-org agent allowlist** — **`PATCH`** body field **`allowed_agent_ids`** persists **`tenants.allowed_agent_ids_json`**. **`resolved_allowed_agent_ids`** (**`services/plan_enforcement.py`**) combines plan + tenant rules: finite plan list ⇒ **intersection** with the tenant list; plan **`null`** ⇒ tenant list is the whitelist (**empty array ⇒ no agents**). **`null`** in the PATCH clears the tenant override so the plan alone applies. The **Agents** card on **`/super/organisations`** mirrors this; rows are **disabled** when the agent is not allowed by the **current** plan or not **installed** on this server.

4. **Personalisation (beyond the allowlist)** — **Per-user**: saved **`agent_id`** + **`config`** (**§16**). **Per embed key**: **`default_agent_id`** + **`agent_config_json`**. There is **no** dedicated tenant-wide “default agent / default config” column today; org-level shaping is **which agents are allowed** plus downstream user/key preferences.

5. **Shipping a new agent** — Follow **§22 (Extension points), item 1**: implement **`Agent`**, **`registry.register`** in **`agents/bootstrap.py`**, add a **`MARKETPLACE_AGENTS`** entry with the same **`agent_id`** and **`available: True`**. Optionally add **`available: False`** rows as roadmap cards without code. If **Starter** (or any tier with a finite list) should expose the new agent, append its **`agent_id`** to that plan’s **`allowed_agent_ids`** in **`plans_catalog.py`**.

Cross-references: marketplace metadata **§15**, preferences **§16**, enforcement details **§24**, **`list_marketplace_payload`** / **`validate_agent_choice`** in **`agent_catalog.py`**.

---

## 18. HTML / UI routes

| Route | Method | Guard | Purpose |
|-------|--------|-------|---------|
| `/` | GET | — | Landing + marketplace preview |
| `/docs` | GET | — | **Swagger UI** (OpenAPI) — public API reference only |
| `/api/openapi.json` | GET | — | OpenAPI 3 document for API explorer |
| `/super/guides` | GET | `login_required`, **`superuser_required`** | **`FEATURES_SUMMARY.md`** + **`DEPLOYMENT.md`** |
| `/super/technical` | GET | `login_required`, **`superuser_required`** | **`TECHNICAL.md`** (full operator reference) |
| `/login` | GET | — | Login form (`next`, default tenant hint) |
| `/login` | POST | — | Submit credentials |
| `/register` | GET | — | Organisation signup form (**404** if **`REGISTRATION_ENABLED`** false) |
| `/register` | POST | — | Provision tenant + first admin (**422** validation; **`abort(404)`** when disabled) |
| `/logout` | POST | — | Clear session → `/` |
| `/super/settings` | GET/POST | `login_required`, **`superuser_required`** | Platform marketing overrides + lead inbox |
| `/super/organisations` | GET | `login_required`, **`superuser_required`** | Cross-tenant org console (plans, suspension, billing stubs, agents, users) |
| `/app` | GET | `login_required` | Dashboard console (Overview, Agents, Chat, Knowledge base, **Embed**, **Team** when `users:manage`) |

---

## 19. Static frontend

- **`static/css/design-system.css`** — tokens, buttons, forms  
- **`static/css/app.css`** — console layout  
- **`static/css/landing.css`** — marketing  
- **`static/css/docs.css`** — documentation typography  
- **`static/js/app.js`** — dashboard tabs, marketplace, chat, library, **embed key CRUD + snippet UI**  
- **`static/js/super_orgs.js`** — platform **Organisations** console (**`/super/organisations`**)  
- **`static/embed/nexura-chat.js`** — customer-site floating chat widget (fetches **`POST /api/embed/chat`**)  

Templates: **`templates/base.html`**, **`landing.html`**, **`login.html`**, **`register.html`**, **`dashboard.html`** (includes **`nexura-console-bootstrap`**), **`docs.html`** (Swagger UI only), **`super_settings.html`**, **`super_orgs.html`**, **`super_guides.html`**, **`super_technical.html`**.

Backend modules (selected): **`services/chat_execution.py`** (`run_chat_turn`), **`services/embed_key_service.py`**, **`services/agent_preferences.py`**, **`services/plan_enforcement.py`**, **`services/super_org_admin.py`**, **`services/tenant_provisioning.py`**, **`plans_catalog.py`**.

---

## 20. Logging

**`logging_setup.logger`** used in `app.py` for chat and upload/delete failures. Log directory from **`LOG_DIR`**.

---

## 21. Security checklist

1. Set **`SESSION_SECRET`** and **`ADMIN_BOOTSTRAP_PASSWORD`** in production.  
2. Use **HTTPS** so session cookies are not leaked on networks.  
3. Rotate **`OPENAI_API_KEY`** and restrict DB file permissions / use Postgres.  
4. Treat **`/api/marketplace/agents`** as public marketing data only.  
5. **`uploads/`** and **`chroma-db/`** contain tenant data — backup and ACL accordingly.  
6. Replace in-memory **`memory_store`** if horizontally scaling workers.  
7. **Embed:** set **`EMBED_CORS_ORIGINS`** to an explicit allow-list of customer **`Origin`** values (avoid **`*`** on the public internet). Revoke compromised **`ApiKey`** rows immediately (**DELETE `/api/v1/embed-keys/<id>`**). Prefer **`allowed_collection_ids`** on keys to limit retrieval blast radius.  
8. **Embed secrets** are bearer tokens — anyone with **`nxemb_…`** can chat within that key’s scope; never commit keys to git or expose them in client-side source beyond the hosted snippet pattern (rotate if leaked).

---

## 22. Extension points

1. **New agent:** implement `Agent`, register in **`agents/bootstrap.py`**, add **`MARKETPLACE_AGENTS`** row with matching `agent_id` and `available`.  
2. **New permission:** add code in **`seed_database.PERMISSION_CODES`** and **`ROLE_MATRIX`**, migrate DB or re-seed carefully.  
3. **API keys:** tenant **`ApiKey`** rows power **`POST /api/embed/chat`**; tune **`EMBED_CORS_ORIGINS`** for customer domains.  
4. **Billing:** map Growth/Enterprise tiers to metering (tokens, storage) externally. **`tenants.billing_contact_email`** / **`payment_provider_customer_id`** are operator-editable stubs until a gateway is integrated.  
5. **Platform operators:** protect **`users.is_superuser`** accounts; **`PATCH /api/super/*`** can change another tenant’s **`plan_slug`**, suspend organisations, and disable users — rely on **`SESSION_SECRET`**, HTTPS, and DB access controls.  

---

## 23. Deployment (companion guide)

Step-by-step instructions for installing dependencies, configuring environment variables, running under **Gunicorn**, placing **nginx** in front, **systemd** supervision, backups, optional containers, and a **[DigitalOcean (Droplet) walkthrough](DEPLOYMENT.md#digitalocean-droplet-deployment)** are maintained in **`docs/DEPLOYMENT.md`**, rendered with **`docs/FEATURES_SUMMARY.md`** for platform superusers at **`/super/guides`**. The **HTTP API** is **Swagger UI** on public **`/docs`** (spec **`/api/openapi.json`**). This **`TECHNICAL.md`** file is served at **`/super/technical`**. Organisation administration UI lives at **`/super/organisations`**; REST endpoints are §17.16.

---

## 24. Plans, registration & quotas

- **Catalog:** **`plans_catalog.PLANS`** defines **`starter`**, **`growth`**, **`enterprise`** with optional caps (**`max_users`**, **`monthly_chat_quota`**, **`max_collections`**, **`max_embed_keys`**) and optional **`allowed_agent_ids`** (`None` = all installed marketplace agents for that tier).  
- **Tenant overrides:** **`tenants.allowed_agent_ids_json`** (optional) stores a JSON array of **`agent_id`** strings. **`resolved_allowed_agent_ids`** in **`services/plan_enforcement.py`** applies it on top of the plan: if the plan has a finite allowlist, the effective set is the **intersection**; if the plan allows all agents (`None`), the tenant list is the whitelist (an empty array blocks every agent). **`GET /api/v1/tenant/subscription`** exposes **`limits.agents_overridden_by_tenant`** when the JSON column is set. **`PATCH /api/super/tenants/<id>`** drops any submitted ids outside the plan’s finite allowlist before saving. The **`/super/organisations`** UI lists marketplace agents (**`available`**); agents **not on the plan** or **not installed** on the server appear **disabled** until the plan changes or the agent is deployed.  
- **Suspension:** **`tenants.is_active = false`** suspends the organisation (login denied, principal cleared with **`session.pop("user_id")`**, embed chat **403**). Managed via **`/super/organisations`** or **`PATCH /api/super/tenants/<id>`**.  
- **Provisioning:** **`services/tenant_provisioning.provision_new_organization`** creates **`Tenant`**, clones **`ROLE_MATRIX`** roles for that tenant only, creates the first **Admin** user, **`ensure_default_collection`**, and commits.  
- **Enforcement:** **`services/plan_enforcement.py`** — **`subscription_payload`**, **`resolved_allowed_agent_ids`**, **`agent_allowed_on_plan`**, **`chat_quota_blocked`**, **`record_successful_chat_turn`**, **`check_can_add_user`**, **`check_can_add_collection`**, **`check_can_add_embed_key`**. Wired in **`app.py`** for **`PUT /api/v1/me/agent-preference`**, **`POST /chat`**, **`POST /api/embed/chat`**, **`POST /api/v1/users`**, **`POST /api/v1/embed-keys`**, and collection auto-create on **`POST /upload-document`**.  
- **Registration:** **`REGISTRATION_ENABLED`** (`config.py`) gates **`/register`** and marketing links. **`GET /api/public/plans`** lists safe plan metadata for the signup form.  

---

*Generated to match the codebase layout described herein; if behaviour diverges in your branch, prefer source files as ground truth.*
