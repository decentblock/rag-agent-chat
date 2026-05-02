# Nexura — product summary (one page)

**Nexura** is a multi-tenant retrieval-augmented generation (RAG) web platform: organisations keep isolated knowledge collections, users sign in with tenant-aware credentials, and AI agents answer using **only** approved documents—never another tenant’s data.

## Core capabilities

| Area | What you get |
|------|----------------|
| **Tenancy** | Every record is scoped to a `tenant`. Login requires `tenant_slug` + username + password. APIs resolve the principal from the session and refuse cross-tenant IDs. |
| **Knowledge base** | Upload **PDF** or **TXT** into named **collections**. Content is chunked, embedded, and stored in **Chroma** under a deterministic physical name per tenant + collection. |
| **Grounded chat** | **POST /chat** runs a registered **agent** with tenant-safe retrieval. Answers include **citations** (sources). Optional **collection_ids** narrows which collections are searched. |
| **RBAC** | **Admin**, **Editor**, and **Viewer** roles bundle permissions (`documents:*`, `collections:manage`, `chat:query`, `users:manage`, **`embed:keys`**). Admins have `*`. Organisation admins use console **Team** to add users and assign roles (respects plan **max_users**). |
| **Agent marketplace** | Four built-in agents share the same secure retrieval core but apply different **workflow prompts**. Users pick an agent in the console; preference and JSON **config** persist per user (`UserAgentPreference`). |
| **Console UI** | Landing, **`/docs`** (API reference), login, **dashboard** (**Team** when `users:manage`). Users with **`is_superuser`** also see **Organisations**, **Platform settings**, **Product & deployment**, and **Technical reference** in the sidebar (`/super/*`). |
| **Embeddable chat** | **Embed API keys** + **`/api/embed/chat`** + **`static/embed/nexura-chat.js`** let customers mount a floating widget on their sites (CORS via **`EMBED_CORS_ORIGINS`**). |

## Built-in agents (at a glance)

1. **Document Q&A** — Default grounded Q&A.  
2. **Research synthesizer** — Neutral multi-source framing.  
3. **Support router** — Intent-oriented, snippet-grounded reply suggestions.  
4. **SQL analyst** — Read-only **SELECT** drafting from **documented** schema context only (no live warehouse execution).

Shared config keys (where applicable): `user_instructions`, `response_language`; each agent may add fields such as `synthesis_focus`, `brand_voice`, `sql_dialect`, `schema_context`.

## Marketplace agents — platform operators (`/super/*`)

This section is for **platform superusers** (sidebar: **Organisations**, **Technical reference**, etc.).

| Topic | What to know |
|--------|----------------|
| **What “marketplace” means** | **`agent_catalog.py`** defines **`MARKETPLACE_AGENTS`** (names, descriptions, optional **`config_fields`**). **`agents/bootstrap.py`** registers the **runnable** **`Agent`** classes. **`GET /api/marketplace/agents`** lists rows as **`installed`** only when catalog **`available`** and the registry has that **`agent_id`**. |
| **How orgs use agents** | Tenant users pick an agent in the console; **`UserAgentPreference`** stores **`agent_id`** + JSON **`config`**. **Embed** keys can set **`default_agent_id`** and **`agent_config_json`**. Chat/embed calls the registry after **plan enforcement**. |
| **What you set per organisation** | On **`/super/organisations`**, **Plan & access** sets **`plan_slug`** (tier caps + whether the plan allows **all** installed agents or only a **finite** list — see **`plans_catalog.PLANS`**). The **Agents** card saves an optional **tenant allowlist** (`allowed_agent_ids`): it **narrows** what that org may run on top of the plan (finite plan ⇒ intersection; unrestricted plan ⇒ whitelist; empty list ⇒ block all). Clearing the override restores plan-only behaviour. |
| **Personalisation** | **Allowlist** = which agents the org **may** run. **Tone / instructions** = per-user preference **`config`** and/or per-embed-key **`agent_config_json`**. There is **no** single “org default agent” field on the tenant row today. |
| **Adding more agents (engineering)** | Implement **`Agent`**, **`registry.register`** in **`agents/bootstrap.py`**, add a **`MARKETPLACE_AGENTS`** row with matching **`agent_id`**. For tiers with a finite **`allowed_agent_ids`**, extend that list in **`plans_catalog.py`** if the new agent should appear there. Roadmap-only rows can use **`available: False`** without registering code. |

Full detail: **`docs/TECHNICAL.md`** §17.16 (subsection **Marketplace agents — operator summary**), §15–§16, §22, §24.

## Who it is for

- Teams shipping **internal or customer-facing** assistants that must **respect document boundaries** and **tenant isolation**.  
- Operators who want a **single codebase** for ingestion, RBAC, chat, and an **extensible agent registry**—without mixing customer embeddings.

## Quick limits & honesty

- Session auth uses Flask **cookies** (`SESSION_SECRET` required in production).  
- **Embeddable chat** uses bearer **`nxemb_…`** keys — restrict **`EMBED_CORS_ORIGINS`** and revoke keys if exposed.  
- Pricing on the marketing site is **illustrative** until billing integration.

For **HTTP APIs**, open **`/docs`** (Swagger UI; spec **`/api/openapi.json`**). For **product overview** and **deployment** (generic steps plus **DigitalOcean Droplet**), platform superusers use **Console → Product & deployment** (`/super/guides`, sourced from **`docs/FEATURES_SUMMARY.md`** and **`docs/DEPLOYMENT.md`**) — including **Marketplace agents — platform operators**. For full architecture and schema, **Console → Technical reference** (`/super/technical`, **`docs/TECHNICAL.md`**). **Organisations** (`/super/organisations`) is the cross-tenant admin console: plans, suspension, billing stubs, agent allowlists, and user enable/disable — see **`docs/TECHNICAL.md`** §17.16 and the **Marketplace agents — operator summary** subsection.
