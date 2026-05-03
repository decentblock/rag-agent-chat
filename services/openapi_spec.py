"""OpenAPI 3.0 document for Swagger UI (JSON)."""

from __future__ import annotations

from typing import Any


def build_openapi_spec(*, server_url: str) -> dict[str, Any]:
    """Return a dict suitable for Flask ``jsonify``. ``server_url`` should be the API origin (no trailing slash)."""
    su = (server_url or "").rstrip("/") or ""

    return {
        "openapi": "3.0.3",
        "info": {
            "title": "Nexura HTTP API",
            "version": "1.0.0",
            "description": (
                "**Nexura** is a multi-tenant RAG platform: isolated collections per organisation, "
                "session-based console auth, RBAC, grounded chat with citations, embeddable widgets, "
                "and an agent marketplace.\n\n"
                "### Authentication\n"
                "- **Console / tenant APIs**: sign in via `POST /login` (browser cookie session). "
                "Same-origin `Try it out` requests from `/docs` (Swagger UI) reuse your session cookie.\n"
                "- **Embed chat**: send `Authorization: Bearer <nxemb_…>` or header `X-Nexura-Embed-Key`.\n\n"
                "### Permissions\n"
                "Tenant endpoints require the logged-in user to hold the relevant permission "
                "(e.g. `chat:query`, `documents:read`, `embed:keys`, `users:manage`). "
                "Admins typically have `*`.\n\n"
                "Product overview and deployment guides: console → **Product & deployment** (`/super/guides`, superusers). "
                "Architecture and schema: **Technical reference** (`/super/technical`)."
            ),
        },
        "servers": [{"url": su, "description": "This deployment"}],
        "tags": [
            {
                "name": "Public",
                "description": "Unauthenticated catalogue and health probes.",
            },
            {
                "name": "Health",
                "description": "Liveness check.",
            },
            {
                "name": "Tenant · Subscription & preferences",
                "description": "Plan limits and per-user agent preference (session auth).",
            },
            {
                "name": "Chat",
                "description": "Grounded chat with retrieval (`chat:query`).",
            },
            {
                "name": "Embed",
                "description": (
                    "Cross-origin widget (`nxemb_…` Bearer): chat, widget-config, visitor-contact. "
                    "Tenant console: embed-key CRUD, branding, visitor-lead export (`embed:keys`)."
                ),
            },
            {
                "name": "Knowledge base",
                "description": "Collections, documents, chunk previews (`documents:*`, `collections:manage` where noted).",
            },
            {
                "name": "Users",
                "description": "Tenant user administration (`users:manage`).",
            },
        ],
        "components": {
            "securitySchemes": {
                "SessionCookie": {
                    "type": "apiKey",
                    "in": "cookie",
                    "name": "session",
                    "description": "Flask session cookie after successful `POST /login`.",
                },
                "EmbedBearer": {
                    "type": "http",
                    "scheme": "bearer",
                    "bearerFormat": "nxemb_<prefix>_<secret>",
                    "description": "Embed API key; alternatively send `X-Nexura-Embed-Key: <full key>`.",
                },
            },
            "schemas": {
                "Error": {
                    "type": "object",
                    "properties": {"error": {"type": "string"}},
                    "required": ["error"],
                },
                "ChatRequest": {
                    "type": "object",
                    "properties": {
                        "chat_message": {"type": "string", "description": "User message."},
                        "agent_id": {"type": "string", "description": "Optional override; defaults to saved preference."},
                        "agent_config": {"type": "object", "additionalProperties": True},
                        "collection_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional collection UUIDs or slugs to scope retrieval.",
                        },
                        "llm_route": {"type": "string", "default": "platform_llm"},
                        "llm_config_ref": {},
                        "client_hint": {},
                    },
                },
                "ChatResponse": {
                    "type": "object",
                    "properties": {
                        "answer": {"type": "string"},
                        "citations": {"type": "array", "items": {}},
                        "agent_id": {"type": "string"},
                        "usage": {},
                        "extra": {},
                    },
                },
                "EmbedChatRequest": {
                    "type": "object",
                    "properties": {
                        "chat_message": {"type": "string"},
                        "visitor_session": {"type": "string", "description": "Visitor id for memory partitioning."},
                        "agent_id": {"type": "string"},
                        "agent_config": {"type": "object", "additionalProperties": True},
                        "collection_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional KB collection UUIDs or slugs (embed key scope still applies). Omit for full key scope.",
                        },
                        "llm_route": {"type": "string"},
                        "llm_config_ref": {},
                        "client_hint": {},
                    },
                },
                "EmbedWidgetConfig": {
                    "type": "object",
                    "description": "Public widget copy loaded by the embed script (no secrets).",
                    "properties": {
                        "agent_display_name": {
                            "type": "string",
                            "nullable": True,
                            "description": "Header title; omit or empty → browser may use data-title on script tag.",
                        },
                        "welcome_message": {
                            "type": "string",
                            "nullable": True,
                            "description": "Shown as first assistant bubble after chat opens.",
                        },
                        "collect_visitor_contact": {
                            "type": "boolean",
                            "description": "When true, widget shows contact gate (optional comment, then name/email/phone) before chat.",
                        },
                    },
                },
                "EmbedVisitorContactRequest": {
                    "type": "object",
                    "required": ["name", "visitor_session"],
                    "properties": {
                        "name": {"type": "string", "maxLength": 255},
                        "email": {
                            "type": "string",
                            "maxLength": 255,
                            "description": "Optional if phone is provided; both cannot be omitted.",
                        },
                        "phone": {
                            "type": "string",
                            "maxLength": 64,
                            "nullable": True,
                            "description": "Optional if email is provided; both cannot be omitted.",
                        },
                        "message": {
                            "type": "string",
                            "nullable": True,
                            "description": "Optional comment shown first in the widget; stored as initial_message on the lead row.",
                        },
                        "visitor_session": {
                            "type": "string",
                            "maxLength": 160,
                            "description": "Stable id from the widget (e.g. localStorage).",
                        },
                    },
                },
                "EmbedVisitorContactOk": {
                    "type": "object",
                    "required": ["ok"],
                    "properties": {"ok": {"type": "boolean"}},
                },
                "TenantEmbedBranding": {
                    "type": "object",
                    "properties": {
                        "embed_agent_display_name": {"type": "string"},
                        "embed_welcome_message": {"type": "string"},
                        "embed_collect_visitor_contact": {"type": "boolean"},
                        "embed_engagement_count": {
                            "type": "integer",
                            "description": "Successful embed chat turns (read-only via GET).",
                        },
                    },
                },
                "TenantEmbedBrandingPut": {
                    "type": "object",
                    "properties": {
                        "embed_agent_display_name": {"type": "string"},
                        "embed_welcome_message": {"type": "string"},
                        "embed_collect_visitor_contact": {"type": "boolean"},
                    },
                    "description": "Omitted fields keep existing values where applicable.",
                },
                "TenantAiCredentials": {
                    "type": "object",
                    "properties": {
                        "use_exclusive_openai": {
                            "type": "boolean",
                            "description": "When true, tenant embeddings and console chat use organisation credentials if a key is stored.",
                        },
                        "has_stored_openai_key": {
                            "type": "boolean",
                            "description": "Whether an encrypted API key exists (never returns the secret).",
                        },
                        "openai_api_base": {
                            "type": "string",
                            "nullable": True,
                            "maxLength": 512,
                            "description": "Optional OpenAI-compatible base URL when exclusive mode is active.",
                        },
                        "exclusive_active": {
                            "type": "boolean",
                            "description": "True when exclusive mode is on and a stored key exists.",
                        },
                    },
                },
                "TenantAiCredentialsPut": {
                    "type": "object",
                    "properties": {
                        "use_exclusive_openai": {"type": "boolean"},
                        "openai_api_base": {
                            "type": "string",
                            "nullable": True,
                            "maxLength": 512,
                            "description": "Applied only when exclusive is true; null or empty clears stored base.",
                        },
                        "openai_api_key": {
                            "type": "string",
                            "nullable": True,
                            "description": "Applied only when exclusive is true; omit to keep existing key; empty clears (exclusive without key returns 400).",
                        },
                    },
                    "description": "Disabling exclusive clears stored key and base on the server.",
                },
                "EmbedVisitorLeadsList": {
                    "type": "object",
                    "properties": {
                        "tenant_id": {"type": "string"},
                        "total": {"type": "integer"},
                        "limit": {"type": "integer"},
                        "offset": {"type": "integer"},
                        "leads": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "id": {"type": "string"},
                                    "created_at": {"type": "string", "nullable": True},
                                    "name": {"type": "string"},
                                    "email": {"type": "string"},
                                    "phone": {"type": "string", "nullable": True},
                                    "initial_message": {"type": "string", "nullable": True},
                                    "visitor_session": {"type": "string"},
                                    "embed_key_id": {"type": "string", "nullable": True},
                                    "embed_key_name": {"type": "string", "nullable": True},
                                },
                            },
                        },
                    },
                },
            },
        },
        "paths": {
            "/health": {
                "get": {
                    "tags": ["Health"],
                    "summary": "Health check",
                    "operationId": "healthCheck",
                    "responses": {
                        "200": {
                            "description": "OK",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {"status": {"type": "string", "example": "ok"}},
                                    }
                                }
                            },
                        }
                    },
                }
            },
            "/api/public/plans": {
                "get": {
                    "tags": ["Public"],
                    "summary": "Public plan catalog",
                    "operationId": "listPublicPlans",
                    "responses": {
                        "200": {
                            "description": "Plans payload",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {"plans": {"type": "array", "items": {}}},
                                    }
                                }
                            },
                        }
                    },
                }
            },
            "/api/marketplace/agents": {
                "get": {
                    "tags": ["Public"],
                    "summary": "Marketplace agents (metadata)",
                    "operationId": "listMarketplaceAgents",
                    "responses": {"200": {"description": "Agent cards"}},
                }
            },
            "/api/v1/tenant/subscription": {
                "get": {
                    "tags": ["Tenant · Subscription & preferences"],
                    "summary": "Current tenant subscription / limits",
                    "operationId": "getTenantSubscription",
                    "security": [{"SessionCookie": []}],
                    "responses": {
                        "200": {"description": "Plan, usage, limits"},
                        "401": {
                            "description": "Unauthorized",
                            "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}},
                        },
                    },
                }
            },
            "/api/v1/me/agent-preference": {
                "get": {
                    "tags": ["Tenant · Subscription & preferences"],
                    "summary": "Get my agent preference",
                    "operationId": "getAgentPreference",
                    "security": [{"SessionCookie": []}],
                    "responses": {"200": {"description": "Preference object"}},
                },
                "put": {
                    "tags": ["Tenant · Subscription & preferences"],
                    "summary": "Set my agent preference",
                    "operationId": "putAgentPreference",
                    "security": [{"SessionCookie": []}],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "agent_id": {"type": "string"},
                                        "config": {"type": "object", "additionalProperties": True},
                                    },
                                    "required": ["agent_id"],
                                }
                            }
                        },
                    },
                    "responses": {"200": {"description": "Saved preference"}},
                },
            },
            "/chat": {
                "post": {
                    "tags": ["Chat"],
                    "summary": "Grounded chat (session)",
                    "operationId": "sessionChat",
                    "security": [{"SessionCookie": []}],
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ChatRequest"}}},
                    },
                    "responses": {
                        "200": {
                            "description": "Answer + citations",
                            "content": {
                                "application/json": {"schema": {"$ref": "#/components/schemas/ChatResponse"}}
                            },
                        },
                        "400": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}}},
                        "401": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}}},
                        "403": {"description": "Plan / agent not allowed"},
                        "429": {"description": "Quota exceeded"},
                    },
                }
            },
            "/api/embed/chat": {
                "post": {
                    "tags": ["Embed"],
                    "summary": "Grounded chat (embed key)",
                    "operationId": "embedChat",
                    "security": [{"EmbedBearer": []}],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {"schema": {"$ref": "#/components/schemas/EmbedChatRequest"}}
                        },
                    },
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {"schema": {"$ref": "#/components/schemas/ChatResponse"}}
                            }
                        },
                        "401": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}}},
                    },
                }
            },
            "/api/embed/widget-config": {
                "get": {
                    "tags": ["Embed"],
                    "summary": "Widget branding & visitor-form flag",
                    "description": (
                        "Returns display name, welcome message, and whether to collect visitor contact before chat. "
                        "Requires allowed browser `Origin` for the embed key."
                    ),
                    "operationId": "embedWidgetConfig",
                    "security": [{"EmbedBearer": []}],
                    "responses": {
                        "200": {
                            "description": "Public widget settings",
                            "content": {
                                "application/json": {"schema": {"$ref": "#/components/schemas/EmbedWidgetConfig"}}
                            },
                        },
                        "401": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}}},
                        "403": {
                            "description": "Origin not allowed or organisation suspended",
                            "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}},
                        },
                    },
                }
            },
            "/api/embed/visitor-contact": {
                "post": {
                    "tags": ["Embed"],
                    "summary": "Submit visitor details (embed contact gate)",
                    "description": (
                        "Persists visitor submission: optional message (comment), name, and at least one of email or phone. "
                        "Keyed by visitor_session. Same auth and Origin rules as embed chat."
                    ),
                    "operationId": "embedVisitorContact",
                    "security": [{"EmbedBearer": []}],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/EmbedVisitorContactRequest"}
                            }
                        },
                    },
                    "responses": {
                        "200": {
                            "description": "Saved",
                            "content": {
                                "application/json": {"schema": {"$ref": "#/components/schemas/EmbedVisitorContactOk"}}
                            },
                        },
                        "400": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}}},
                        "401": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}}},
                        "403": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}}},
                        "500": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}}},
                    },
                }
            },
            "/api/v1/embed-keys": {
                "get": {
                    "tags": ["Embed"],
                    "summary": "List embed keys",
                    "operationId": "listEmbedKeys",
                    "security": [{"SessionCookie": []}],
                    "responses": {"200": {"description": "`{ keys: [...] }`"}},
                },
                "post": {
                    "tags": ["Embed"],
                    "summary": "Create embed key",
                    "operationId": "createEmbedKey",
                    "security": [{"SessionCookie": []}],
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "name": {"type": "string"},
                                        "allowed_collection_ids": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                        },
                                        "default_agent_id": {"type": "string"},
                                        "default_agent_config": {"type": "object"},
                                        "allowed_embed_origins": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                            "description": "Optional per-key browser Origin allow-list; omit for platform default",
                                        },
                                    },
                                    "required": ["name"],
                                }
                            }
                        }
                    },
                    "responses": {"201": {"description": "Returns full secret once"}},
                },
            },
            "/api/v1/embed-keys/{key_id}": {
                "patch": {
                    "tags": ["Embed"],
                    "summary": "Update embed key sites and/or OpenAI (BYOK) settings",
                    "operationId": "patchEmbedKey",
                    "security": [{"SessionCookie": []}],
                    "parameters": [
                        {
                            "name": "key_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "minProperties": 1,
                                    "properties": {
                                        "allowed_embed_origins": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                            "description": "Empty array clears per-key list → platform CORS default",
                                        },
                                        "openai_api_key": {
                                            "type": "string",
                                            "description": "OpenAI-compatible API key for embed chat completions only; omit to leave unchanged, empty string clears stored key",
                                            "nullable": True,
                                        },
                                        "openai_api_base": {
                                            "type": "string",
                                            "maxLength": 512,
                                            "description": "Optional API base URL; omit to leave unchanged, empty string clears",
                                            "nullable": True,
                                        },
                                    },
                                }
                            }
                        },
                    },
                    "responses": {"200": {"description": "Updated"}},
                },
                "delete": {
                    "tags": ["Embed"],
                    "summary": "Revoke embed key",
                    "operationId": "revokeEmbedKey",
                    "security": [{"SessionCookie": []}],
                    "parameters": [
                        {
                            "name": "key_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "responses": {"200": {"description": "Revoked"}, "404": {"description": "Not found"}},
                }
            },
            "/api/v1/tenant/embed-branding": {
                "get": {
                    "tags": ["Embed"],
                    "summary": "Widget appearance & engagement counter",
                    "operationId": "getTenantEmbedBranding",
                    "security": [{"SessionCookie": []}],
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {"schema": {"$ref": "#/components/schemas/TenantEmbedBranding"}}
                            }
                        },
                        "401": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}}},
                        "403": {"description": "Missing `embed:keys`"},
                    },
                },
                "put": {
                    "tags": ["Embed"],
                    "summary": "Update widget title, welcome text, contact gate",
                    "operationId": "putTenantEmbedBranding",
                    "security": [{"SessionCookie": []}],
                    "requestBody": {
                        "content": {
                            "application/json": {"schema": {"$ref": "#/components/schemas/TenantEmbedBrandingPut"}}
                        }
                    },
                    "responses": {
                        "200": {"description": "`{ ok: true }`"},
                        "401": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}}},
                        "403": {"description": "Missing `embed:keys`"},
                    },
                },
            },
            "/api/v1/tenant/ai-credentials": {
                "get": {
                    "tags": ["Knowledge base"],
                    "summary": "Organisation OpenAI credentials (BYOK)",
                    "description": "Requires `collections:manage`. Never returns the API key; indicates whether exclusive mode and a stored key are active.",
                    "operationId": "getTenantAiCredentials",
                    "security": [{"SessionCookie": []}],
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {"schema": {"$ref": "#/components/schemas/TenantAiCredentials"}}
                            }
                        },
                        "401": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}}},
                        "403": {"description": "Missing `collections:manage`"},
                    },
                },
                "put": {
                    "tags": ["Knowledge base"],
                    "summary": "Update organisation OpenAI credentials",
                    "description": (
                        "Requires `collections:manage`. Key and base are applied only while "
                        "`use_exclusive_openai` is true; turning exclusive off clears stored credentials."
                    ),
                    "operationId": "putTenantAiCredentials",
                    "security": [{"SessionCookie": []}],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {"schema": {"$ref": "#/components/schemas/TenantAiCredentialsPut"}}
                        },
                    },
                    "responses": {
                        "200": {
                            "description": "Saved; echoes flags like GET.",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "allOf": [
                                            {"type": "object", "properties": {"ok": {"type": "boolean"}}},
                                            {"$ref": "#/components/schemas/TenantAiCredentials"},
                                        ]
                                    }
                                }
                            },
                        },
                        "400": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}}},
                        "401": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}}},
                        "403": {"description": "Missing `collections:manage`"},
                    },
                },
            },
            "/api/v1/tenant/embed-visitor-leads": {
                "get": {
                    "tags": ["Embed"],
                    "summary": "List embed visitor submissions",
                    "description": "Requires `embed:keys`. Newest first.",
                    "operationId": "listEmbedVisitorLeads",
                    "security": [{"SessionCookie": []}],
                    "parameters": [
                        {
                            "name": "limit",
                            "in": "query",
                            "schema": {"type": "integer", "default": 50, "maximum": 500},
                            "description": "Page size (1–500)",
                        },
                        {
                            "name": "offset",
                            "in": "query",
                            "schema": {"type": "integer", "default": 0},
                        },
                    ],
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {"schema": {"$ref": "#/components/schemas/EmbedVisitorLeadsList"}}
                            }
                        },
                        "401": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}}},
                        "403": {"description": "Missing `embed:keys`"},
                    },
                }
            },
            "/api/v1/tenant/embed-visitor-leads/export": {
                "get": {
                    "tags": ["Embed"],
                    "summary": "Export visitor submissions as CSV",
                    "description": "Requires `embed:keys`. Up to 10000 most recent rows.",
                    "operationId": "exportEmbedVisitorLeadsCsv",
                    "security": [{"SessionCookie": []}],
                    "responses": {
                        "200": {
                            "description": "UTF-8 CSV attachment",
                            "content": {"text/csv": {"schema": {"type": "string", "format": "binary"}}},
                        },
                        "401": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}}},
                        "403": {"description": "Missing `embed:keys`"},
                    },
                }
            },
            "/upload-document": {
                "post": {
                    "tags": ["Knowledge base"],
                    "summary": "Upload PDF or TXT",
                    "operationId": "uploadDocument",
                    "security": [{"SessionCookie": []}],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "multipart/form-data": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "file": {"type": "string", "format": "binary"},
                                        "collection_name": {"type": "string"},
                                        "module": {"type": "string", "default": "DEFAULT"},
                                    },
                                    "required": ["file", "collection_name"],
                                }
                            }
                        },
                    },
                    "responses": {"200": {"description": "Indexed"}, "400": {}, "403": {}, "500": {}},
                }
            },
            "/delete-document": {
                "delete": {
                    "tags": ["Knowledge base"],
                    "summary": "Delete document from collection",
                    "operationId": "deleteDocument",
                    "security": [{"SessionCookie": []}],
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "collection_name": {"type": "string"},
                                        "file_name": {"type": "string"},
                                    },
                                    "required": ["collection_name", "file_name"],
                                }
                            }
                        }
                    },
                    "responses": {"200": {}, "404": {}},
                }
            },
            "/api/collections": {
                "get": {
                    "tags": ["Knowledge base"],
                    "summary": "List collections",
                    "operationId": "listCollections",
                    "security": [{"SessionCookie": []}],
                    "responses": {"200": {"description": "`{ collections: [...] }`"}},
                }
            },
            "/api/documents": {
                "get": {
                    "tags": ["Knowledge base"],
                    "summary": "List documents in collection",
                    "operationId": "listDocuments",
                    "security": [{"SessionCookie": []}],
                    "parameters": [
                        {
                            "name": "collection_name",
                            "in": "query",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "responses": {"200": {}, "400": {}},
                }
            },
            "/api/chunks": {
                "get": {
                    "tags": ["Knowledge base"],
                    "summary": "Preview retrieval chunks",
                    "operationId": "previewChunks",
                    "security": [{"SessionCookie": []}],
                    "parameters": [
                        {"name": "collection_name", "in": "query", "required": True, "schema": {"type": "string"}},
                        {"name": "file_name", "in": "query", "required": True, "schema": {"type": "string"}},
                    ],
                    "responses": {"200": {"description": "`{ chunks: [...] }`"}},
                }
            },
            "/api/v1/kb/documents/{document_id}/index-debug": {
                "get": {
                    "tags": ["Knowledge base"],
                    "summary": "Verify embeddings vs DB after upload",
                    "operationId": "kbDocumentIndexDebug",
                    "security": [{"SessionCookie": []}],
                    "parameters": [
                        {"name": "document_id", "in": "path", "required": True, "schema": {"type": "string"}},
                        {
                            "name": "tenant_id",
                            "in": "query",
                            "required": False,
                            "schema": {"type": "string"},
                            "description": "Superusers only — target organisation UUID.",
                        },
                    ],
                    "responses": {
                        "200": {"description": "Chroma counts, warnings, troubleshooting hints"},
                        "404": {},
                    },
                }
            },
            "/api/v1/kb/retrieval-probe": {
                "post": {
                    "tags": ["Knowledge base"],
                    "summary": "Test vector retrieval (same path as chat)",
                    "operationId": "kbRetrievalProbe",
                    "security": [{"SessionCookie": []}],
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "query": {"type": "string"},
                                        "collection_slugs": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                            "description": "Empty/unset = all tenant collections",
                                        },
                                        "tenant_id": {
                                            "type": "string",
                                            "description": "Superusers only — probe another org",
                                        },
                                        "k_per_collection": {"type": "integer"},
                                    },
                                    "required": ["query"],
                                }
                            }
                        }
                    },
                    "responses": {"200": {}, "400": {}},
                }
            },
            "/api/v1/kb/audit-events": {
                "get": {
                    "tags": ["Knowledge base"],
                    "summary": "KB audit timeline (ingest, probes, deletes)",
                    "operationId": "kbAuditEvents",
                    "security": [{"SessionCookie": []}],
                    "parameters": [
                        {"name": "limit", "in": "query", "schema": {"type": "integer"}},
                        {
                            "name": "tenant_id",
                            "in": "query",
                            "schema": {"type": "string"},
                            "description": "Superusers only",
                        },
                    ],
                    "responses": {"200": {}},
                }
            },
            "/api/agents": {
                "get": {
                    "tags": ["Knowledge base"],
                    "summary": "Registered agent ids (console)",
                    "operationId": "listAgents",
                    "security": [{"SessionCookie": []}],
                    "responses": {"200": {"description": "`{ agents: [...] }`"}},
                }
            },
            "/api/v1/roles": {
                "get": {
                    "tags": ["Users"],
                    "summary": "List role names for tenant",
                    "operationId": "listTenantRoles",
                    "security": [{"SessionCookie": []}],
                    "responses": {"200": {"description": "`{ roles: [\"Admin\", ...] }`"}},
                }
            },
            "/api/v1/users": {
                "get": {
                    "tags": ["Users"],
                    "summary": "List tenant users",
                    "operationId": "listUsers",
                    "security": [{"SessionCookie": []}],
                    "responses": {"200": {"description": "Array of users"}},
                },
                "post": {
                    "tags": ["Users"],
                    "summary": "Create user",
                    "operationId": "createUser",
                    "security": [{"SessionCookie": []}],
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "username": {"type": "string"},
                                        "password": {"type": "string"},
                                        "email": {"type": "string"},
                                        "roles": {"type": "array", "items": {"type": "string"}},
                                    },
                                    "required": ["username", "password"],
                                }
                            }
                        }
                    },
                    "responses": {"201": {}, "400": {}, "409": {}},
                },
            },
            "/api/v1/users/{user_id}": {
                "patch": {
                    "tags": ["Users"],
                    "summary": "Patch user (e.g. is_active)",
                    "operationId": "patchUser",
                    "security": [{"SessionCookie": []}],
                    "parameters": [
                        {"name": "user_id", "in": "path", "required": True, "schema": {"type": "string"}}
                    ],
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {"is_active": {"type": "boolean"}},
                                }
                            }
                        }
                    },
                    "responses": {"200": {}, "404": {}},
                }
            },
            "/api/v1/users/{user_id}/roles": {
                "put": {
                    "tags": ["Users"],
                    "summary": "Replace user roles",
                    "operationId": "putUserRoles",
                    "security": [{"SessionCookie": []}],
                    "parameters": [
                        {"name": "user_id", "in": "path", "required": True, "schema": {"type": "string"}}
                    ],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {"roles": {"type": "array", "items": {"type": "string"}}},
                                    "required": ["roles"],
                                }
                            }
                        },
                    },
                    "responses": {"200": {}, "400": {}, "404": {}},
                }
            },
        },
    }
