# Nexura — deployment guide (step-by-step)

This guide walks you from a clean machine to a running Nexura instance, then outlines production hardening. Paths assume the project root is **`latest_rag_application/`** (where **`app.py`** lives).

---

## Quick checklist (end-to-end)

1. Clone repo → **`cd latest_rag_application`**
2. **`python3 -m venv .venv`** → **`source .venv/bin/activate`**
3. **`pip install -r requirements-dev.txt`** (+ **`gunicorn`** for production)
4. Create **`logs/`**, **`chroma-db/`**, **`uploads/`** (or set **`LOG_DIR`** / **`CHROMA_DB_FILE_PATH`** to mounted paths)
5. Export **`OPENAI_API_KEY`**, **`SESSION_SECRET`**, strong **`ADMIN_BOOTSTRAP_PASSWORD`**, **`EMBED_CORS_ORIGINS`** (not `*` in production)
6. If your network blocks **`api.openai.com`**, set **`OPENAI_API_BASE`** to an approved OpenAI-compatible URL or deploy where embeddings are allowed (see §Step 5)
7. Optional: **`DATABASE_URL`** for Postgres
8. **`python app.py`** or **`gunicorn … app:app`** — wait for **`init_database()`** (tables + seed + best-effort schema patches)
9. **`curl http://127.0.0.1:$PORT/health`** → `{"status":"ok"}`
10. Log in at **`/login`** (seeded **`default`** tenant) **or** register an org at **`/register`** when **`REGISTRATION_ENABLED=true`**

---

## Table of contents

1. [Before you start](#before-you-start)  
2. [Step 1 — Get the code](#step-1--get-the-code)  
3. [Step 2 — Virtual environment](#step-2--create-a-virtual-environment)  
4. [Step 3 — Dependencies](#step-3--install-python-dependencies)  
5. [Step 4 — Disk layout](#step-4--choose-where-state-lives-on-disk)  
6. [Step 5 — Environment variables](#step-5--configure-environment-variables)  
7. [Step 6 — PostgreSQL](#step-6--use-postgresql-optional-but-typical-for-production)  
    - [PostgreSQL on this Droplet (Ubuntu)](#postgresql-installed-on-this-droplet-ubuntu--digitalocean)  
8. [Step 7 — First start & login](#step-7--first-start-database-bootstrap)  
9. [Optional — Embed widget](#optional--customer-site-embed-widget)  
10. [Step 8 — Gunicorn](#step-8--run-behind-gunicorn-production-app-server)  
11. [Step 9 — nginx / TLS](#step-9--reverse-proxy-and-tls-nginx-example)  
12. [Step 10 — Supervision](#step-10--process-supervision)  
13. [Step 11 — Security](#step-11--security-checklist-production)  
14. [Step 12 — Backups](#step-12--backups-and-restores)  
15. [Step 13 — Upgrades](#step-13--upgrades)  
16. [Step 14 — Containers](#step-14--container-deployment-optional-pattern)  
17. [DigitalOcean (Droplet) deployment](#digitalocean-droplet-deployment)  
18. [Troubleshooting](#troubleshooting)  

---

## Before you start

You need:

| Requirement | Notes |
|-------------|--------|
| **Python** | 3.10 or newer recommended (3.11+ typical for LangChain stacks). |
| **Network** | Outbound HTTPS to **OpenAI** at **`https://api.openai.com`** (embeddings + chat) **unless** you override **`OPENAI_API_BASE`** to another OpenAI-compatible endpoint. Many enterprises **block** public AI URLs — confirm with IT or use an approved gateway before going live. |
| **Disk** | Space for SQLite or Postgres, **`chroma-db/`** embeddings, **`uploads/`** originals, **`logs/`**. |
| **Secrets** | At minimum **`OPENAI_API_KEY`** and a strong **`SESSION_SECRET`** for any internet-facing deployment. |

Optional: **PostgreSQL** for multi-instance or managed DB; **Nginx** (or another reverse proxy) for TLS and static buffering.

---

## Step 1 — Get the code

On the server or build agent:

```bash
git clone <your-repo-url> nexura
cd nexura/latest_rag_application
```

(Adjust folder names if your repo layout differs.)

---

## Step 2 — Create a virtual environment

Isolates dependencies from system Python.

```bash
python3 -m venv .venv
source .venv/bin/activate          # Linux / macOS
# .venv\Scripts\activate           # Windows PowerShell
```

Every deploy command below assumes the venv is **activated**.

---

## Step 3 — Install Python dependencies

```bash
pip install --upgrade pip
pip install -r requirements-dev.txt
```

Public **`/docs`** serves **Swagger UI** only (OpenAPI at **`/api/openapi.json`**). **Product summary** and **this deployment guide** render in the console for platform superusers at **`/super/guides`** — install the **`markdown`** package (listed in `requirements-dev.txt`) for HTML rendering there.

For **production HTTP serving**, install a WSGI server (not included by default):

```bash
pip install gunicorn
```

---

## Step 4 — Choose where state lives on disk

Nexura persists:

| Path | Purpose | Default (see `config.py`) |
|------|---------|---------------------------|
| **SQL database** | Users, tenants, collections, documents metadata | `sqlite:///…/rag_platform.db` |
| **Chroma** | Vector index | `CHROMA_DB_FILE_PATH` → `<project>/chroma-db` |
| **Uploads** | Stored PDF/TXT files | `uploads/` under project root |
| **Logs** | Application logs | `<project>/logs` via `LOG_DIR` |

On production hosts, point **`CHROMA_DB_FILE_PATH`**, **`LOG_DIR`**, and optionally the SQLite path (via **`DATABASE_URL`**) at **mounted volumes** with backups and correct UNIX ownership (the user running the app must be able to read/write).

Create directories if you override paths:

```bash
mkdir -p logs chroma-db uploads
chmod 750 uploads chroma-db logs
```

---

## Step 5 — Configure environment variables

Set variables **before** starting the process (shell exports, systemd `Environment=`, Docker `env`, Kubernetes `Secret`, etc.). All keys are read in **`config.py`**.

### Minimum for a working chat + upload (embeddings) stack

```bash
export OPENAI_API_KEY="sk-..."
export SESSION_SECRET="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
export ADMIN_BOOTSTRAP_PASSWORD='choose-a-strong-password'
# Restrict widget CORS (comma-separated origins). Default "*" is for demos only.
export EMBED_CORS_ORIGINS='https://www.customer.com,https://customer.com'
```

### Corporate / locked-down networks

If TLS interception breaks Python’s default CA bundle, or you must disable verification **only** for the OpenAI HTTP client:

```bash
# false (default in config): httpx verify=False for OpenAI calls — use only when needed.
# true: normal certificate verification (preferred on trusted networks).
export VERIFY_SSL='false'    # or true

# If api.openai.com is blocked but IT provides an OpenAI-compatible URL (gateway, approved host):
export OPENAI_API_BASE='https://your-approved-host/v1'   # trailing path per vendor docs
```

**Note:** If the firewall returns an HTML “blocked” page (policy category AI), **`OPENAI_API_BASE`** alone may not help unless that URL is explicitly allowed. You may need IT approval, VPN, or Azure / internal AI endpoints (sometimes requiring different client classes — follow your platform docs).

### Strongly recommended for production

```bash
export SESSION_SECRET='long-random-string'
export ADMIN_BOOTSTRAP_USERNAME='admin'
export ADMIN_BOOTSTRAP_PASSWORD='long-random-password'
export DATABASE_URL='postgresql+psycopg://user:pass@host:5432/nexura'   # optional
export CHROMA_DB_FILE_PATH='/var/lib/nexura/chroma'
export LOG_DIR='/var/log/nexura'
export PORT='8000'
```

### Multi-tenant signup (optional)

```bash
# Default true: marketing site + /register create new organisations + first admin.
# Set false for a fixed appliance (only seeded default tenant + manual DB provisioning).
export REGISTRATION_ENABLED='false'
```

### Other optional overrides

| Variable | Purpose |
|----------|---------|
| **`OPENAI_MODEL`**, **`EMEDDING_MODEL`** | LLM and embedding model IDs (`EMEDDING_MODEL` spelling matches **`config.py`**). |
| **`SEARCH_K`** | Retrieval breadth for RAG. |
| **`DEFAULT_TENANT_SLUG`** | Seed tenant slug at first boot (login hint); default **`default`**. |

Reference: **`docs/TECHNICAL.md`** §4 (configuration reference) and §24 (plans / quotas).

---

## Step 6 — Use PostgreSQL (optional but typical for production)

1. Choose **where** Postgres runs: **DigitalOcean Managed Database**, **PostgreSQL packages on your Droplet/server** ([walkthrough below](#postgresql-installed-on-this-droplet-ubuntu--digitalocean)), or another Postgres you operate. The app expects an empty logical database — it uses **`db.create_all()`** at startup (no Alembic migrations in-tree).
2. Install the Python driver in the **same virtualenv** as Nexura:

   ```bash
   pip install psycopg[binary]
   ```

3. Set **`DATABASE_URL`** (**`config.py`** reads this). Use the **`postgresql+psycopg://`** dialect, for example:

   ```text
   postgresql+psycopg://nexura:YOUR_PASSWORD@127.0.0.1:5432/nexura
   ```

   For **Managed Postgres** over TLS, include **`?sslmode=require`** when the vendor requires it (use the connection string from the vendor control panel — replace **placeholders** such as **`db-private-host`** with the **real** hostname).

4. Start Nexura once so tables are created and **`seed_if_needed`** runs (bootstrap tenant + admin).

SQLite is acceptable for single-node demos; use Postgres when you want better concurrency under load, **`pg_dump`** backups, or a clearer path to an external DB later.

---

### PostgreSQL installed on this Droplet (Ubuntu / DigitalOcean)

Use these steps when Postgres runs **on the same machine** as Gunicorn (typical single Droplet).

#### 1. Install server packages

```bash
sudo apt update
sudo apt install -y postgresql postgresql-contrib
sudo systemctl enable --now postgresql
sudo systemctl status postgresql --no-pager
```

Packaged Postgres on Ubuntu listens on **`127.0.0.1`** by default — match **`DATABASE_URL`** with **`...@127.0.0.1:5432/...`**; **do not** publish **`TCP 5432`** on a public Droplet firewall.

#### 2. Create database role and database

Replace **`YOUR_DB_PASSWORD`** with a strong secret (use the same value in **`DATABASE_URL`**):

```bash
sudo -u postgres psql -v ON_ERROR_STOP=1 <<'EOSQL'
CREATE USER nexura WITH PASSWORD 'YOUR_DB_PASSWORD';
CREATE DATABASE nexura OWNER nexura;
GRANT ALL PRIVILEGES ON DATABASE nexura TO nexura;
EOSQL
```

#### 3. Password auth from **`127.0.0.1`** (usually already correct)

Ubuntu’s default **`/etc/postgresql/*/main/pg_hba.conf`** normally allows **`host … 127.0.0.1/32 … scram-sha-256`** (or **`md5`**). Inspect if TCP auth fails:

```bash
grep -E '^\s*host' /etc/postgresql/*/main/pg_hba.conf
```

After edits: **`sudo systemctl reload postgresql`**.

#### 4. Verify before starting Nexura

```bash
PGPASSWORD='YOUR_DB_PASSWORD' psql -h 127.0.0.1 -p 5432 -U nexura -d nexura -c 'SELECT current_user, current_database();'
```

Expect **`nexura`** for both columns.

#### 5. Nexura environment

In **`/etc/nexura/environment`** (or shell exports):

```bash
DATABASE_URL=postgresql+psycopg://nexura:YOUR_DB_PASSWORD@127.0.0.1:5432/nexura
```

Ensure the app venv includes **`pip install psycopg[binary]`** (included in **[DigitalOcean §5](#5--clone-app-and-python-env)** example).

Optional ordering in **`/etc/systemd/system/nexura.service`**:

```ini
After=network.target postgresql.service
```

Then **`sudo systemctl daemon-reload`** and **`sudo systemctl restart nexura.service`**.

#### 6. Health check

```bash
curl -sf http://127.0.0.1:8000/health
```

#### 7. Backups (**`pg_dump`**)

Align with **Step 12** — example compressed dump owned by **`postgres`**:

```bash
sudo -u postgres pg_dump -Fc -f /tmp/nexura-$(date +%F).dump nexura
```

Copy **`*.dump`** off the Droplet (object storage / backup tooling).

---

## Step 7 — First start (database bootstrap)

Tables are created and the seed routine runs when **`app.py`** is loaded (`init_database()` at module level). On startup the app also runs **best-effort `ALTER TABLE`** helpers for existing SQLite/Postgres databases (for example **`tenants.plan_slug`**, **`usage_*`**, **`tenants.is_active`**, **`billing_contact_email`**, **`allowed_agent_ids_json`**, **`api_keys.default_agent_id`**) so minor schema additions do not always require manual SQL—see **`app.py`** (`_ensure_tenant_plan_columns`, `_ensure_api_keys_columns`).

**Development:**

```bash
python app.py
```

Expected:

- Listening on **`0.0.0.0:PORT`** (default **5000** from `config.py`).
- Log warning if **`ADMIN_BOOTSTRAP_PASSWORD`** is still **`changeme`** — change it before exposing to the internet.

**Verify:**

```bash
curl -sSf http://127.0.0.1:${PORT:-5000}/health
```

Expect JSON `{"status":"ok"}`.

### Path A — Seeded default tenant (always created on first boot)

1. Open **`http://<host>:<port>/login`**
2. **Organisation (tenant slug):** **`default`** (unless you changed **`DEFAULT_TENANT_SLUG`**)
3. **Username / password:** **`ADMIN_BOOTSTRAP_USERNAME`** / **`ADMIN_BOOTSTRAP_PASSWORD`**

Then open **`/app`** for the console. To grant **platform superuser** access to that bootstrap user on first seed only, set **`BOOTSTRAP_SUPERUSER=true`** in the environment before the first run (see **`docs/TECHNICAL.md`** §4). Superusers can open **`/super/settings`**, **`/super/organisations`** (all tenants), **`/super/guides`**, and **`/super/technical`**.

### Path B — Self-service organisation (`REGISTRATION_ENABLED=true`, default)

1. Open **`http://<host>:<port>/register`**
2. Complete organisation name, URL slug, plan (**Starter** / **Growth** / **Enterprise** — limits in **`plans_catalog.py`**), and first admin credentials.
3. You are redirected to **`/login`** with the new slug prefilled; sign in as that admin.
4. In the console, **Team** (admins / anyone with **`users:manage`**) can add users and assign **Admin / Editor / Viewer**; same capability via **`/api/v1/users`** and **`/api/v1/roles`**.

Use **`REGISTRATION_ENABLED=false`** if you do not want public signup (single-tenant or invite-only operations).

---

## Optional — Customer-site embed widget

After Nexura is running and you can open **`/app`**:

1. Set **`EMBED_CORS_ORIGINS`** on the server to the exact **`Origin`** values of pages that will host the widget (comma-separated HTTPS URLs). Restart after edits. Default **`*`** is only for local experiments.
2. Log in as **Admin** or **Editor** (role includes **`embed:keys`**).
3. Go to **Embed** in the sidebar → **Create embed key**. Optionally pick **allowed collections** and a **default agent**.
4. Copy the **full secret** from the response/snippet once; store it securely. Copy the **`<script … nexura-chat.js>`** snippet into customer HTML before **`</body>`**.
5. Ensure **`data-base-url`** is your Nexura deployment’s public origin (scheme + host + optional port), matching where **`/api/embed/chat`** is reachable.

If the widget shows network/CORS errors, verify **`EMBED_CORS_ORIGINS`**, HTTPS mismatches, and that **`data-base-url`** has no trailing slash issues relative to your nginx **`proxy_pass`** rules.

---

## Step 8 — Run behind Gunicorn (production app server)

Do **not** rely on Flask’s built-in server in production.

Example (adjust workers for CPU; see caveat below on chat memory):

```bash
cd /path/to/latest_rag_application
source .venv/bin/activate
export OPENAI_API_KEY=...
export SESSION_SECRET=...
gunicorn -w 2 -b 0.0.0.0:8000 --timeout 120 app:app
```

- **`--timeout 120`** helps long LLM/RAG requests.
- **`app:app`** is the Flask application object in **`app.py`**.

**Multi-worker caveat:** conversation **`memory_store`** is **in-process**. Multiple Gunicorn workers do **not** share chat memory. Use **`-w 1`** if session continuity across requests matters until you replace memory with Redis or similar.

---

## Step 9 — Reverse proxy and TLS (nginx example)

Terminate TLS at nginx and proxy to Gunicorn:

```nginx
server {
    listen 443 ssl http2;
    server_name nexura.example.com;

    ssl_certificate     /etc/letsencrypt/live/nexura.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/nexura.example.com/privkey.pem;

    client_max_body_size 50m;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Issue certificates with **Certbot** or your cloud load balancer. Cookies are session-based — HTTPS is required on untrusted networks.

---

## Step 10 — Process supervision

Keep the app alive with **systemd**, **supervisor**, Docker **`restart`**, or Kubernetes **`Deployment`**.

**systemd sketch** (`/etc/systemd/system/nexura.service`):

```ini
[Unit]
Description=Nexura Flask app
After=network.target

[Service]
User=nexura
Group=nexura
# APP_ROOT = directory containing app.py and .venv/
WorkingDirectory=/opt/nexura/rag-agent-chat
# Use EnvironmentFile=-/etc/nexura/environment with lines like:
#   OPENAI_API_KEY=...
#   SESSION_SECRET=...
#   ADMIN_BOOTSTRAP_PASSWORD=...
#   EMBED_CORS_ORIGINS=https://app.example.com
#   DATABASE_URL=postgresql+psycopg://...
#   REGISTRATION_ENABLED=false
EnvironmentFile=-/etc/nexura/environment
# One line avoids systemd execution issues; prefer -w 1 while chat memory is in-process — see Step 8.
ExecStart=/opt/nexura/rag-agent-chat/.venv/bin/gunicorn -w 1 -b 127.0.0.1:8000 --timeout 120 app:app
Restart=always

[Install]
WantedBy=multi-user.target
```

Reload and enable:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now nexura.service
```

---

## Step 11 — Security checklist (production)

1. **`SESSION_SECRET`** — unique per environment; rotate revokes sessions.
2. **`ADMIN_BOOTSTRAP_PASSWORD`** — never `changeme` in production.
3. **Firewall** — expose only 80/443 (or your LB); bind Gunicorn to localhost if nginx is local.
4. **File permissions** — restrict **`uploads/`**, **`chroma-db/`**, DB files to the service user.
5. **Dependency updates** — periodically **`pip audit`** / image scans.  
6. **OpenAI keys** — scoped keys, usage alerts, separate keys per env.  
7. **Embed** — **`EMBED_CORS_ORIGINS`** allow-list only; revoke leaked **`nxemb_…`** keys from console **Embed** tab (`DELETE /api/v1/embed-keys/…`).

See **`docs/TECHNICAL.md`** §21.

---

## Step 12 — Backups and restores

| Asset | What to back up |
|--------|------------------|
| Relational DB | Full dump (`pg_dump`) or SQLite file **while consistent** (stop app or use backup mode). |
| Chroma | Entire directory pointed to by **`CHROMA_DB_FILE_PATH`**. |
| Uploads | **`uploads/`** tree (or your custom storage path). |

Restore order: restore DB + Chroma + uploads from the **same point in time** where possible, or re-ingest documents after DB restore if vectors are lost.

---

## Step 13 — Upgrades

1. Pull new code.
2. Activate venv → **`pip install -r requirements-dev.txt`** (review changelog for breaking env vars).
3. Restart Gunicorn/systemd so **`init_database()`** runs again.
4. **Schema:** New tables are created via **`db.create_all()`**. Some **additive** columns on **`tenants`** and **`api_keys`** are applied automatically on startup (see Step 7). If you add columns elsewhere in **`models.py`**, you may still need manual **`ALTER TABLE`**, a fresh dev DB, or a formal migration tool—inspect **`docs/TECHNICAL.md`** §5 and §24.

---

## Step 14 — Container deployment (optional pattern)

There is no checked-in Dockerfile in this repository; a minimal pattern:

1. Base image **`python:3.11-slim`**
2. Copy app, **`pip install -r requirements-dev.txt gunicorn`**
3. **`ENV`** for secrets (prefer runtime injection, not baked images)
4. **`VOLUME`** or mounted PVC for **`CHROMA_DB_FILE_PATH`**, **`uploads/`**, SQLite file if used
5. **`CMD`** → **`gunicorn`** as in Step 8

Ensure **one writable persistence layer** per tenant data path; read-only container filesystem breaks uploads and Chroma.

---

## DigitalOcean (Droplet) deployment

This section is tailored for **[DigitalOcean Droplets](https://www.digitalocean.com/products/droplets)** (Ubuntu LTS): persistent disk for **`chroma-db/`**, **`uploads/`**, and logs; **nginx + Let’s Encrypt**; **systemd**. It mirrors Steps 8–12 with DO-specific defaults. *(Platform superusers: this guide also renders under **Console → Product & deployment** at **`/super/guides`.)*

**Deployment directory (`APP_ROOT`).** **`systemd`** must use the **same** directory that contains **`app.py`**, **`requirements-dev.txt`**, and (after Step 5) **`.venv/`**. This walkthrough assumes:

**`APP_ROOT=/opt/nexura/rag-agent-chat`** — for example **`/opt/nexura/rag-agent-chat/app.py`**.

If your repo nests the Flask project (e.g. **`…/latest_rag_application/app.py`**), treat that **inner folder** as **`APP_ROOT`** everywhere below (**`WorkingDirectory`**, **`ExecStart`** path to **`.venv/bin/gunicorn`**, **`git pull`** upgrades).

### Before you provision

| Approach | Notes |
|----------|--------|
| **Ubuntu Droplet + nginx + systemd** | **Recommended.** Matches Chroma + file uploads local paths (Steps 4, 12). Attach a **[Volume](https://www.digitalocean.com/products/block-storage)** (e.g. mount **`/var/lib/nexura`**) if the Droplet disk is small. |
| **Droplet + [Managed PostgreSQL](https://www.digitalocean.com/products/managed-databases)** | **Recommended** instead of SQLite when you want a separate DB cluster: backups and concurrency (**Step 6**). Use the **real** hostname from the DO control panel (**not** literal placeholders like **`db-private-host`**); VPC **private** host requires the Droplet on the **same VPC** / trusted sources. |
| **PostgreSQL on this Droplet** | Postgres and Nexura share one VM (**[details — Step 6](#postgresql-installed-on-this-droplet-ubuntu--digitalocean)**). **`DATABASE_URL`** uses **`127.0.0.1:5432`** — do **not** open **TCP 5432** on a public Droplet firewall. |
| **DigitalOcean App Platform** | **Not recommended as-is:** deploys typically use an **ephemeral** filesystem — **Chroma**, **uploads**, and default **SQLite** can be reset on redeploy unless you redesign storage (object storage + code changes). Use a Droplet until then. |

### 1 — Create Droplet, DNS, firewall

1. **DigitalOcean → Droplets → Create** — Image **Ubuntu 24.04 LTS** (or 22.04). Plan **≥ 2 GB RAM** ( **4 GB** safer for embeddings + concurrency). Authenticate with **SSH keys**.  
2. **DNS:** **A record** for your hostname (e.g. **`app.example.com`**) → Droplet public IPv4 (and **AAAA** if you use IPv6).  
3. **Cloud firewall:** inbound **SSH 22** — restrict to **your IP(s)** where possible; inbound **HTTP 80** and **HTTPS 443** → everywhere (for HTTPS + ACME). **Do not** publish Gunicorn’s port; only **nginx** faces the internet.  

### 2 — Optional Managed Postgres

Create a PostgreSQL cluster in the **same region/VPC**, create database + user, copy the **connection string** from the control panel and paste **verbatim** into **`DATABASE_URL`** (often includes **`sslmode=require`**). Do **not** keep template hostnames — they will fail DNS (**`journalctl`** shows “failed to resolve host”).

### PostgreSQL on the same Droplet (local packages)

Prefer this when everything runs on **one Droplet**. Full procedure: **[Step 6 — PostgreSQL installed on this Droplet](#postgresql-installed-on-this-droplet-ubuntu--digitalocean)**. Summary:

1. **`sudo apt install -y postgresql postgresql-contrib`** then **`sudo systemctl enable --now postgresql`**  
2. Create **`nexura`** DB user + **`nexura`** database as **`postgres`** (**`sudo -u postgres psql …`**) — same password must appear in **`DATABASE_URL`**  
3. **`DATABASE_URL=postgresql+psycopg://nexura:PASSWORD@127.0.0.1:5432/nexura`** in **`/etc/nexura/environment`**  
4. Optionally add **`After=postgresql.service`** to **`nexura.service`**, **`systemctl daemon-reload`**, then **`systemctl restart nexura`**

Perform these **before** the first Nexura start that connects to Postgres. Install **`psycopg[binary]`** in Step 6 / **[§5 Clone](#5--clone-app-and-python-env)**.

### 3 — Baseline packages and deploy user

On the Droplet:

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-venv python3-pip git nginx certbot python3-certbot-nginx

sudo useradd -r -m -s /bin/bash nexura 2>/dev/null || true
sudo mkdir -p /opt/nexura
sudo chown nexura:nexura /opt/nexura

sudo mkdir -p /etc/nexura
sudo chmod 700 /etc/nexura
```

### 4 — Optional Volume for data

Attach a Block Storage Volume, **[format and mount](https://docs.digitalocean.com/products/volumes/how-to/format-and-mount/)** e.g. **`/var/lib/nexura`**. Then:

```bash
sudo mkdir -p /var/lib/nexura/chroma-db /var/lib/nexura/uploads /var/lib/nexura/logs
sudo chown -R nexura:nexura /var/lib/nexura
```

### 5 — Clone app and Python env

Ensure **`nexura`** owns the tree and **`app.py`** resolves to **`APP_ROOT/app.py`** (here **`/opt/nexura/rag-agent-chat/app.py`**):

```bash
sudo mkdir -p /opt/nexura/rag-agent-chat
sudo chown -R nexura:nexura /opt/nexura/rag-agent-chat

sudo -iu nexura
cd /opt/nexura/rag-agent-chat
# Put the Nexura codebase in this folder (example: shallow clone contents into APP_ROOT).
git clone --depth 1 https://github.com/YOUR_ORG/YOUR_REPO.git .
# If your repo only contains a subfolder (e.g. latest_rag_application/), clone then:
#   git clone … /tmp/repo && rsync -a /tmp/repo/latest_rag_application/ .
# Confirm:
test -f app.py || { echo "app.py missing — adjust clone so APP_ROOT contains app.py"; exit 1; }

python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements-dev.txt gunicorn "psycopg[binary]"
mkdir -p logs chroma-db uploads
exit
```

If **not** using a Volume for Chroma/logs/uploads, ensure **`nexura`** can write **`chroma-db/`**, **`uploads/`**, **`logs/`** next to **`app.py`**.

### 6 — Secrets and environment (`/etc/nexura/environment`)

```bash
sudo tee /etc/nexura/environment >/dev/null <<'EOF'
OPENAI_API_KEY=sk-your-key-here
SESSION_SECRET=REPLACE_WITH_openssl_rand_hex32_or_python_secrets_token_hex
ADMIN_BOOTSTRAP_USERNAME=admin
ADMIN_BOOTSTRAP_PASSWORD=REPLACE_WITH_STRONG_PASSWORD
VERIFY_SSL=true
EMBED_CORS_ORIGINS=https://app.example.com
# Optional — only effective on first seed; then set false / remove line
BOOTSTRAP_SUPERUSER=true
# Postgres — use REAL values (examples):
# DATABASE_URL=postgresql+psycopg://nexura:STRONG_PW@127.0.0.1:5432/nexura
# DATABASE_URL='postgresql+psycopg://doadmin:...@HOST_FROM_DO_PANEL:25060/defaultdb?sslmode=require'
# Omit DATABASE_URL entirely to fall back to SQLite under APP_ROOT.
# Uncomment if using Volume paths
# CHROMA_DB_FILE_PATH=/var/lib/nexura/chroma-db
# LOG_DIR=/var/lib/nexura/logs
EOF
sudo chmod 600 /etc/nexura/environment
sudo chown root:root /etc/nexura/environment
```

Edit the file (**`sudo nano /etc/nexura/environment`**): set real secrets, uncomment **`DATABASE_URL`** / paths as needed. Set **`REGISTRATION_ENABLED`**, **`OPENAI_MODEL`**, etc. per **Step 5** of this guide.

Embed hosting: **`EMBED_CORS_ORIGINS`** must be comma-separated **`https://…`** origins, not **`*`** in production (**Step 11** applies).

### 7 — systemd (Gunicorn on localhost)

**Multi-worker caveat:** **`memory_store`** is in-process (**Step 8**). Use **`-w 1`** unless you omit session memory or adopt shared storage.

Create **`/etc/systemd/system/nexura.service`** (same **`WorkingDirectory`** and **`ExecStart`** prefixes as **`APP_ROOT`**):

```ini
[Unit]
Description=Nexura (Gunicorn)
After=network.target

[Service]
User=nexura
Group=nexura
WorkingDirectory=/opt/nexura/rag-agent-chat
EnvironmentFile=-/etc/nexura/environment
ExecStart=/opt/nexura/rag-agent-chat/.venv/bin/gunicorn -w 1 -b 127.0.0.1:8000 --timeout 120 app:app
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now nexura.service
curl -sf http://127.0.0.1:8000/health
```

Expect **`{"status":"ok"}`**.

### 8 — nginx + TLS (Let’s Encrypt)

**`/etc/nginx/sites-available/nexura`**:

```nginx
server {
    listen 80;
    server_name app.example.com;

    client_max_body_size 50m;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
sudo ln -sf /etc/nginx/sites-available/nexura /etc/nginx/sites-enabled/nexura
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d app.example.com
```

### 9 — First login and superuser

Follow **Step 7 (Path A)** in this guide: **`/login`** with tenant **`default`** (**`DEFAULT_TENANT_SLUG`**) unless you use **public registration**. If **`BOOTSTRAP_SUPERUSER=true`** was present **before the first seed**, the bootstrap admin can open **`/super/*`**. Rotate **`ADMIN_BOOTSTRAP_PASSWORD`**, then set **`BOOTSTRAP_SUPERUSER=false`** (and restart) before treating the deployment as hardened — see **`docs/TECHNICAL.md`** §4.

### 10 — Backups on DigitalOcean

| Asset | Recommendation |
|--------|------------------|
| **Managed Postgres** | Enable **automatic backups** in the DO control panel; test restore. |
| **Postgres on this Droplet** | **`pg_dump`** (see **[Step 6 §7](#postgresql-installed-on-this-droplet-ubuntu--digitalocean)** and **Step 12**); copy dumps off-droplet nightly. |
| **SQLite on Droplet** | Snapshot Droplet **or** copy **`rag_platform.db`** with the app stopped for consistency (**Step 12**). |
| **Chroma + uploads** | **Volume snapshots** or **scheduled rsync**/Droplet backups; keep DB + vectors + uploads time-aligned (**Step 12**). |

### 11 — Upgrades on the Droplet

```bash
sudo systemctl stop nexura
sudo -iu nexura bash -lc 'cd /opt/nexura/rag-agent-chat && git pull && source .venv/bin/activate && pip install -r requirements-dev.txt'
sudo systemctl start nexura
```

See **Step 13** for schema / **`init_database()`** behaviour.

References: **Steps 5–13**, **`docs/TECHNICAL.md`** §4 (environment), §21 (security checklist).

---

## Troubleshooting

| Symptom | Things to check |
|---------|-------------------|
| **401 on APIs** | Session cookie missing; login via **`/login`**; same-site cookie settings behind proxy (**`X-Forwarded-*`**). |
| **401 on `/api/embed/chat`** | Missing/wrong **`Authorization: Bearer`** or **`X-Nexura-Embed-Key`**; key revoked (**`is_active`** false). |
| **Browser blocks embed widget (CORS)** | **`Origin`** of the page hosting the snippet must be listed in **Platform settings → Embed widget · CORS** (super admin) or env **`EMBED_CORS_ORIGINS`** when no DB row exists. Scheme/host/port must match exactly (**`www`** vs apex). Restart **not** required after saving settings. |
| **500 on chat** | **`OPENAI_API_KEY`**; plan quotas (**`plans_catalog`**); Chroma path writable; logs under **`LOG_DIR`**. |
| **500 on upload / “embedding API blocked”** | Corporate firewall blocking **`api.openai.com`** (HTML block page in logs). Use **`OPENAI_API_BASE`**, approved gateway, or unrestricted network. See Step 5. |
| **`CERTIFICATE_VERIFY_FAILED` on embeddings** | TLS inspection: **`VERIFY_SSL=false`** for OpenAI HTTP client only, or install corporate root CA; prefer **`VERIFY_SSL=true`** when verification works. |
| **`no such column: api_keys.*` / `tenants.*`** | Restart after upgrade so startup **`ALTER`** helpers run; else manual SQL — **`docs/TECHNICAL.md`** §5 / §24. |
| **403 on users / embed keys / new collection** | Plan limits (**`max_users`**, **`max_embed_keys`**, **`max_collections`**). Adjust **`tenants.plan_slug`** or **`plans_catalog.py`**. |
| **Empty retrieval** | Documents ingested? Correct tenant? **`collection_ids`** in chat body if narrowing scope. |
| **Wrong tenant data** | **`tenant_slug`** at login; **`DATABASE_URL`** points to intended DB. |
| **502 Bad Gateway** (nginx) | **`nexura`** service stopped or crashing — **`journalctl -u nexura -f`**; **`curl http://127.0.0.1:8000/health`** on the Droplet; fix **`DATABASE_URL`**, **`OPENAI_API_KEY`**, or writable paths (**[DigitalOcean section](#digitalocean-droplet-deployment)**). |
| **Postgres** “failed to resolve host” | **`DATABASE_URL`** still uses a docs **placeholder** (e.g. **`db-private-host`**) — substitute the **real DO host** or use **`127.0.0.1`** if Postgres is **[on-Droplet](#postgresql-installed-on-this-droplet-ubuntu--digitalocean)**. |
| **Postgres connection refused / auth failed** | **`postgresql`** running? (**`systemctl status postgresql`**). Password, username, **`DATABASE_URL`**, and **`pg_hba.conf`** (**`127.0.0.1`**) aligned? Test **`PGPASSWORD=… psql -h 127.0.0.1 -U nexura -d nexura`** (on-Droplet install). |
| **`status=203/EXEC`** (**`systemctl status nexura`**) | **`ExecStart`** path wrong or **`gunicorn`** missing — verify **`WorkingDirectory`** is the folder with **`app.py`**; **`ls APP_ROOT/.venv/bin/gunicorn`**; keep **`ExecStart`** on **one line** (**[DigitalOcean §5–§7](#digitalocean-droplet-deployment)**). |

---

For architecture and every HTTP route, see **`docs/TECHNICAL.md`** (superusers: **`/super/technical`**). Cross-tenant administration is **`/super/organisations`**. Product overview and this deployment guide render together at **`/super/guides`** (sources **`docs/FEATURES_SUMMARY.md`** — including marketplace agents for platform operators — **`docs/DEPLOYMENT.md`**, with a **[DigitalOcean (Droplet)](#digitalocean-droplet-deployment)** walkthrough). Live API explorer: **`/docs`** (Swagger).
