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
                "description": "Cross-origin widget chat (`nxemb_…` key) and tenant embed-key CRUD (`embed:keys`).",
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
                            "description": "Optional collection UUIDs to scope retrieval.",
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
                        "collection_ids": {"type": "array", "items": {"type": "string"}},
                        "llm_route": {"type": "string"},
                        "llm_config_ref": {},
                        "client_hint": {},
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
            "/api/agents": {
                "get": {
                    "tags": ["Knowledge base"],
                    "summary": "Registered agent ids (console)",
                    "operationId": "listAgents",
                    "security": [{"SessionCookie": []}],
                    "responses": {"200": {"description": "`{ agents: [...] }`"}},
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
