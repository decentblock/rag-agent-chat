import os
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
EMEDDING_MODEL = os.getenv("EMEDDING_MODEL", "text-embedding-3-small")
# Corporate-friendly: OpenAI-compatible base URL (gateway, proxy, some Azure setups). Env OPENAI_API_BASE.
OPENAI_API_BASE = (os.getenv("OPENAI_API_BASE") or "").strip() or None


SEARCH_K = int(os.getenv("SEARCH_K", "3"))

# Defaults live under the repo so local runs work without Docker mounts.
# Override with LOG_DIR / CHROMA_DB_DIR (and optionally CHROMA_DB_FILE_PATH) in production.
LOG_DIR = os.getenv("LOG_DIR") or str(_PROJECT_ROOT / "logs")
PORT = int(os.getenv("PORT", "5000"))
CHROMA_DB_DIR = os.getenv("CHROMA_DB_DIR") or str(_PROJECT_ROOT / "chroma-db")
CHROMA_DB_FILE_PATH = os.getenv("CHROMA_DB_FILE_PATH") or CHROMA_DB_DIR

DEFAULT_COLLECTION_NAME=""

# Until JWT tenancy ships: single placeholder tenant for SaaS migration path.
DEFAULT_TENANT_ID = os.getenv("DEFAULT_TENANT_ID", "default")

# When false (default), OpenAI calls use httpx with verify=False — needed behind TLS-intercepting proxies.
# Set VERIFY_SSL=true in production when no custom CA issues.
VERIFY_SSL = os.getenv("VERIFY_SSL", "false").lower() in ("1", "true", "yes")

# Web UI + sessions (override in production)
SESSION_SECRET = os.getenv("SESSION_SECRET") or "dev-only-set-SESSION_SECRET-in-production"

# Dev bootstrap admin (seed_database); replace with IdP in production.
ADMIN_BOOTSTRAP_USERNAME = os.getenv("ADMIN_BOOTSTRAP_USERNAME", "admin")
ADMIN_BOOTSTRAP_PASSWORD = os.getenv("ADMIN_BOOTSTRAP_PASSWORD", "changeme")

# Legacy UI env login removed — use seeded admin + tenant slug on login form.

DATABASE_URL = os.getenv("DATABASE_URL") or f"sqlite:///{_PROJECT_ROOT / 'rag_platform.db'}"
DEFAULT_TENANT_SLUG = os.getenv("DEFAULT_TENANT_SLUG", "default")

# Comma-separated Origin values for browser embeds (POST /api/embed/*). Default "*" for dev only.
EMBED_CORS_ORIGINS = os.getenv("EMBED_CORS_ORIGINS", "*")

# New organisation self-signup (disable with REGISTRATION_ENABLED=false).
REGISTRATION_ENABLED = os.getenv("REGISTRATION_ENABLED", "true").lower() in (
    "1",
    "true",
    "yes",
)