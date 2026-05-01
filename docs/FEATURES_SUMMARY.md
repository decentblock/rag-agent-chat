# Nexura — product summary (one page)

**Nexura** is a multi-tenant retrieval-augmented generation (RAG) web platform: organisations keep isolated knowledge collections, users sign in with tenant-aware credentials, and AI agents answer using **only** approved documents—never another tenant’s data.

## Core capabilities

| Area | What you get |
|------|----------------|
| **Tenancy** | Every record is scoped to a `tenant`. Login requires `tenant_slug` + username + password. APIs resolve the principal from the session and refuse cross-tenant IDs. |
| **Knowledge base** | Upload **PDF** or **TXT** into named **collections**. Content is chunked, embedded, and stored in **Chroma** under a deterministic physical name per tenant + collection. |
| **Grounded chat** | **POST /chat** runs a registered **agent** with tenant-safe retrieval. Answers include **citations** (sources). Optional **collection_ids** narrows which collections are searched. |
| **RBAC** | **Admin**, **Editor**, and **Viewer** roles bundle permissions (`documents:*`, `collections:manage`, `chat:query`, `users:manage`, **`embed:keys`**). Admins have `*`. |
| **Agent marketplace** | Four built-in agents share the same secure retrieval core but apply different **workflow prompts**. Users pick an agent in the console; preference and JSON **config** persist per user (`UserAgentPreference`). |
| **Console UI** | Landing page (marketing), **Documentation** (`/docs`), login, and authenticated **dashboard** (overview, agents, chat, library, **embed** snippet). |
| **Embeddable chat** | **Embed API keys** + **`/api/embed/chat`** + **`static/embed/nexura-chat.js`** let customers mount a floating widget on their sites (CORS via **`EMBED_CORS_ORIGINS`**). |

## Built-in agents (at a glance)

1. **Document Q&A** — Default grounded Q&A.  
2. **Research synthesizer** — Neutral multi-source framing.  
3. **Support router** — Intent-oriented, snippet-grounded reply suggestions.  
4. **SQL analyst** — Read-only **SELECT** drafting from **documented** schema context only (no live warehouse execution).

Shared config keys (where applicable): `user_instructions`, `response_language`; each agent may add fields such as `synthesis_focus`, `brand_voice`, `sql_dialect`, `schema_context`.

## Who it is for

- Teams shipping **internal or customer-facing** assistants that must **respect document boundaries** and **tenant isolation**.  
- Operators who want a **single codebase** for ingestion, RBAC, chat, and an **extensible agent registry**—without mixing customer embeddings.

## Quick limits & honesty

- Session auth uses Flask **cookies** (`SESSION_SECRET` required in production).  
- **Embeddable chat** uses bearer **`nxemb_…`** keys — restrict **`EMBED_CORS_ORIGINS`** and revoke keys if exposed.  
- Pricing on the marketing site is **illustrative** until billing integration.

For APIs, configuration, database schema, ingestion details, and extension points, see **`docs/TECHNICAL.md`**. For **step-by-step deployment** (production setup, Gunicorn, nginx, backups), see **`docs/DEPLOYMENT.md`**. Both are rendered on **`/docs`** in the running app.
