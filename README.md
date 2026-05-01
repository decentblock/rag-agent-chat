# Nexura (latest_rag_application)

Multi-tenant RAG platform with Flask: tenant-scoped collections, RBAC, Chroma embeddings, LangChain chat, and a **registry-based agent marketplace** (four built-in agents).

---

## Documentation

| Document | Purpose |
|----------|---------|
| **[docs/FEATURES_SUMMARY.md](docs/FEATURES_SUMMARY.md)** | One-page product / capability overview |
| **[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)** | Step-by-step deployment (env, Gunicorn, nginx, systemd, backups) |
| **[docs/TECHNICAL.md](docs/TECHNICAL.md)** | Full technical reference (architecture, config, APIs, agents, security) |

After you run the app, these render at **`/docs`** (install the `markdown` package for HTML rendering; otherwise raw Markdown is shown with a hint).

---

## Quick setup

1. **Python 3** virtualenv recommended.

   ```bash
   python3 -m venv venv
   source venv/bin/activate   # Windows: venv\Scripts\activate
   ```

2. **Install dependencies**

   ```bash
   pip install -r requirements-dev.txt
   ```

   Set **`OPENAI_API_KEY`** (and optionally **`OPENAI_MODEL`**, **`EMEDDING_MODEL`**, **`DATABASE_URL`**, **`SESSION_SECRET`**, **`ADMIN_BOOTSTRAP_PASSWORD`**, **`EMBED_CORS_ORIGINS`** for third-party hosted widgets).

3. **Run**

   ```bash
   python app.py
   ```

   Defaults: **http://127.0.0.1:5000/** — landing at `/`, console at `/app` after login.

4. **First login**

   Seed creates tenant slug **`default`** (override with `DEFAULT_TENANT_SLUG`) and admin **`ADMIN_BOOTSTRAP_USERNAME`** / **`ADMIN_BOOTSTRAP_PASSWORD`** (`changeme` until changed).

---

## Key endpoints (overview)

- **`GET /health`** — Liveness  
- **`GET /api/marketplace/agents`** — Public catalog JSON  
- **`POST /login`** — Form: `tenant_slug`, `username`, `password`  
- **`POST /api/embed/chat`** — JSON + embed API key header (see **`docs/TECHNICAL.md`**).  
- **`/static/embed/nexura-chat.js`** — Customer-site widget (snippet in console **Embed** tab).

See **`docs/TECHNICAL.md`** for every route, permission, and request/response shape.

---

## Project layout (selected)

| Path | Role |
|------|------|
| `app.py` | Flask routes (`/chat`, `/api/embed/chat`, embed key CRUD, uploads, …) |
| `config.py` | Environment-driven settings (`EMBED_CORS_ORIGINS`, …) |
| `models.py` | SQLAlchemy schema (`ApiKey`, …) |
| `seed_database.py` | Permissions (`embed:keys`), roles, bootstrap admin |
| `agent_catalog.py` | Marketplace metadata |
| `agents/` | Registry + built-in agents |
| `services/chat_execution.py` | Shared `run_chat_turn` for session + embed chat |
| `services/embed_key_service.py` | Mint / verify embed API keys |
| `static/embed/nexura-chat.js` | Customer-site widget |
| `docs/` | FEATURES_SUMMARY, DEPLOYMENT, TECHNICAL |

---

## Legacy note

Older README fragments referred to a simpler single-tenant RAG service. This tree is the **multi-tenant Nexura** stack; ignore any stale paths or env-only login references outside this file.
