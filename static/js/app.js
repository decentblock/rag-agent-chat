(function () {
  "use strict";

  const panelCopy = {
    overview: {
      title: "Overview",
      desc: "Service status and quick checks.",
    },
    agents: {
      title: "Agent marketplace",
      desc: "Install workflows for grounded chat and embed-ready routing.",
    },
    chat: {
      title: "Chat",
      desc: "Uses your saved marketplace agent + collection scope.",
    },
    library: {
      title: "Knowledge base",
      desc: "Upload files, browse collections, preview chunks, delete documents.",
    },
    embed: {
      title: "Embed",
      desc: "Mint API keys and paste the widget snippet on customer websites.",
    },
    team: {
      title: "Team",
      desc: "Invite users to your organisation and assign Admin, Editor, or Viewer roles.",
    },
  };

  function toast(message, variant) {
    const stack = document.getElementById("toast-stack");
    if (!stack) return;
    const el = document.createElement("div");
    el.className = "toast toast-" + (variant === "success" ? "success" : "error");
    el.textContent = message;
    stack.appendChild(el);
    setTimeout(() => {
      el.remove();
    }, 5200);
  }

  async function parseJsonResponse(res) {
    const text = await res.text();
    try {
      return text ? JSON.parse(text) : {};
    } catch {
      return { raw: text };
    }
  }

  async function apiFetch(url, options) {
    const res = await fetch(url, {
      credentials: "same-origin",
      ...options,
    });
    if (res.status === 401) {
      window.location.href = "/login?next=" + encodeURIComponent(window.location.pathname);
      throw new Error("Unauthorized");
    }
    const data = await parseJsonResponse(res);
    if (!res.ok) {
      throw new Error(data.error || data.message || res.statusText || "Request failed");
    }
    return data;
  }

  /* Agent marketplace (defined before nav binds tabs). */
  let marketplaceAgents = [];
  let agentPreference = { agent_id: "rag_document_qa", config: {} };
  /** @type {string[] | null} null = all agents allowed */
  let subscriptionAllowedAgents = null;
  let modalEditingAgent = null;

  function agentAllowedByPlan(agentId) {
    const aid = String(agentId || "").toLowerCase();
    if (subscriptionAllowedAgents === null) return true;
    return subscriptionAllowedAgents.includes(aid);
  }

  async function loadTenantSubscription() {
    subscriptionAllowedAgents = null;
    const strip = document.getElementById("subscription-strip");
    try {
      const s = await apiFetch("/api/v1/tenant/subscription");
      const ids = s.limits && s.limits.allowed_agent_ids;
      subscriptionAllowedAgents = Array.isArray(ids)
        ? ids.map((x) => String(x).toLowerCase())
        : null;
      if (strip && s) {
        strip.hidden = false;
        const label = s.plan_label || s.plan_slug || "";
        const use = s.usage || {};
        const lim = s.limits || {};
        const chatCap = lim.monthly_chat_quota;
        const chatUsed = use.chat_count_month ?? 0;
        const chatPart =
          chatCap != null ? ` · Chats (UTC month): ${chatUsed} / ${chatCap}` : "";
        const usersPart = ` · Users: ${use.users_active ?? "—"}${
          lim.max_users != null ? ` / ${lim.max_users}` : ""
        }`;
        const colPart = ` · Collections: ${use.collections ?? "—"}${
          lim.max_collections != null ? ` / ${lim.max_collections}` : ""
        }`;
        const embedPart = ` · Embed keys: ${use.embed_keys_active ?? "—"}${
          lim.max_embed_keys != null ? ` / ${lim.max_embed_keys}` : ""
        }`;
        strip.textContent = `Plan: ${label}${chatPart}${usersPart}${colPart}${embedPart}`;
      }
    } catch {
      if (strip) strip.hidden = true;
    }
  }

  function syncChatAgentBar() {
    const label = document.getElementById("chat-active-agent");
    const badge = document.getElementById("chat-agent-badge");
    const aid = agentPreference.agent_id;
    const row = marketplaceAgents.find((a) => a.agent_id === aid);
    if (label) label.textContent = row ? row.name : aid;
    if (badge) {
      if (row && row.badge) {
        badge.hidden = false;
        badge.textContent = row.badge;
      } else {
        badge.hidden = true;
      }
    }
  }

  function iconGlyph(icon) {
    const m = { layers: "▦", search: "⌕", lifebuoy: "◎", table: "#" };
    return m[icon] || "◇";
  }

  function renderMarketplaceGrid() {
    const grid = document.getElementById("marketplace-grid");
    if (!grid) return;

    if (!marketplaceAgents.length) {
      grid.innerHTML = '<p class="muted">No marketplace entries configured.</p>';
      return;
    }

    grid.innerHTML = marketplaceAgents
      .map((a) => {
        const active =
          a.agent_id === agentPreference.agent_id ? " active" : "";
        const planOk = agentAllowedByPlan(a.agent_id);
        const disabled = !a.installed || !planOk ? " disabled" : "";
        const badgeHtml = a.badge
          ? `<span class="badge ${a.installed ? "badge-accent" : "badge-soon"}">${escapeHtml(a.badge)}</span>`
          : "";
        let foot = "Coming soon";
        if (a.installed && !planOk) foot = "Not on your plan · upgrade to unlock";
        else if (a.installed) foot = "Tap to configure & activate";
        return `<button type="button" class="agent-card${active}${disabled}" data-agent-id="${escapeAttr(a.agent_id)}" ${a.installed && planOk ? "" : "disabled"}>
          <div class="agent-card-head">
            <div class="agent-card-icon">${escapeHtml(iconGlyph(a.icon))}</div>
            ${badgeHtml}
          </div>
          <h4>${escapeHtml(a.name)}</h4>
          <p class="tagline">${escapeHtml(a.tagline || "")}</p>
          <p class="desc">${escapeHtml(a.description || "")}</p>
          <span class="muted" style="font-size:0.78rem;">${escapeHtml(foot)}</span>
        </button>`;
      })
      .join("");

    grid.querySelectorAll(".agent-card:not([disabled])").forEach((btn) => {
      btn.addEventListener("click", () => {
        const id = btn.getAttribute("data-agent-id");
        const row = marketplaceAgents.find((x) => x.agent_id === id);
        if (row) openAgentModal(row);
      });
    });
  }

  function renderModalFields(agent, cfg) {
    const wrap = document.getElementById("agent-settings-fields");
    if (!wrap) return;
    const fields = agent.config_fields || [];
    if (!fields.length) {
      wrap.innerHTML =
        '<p class="muted">No extra configuration required — save to activate this agent.</p>';
      return;
    }
    wrap.innerHTML = fields
      .map((f) => {
        const val = cfg[f.key] != null ? String(cfg[f.key]) : "";
        const id = "cfg-" + encodeURIComponent(f.key).replace(/%/g, "_");
        if (f.type === "textarea") {
          return `<label class="field"><span class="field-label">${escapeHtml(f.label)}</span><textarea class="input textarea" id="${id}" rows="3" placeholder="${escapeAttr(f.placeholder || "")}">${escapeHtml(val)}</textarea>${f.help ? `<span class="muted" style="font-size:0.8rem;">${escapeHtml(f.help)}</span>` : ""}</label>`;
        }
        return `<label class="field"><span class="field-label">${escapeHtml(f.label)}</span><input class="input" type="text" id="${id}" value="${escapeAttr(val)}" placeholder="${escapeAttr(f.placeholder || "")}" />${f.help ? `<span class="muted" style="font-size:0.8rem;">${escapeHtml(f.help)}</span>` : ""}</label>`;
      })
      .join("");
  }

  function readModalConfig(agent) {
    const cfg = {};
    for (const f of agent.config_fields || []) {
      const id = "cfg-" + encodeURIComponent(f.key).replace(/%/g, "_");
      const el = document.getElementById(id);
      if (el) cfg[f.key] = el.value.trim();
    }
    return cfg;
  }

  function openAgentModal(agent) {
    modalEditingAgent = agent;
    const dlg = document.getElementById("agent-settings-dialog");
    const title = document.getElementById("agent-settings-title");
    const sub = document.getElementById("agent-settings-sub");
    if (title) title.textContent = agent.name;
    if (sub) sub.textContent = agent.tagline || "";

    const cfg =
      agentPreference.agent_id === agent.agent_id
        ? Object.assign({}, agentPreference.config || {})
        : {};

    renderModalFields(agent, cfg);
    dlg?.showModal();
    document.getElementById("agent-settings-save")?.focus();
  }

  function closeAgentModal() {
    document.getElementById("agent-settings-dialog")?.close();
    modalEditingAgent = null;
  }

  async function persistAgentPreference(agentId, cfg) {
    const saved = await apiFetch("/api/v1/me/agent-preference", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ agent_id: agentId, config: cfg }),
    });
    agentPreference = saved;
    renderMarketplaceGrid();
    syncChatAgentBar();
    toast("Agent preference saved", "success");
    closeAgentModal();
  }

  async function refreshMarketplace() {
    const grid = document.getElementById("marketplace-grid");
    const status = document.getElementById("marketplace-status");
    if (!grid) return;

    grid.setAttribute("aria-busy", "true");
    if (status) status.textContent = "Loading catalog…";

    try {
      await loadTenantSubscription();
      const catRes = await fetch("/api/marketplace/agents");
      const catJson = await catRes.json();
      if (!catRes.ok) throw new Error(catJson.error || "Catalog unavailable");
      marketplaceAgents = catJson.agents || [];

      try {
        agentPreference = await apiFetch("/api/v1/me/agent-preference");
      } catch {
        agentPreference = { agent_id: "rag_document_qa", config: {} };
      }

      renderMarketplaceGrid();
      syncChatAgentBar();
      if (status)
        status.textContent =
          "Catalog synced · your preference persists per user.";
    } catch (e) {
      if (status) status.textContent = String(e.message || e);
      toast(e.message || "Marketplace failed", "error");
    } finally {
      grid.removeAttribute("aria-busy");
    }
  }

  document.getElementById("btn-reload-marketplace")?.addEventListener("click", () => {
    refreshMarketplace().catch((err) =>
      toast(err.message || "Reload failed", "error")
    );
  });

  document.getElementById("btn-agent-quick-setup")?.addEventListener("click", () => {
    const row = marketplaceAgents.find((a) => a.agent_id === agentPreference.agent_id);
    if (row && row.installed) openAgentModal(row);
    else toast("Choose an available agent from the Agents tab.", "error");
  });

  document.getElementById("agent-settings-close")?.addEventListener("click", closeAgentModal);
  document.getElementById("agent-settings-cancel")?.addEventListener("click", closeAgentModal);

  document.getElementById("agent-settings-save")?.addEventListener("click", async () => {
    if (!modalEditingAgent) return;
    const cfg = readModalConfig(modalEditingAgent);
    try {
      await persistAgentPreference(modalEditingAgent.agent_id, cfg);
    } catch (e) {
      toast(e.message || "Save failed", "error");
    }
  });

  document.getElementById("agent-settings-dialog")?.addEventListener("click", (ev) => {
    if (ev.target.id === "agent-settings-dialog") closeAgentModal();
  });

  /* Tabs */
  document.querySelectorAll(".nav-item[data-tab]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const tab = btn.getAttribute("data-tab");
      document.querySelectorAll(".nav-item").forEach((b) => {
        b.classList.toggle("active", b === btn);
        b.removeAttribute("aria-current");
      });
      btn.setAttribute("aria-current", "page");

      document.querySelectorAll(".panel").forEach((p) => {
        const id = "panel-" + tab;
        const show = p.id === id;
        p.hidden = !show;
      });

      const meta = panelCopy[tab];
      if (meta) {
        const titleEl = document.getElementById("panel-title");
        const descEl = document.getElementById("panel-desc");
        if (titleEl) titleEl.textContent = meta.title;
        if (descEl) descEl.textContent = meta.desc;
      }

      if (tab === "agents") {
        refreshMarketplace().catch((err) =>
          toast(err.message || "Marketplace failed", "error")
        );
      }
      if (tab === "embed") {
        refreshEmbedPanel().catch((err) =>
          toast(err.message || "Embed panel failed", "error")
        );
      }
      if (tab === "team") {
        refreshTeamPanel().catch((err) =>
          toast(err.message || "Team panel failed", "error")
        );
      }
    });
  });

  /* Health */
  async function refreshHealth() {
    const badge = document.getElementById("health-badge");
    const raw = document.getElementById("health-raw");
    if (!badge || !raw) return;
    badge.textContent = "Checking…";
    badge.className = "badge badge-muted";
    raw.textContent = "—";
    raw.classList.add("empty");
    try {
      const data = await apiFetch("/health");
      badge.textContent = "Healthy";
      badge.className = "badge badge-ok";
      raw.textContent = JSON.stringify(data, null, 2);
      raw.classList.remove("empty");
    } catch (e) {
      badge.textContent = "Unreachable";
      badge.className = "badge badge-bad";
      raw.textContent = String(e.message || e);
      raw.classList.remove("empty");
      toast(e.message || "Health check failed", "error");
    }
  }

  const btnHealth = document.getElementById("btn-refresh-health");
  if (btnHealth) btnHealth.addEventListener("click", refreshHealth);
  refreshHealth();
  loadTenantSubscription().catch(() => {});

  /* Chat */
  const transcript = document.getElementById("chat-transcript");
  const chatForm = document.getElementById("chat-form");
  const chatInput = document.getElementById("chat-input");

  function appendBubble(role, html) {
    if (!transcript) return;
    const div = document.createElement("div");
    div.className = "chat-bubble " + role;
    div.innerHTML = html;
    transcript.appendChild(div);
    transcript.scrollTop = transcript.scrollHeight;
  }

  document.getElementById("btn-reset-chat")?.addEventListener("click", () => {
    if (transcript) transcript.innerHTML = "";
    toast("Transcript cleared", "success");
  });

  chatForm?.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const msg = (chatInput?.value || "").trim();
    if (!msg) return;

    appendBubble("user", escapeHtml(msg));
    chatInput.value = "";

    const coll =
      document.getElementById("collection-select")?.value?.trim() || "";

    try {
      const reqBody = {
        chat_message: msg,
        agent_id: agentPreference.agent_id,
        agent_config: agentPreference.config,
      };
      if (coll) reqBody.collection_ids = [coll];

      const data = await apiFetch("/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(reqBody),
      });

      let answerText =
        typeof data.answer === "string"
          ? data.answer
          : data.answer != null
            ? JSON.stringify(data.answer)
            : "";

      let citationsHtml = "";
      if (Array.isArray(data.citations) && data.citations.length) {
        citationsHtml =
          '<div class="citations"><strong>Sources:</strong> ' +
          escapeHtml(data.citations.join(", ")) +
          "</div>";
      }

      appendBubble("assistant", escapeHtml(answerText) + citationsHtml);
    } catch (e) {
      toast(e.message || "Chat failed", "error");
      appendBubble(
        "assistant",
        '<span class="muted">Error: ' + escapeHtml(String(e.message || e)) + "</span>"
      );
    }
  });

  function escapeHtml(s) {
    const d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
  }

  function escapeAttr(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;")
      .replace(/</g, "&lt;");
  }

  function getAppOrigin() {
    const el = document.getElementById("nexura-console-bootstrap");
    return (el && el.dataset.appOrigin) || window.location.origin;
  }

  function getCurrentUserId() {
    const el = document.getElementById("nexura-console-bootstrap");
    return (el && el.dataset.currentUserId) || "";
  }

  let tenantRoleNames = [];
  let teamUsersCache = [];

  function renderTeamAddRoleBoxes(names) {
    const wrap = document.getElementById("team-add-role-checkboxes");
    if (!wrap) return;
    if (!names.length) {
      wrap.innerHTML = '<p class="muted">No roles — contact support.</p>';
      return;
    }
    wrap.innerHTML = names
      .map((n) => {
        const checked = n === "Viewer" ? " checked" : "";
        return (
          '<label class="team-role-label"><input type="checkbox" class="team-role-add-cb" value="' +
          escapeAttr(n) +
          '"' +
          checked +
          ' /><span>' +
          escapeHtml(n) +
          "</span></label>"
        );
      })
      .join("");
  }

  function renderTeamDialogRoleBoxes(names, selected) {
    const wrap = document.getElementById("team-roles-dialog-fields");
    const sel = new Set(selected || []);
    if (!wrap) return;
    wrap.innerHTML = names
      .map((n) => {
        const checked = sel.has(n) ? " checked" : "";
        return (
          '<label class="team-role-label"><input type="checkbox" class="team-role-edit-cb" value="' +
          escapeAttr(n) +
          '"' +
          checked +
          ' /><span>' +
          escapeHtml(n) +
          "</span></label>"
        );
      })
      .join("");
  }

  async function loadTenantRolesForTeam() {
    const wrap = document.getElementById("team-add-role-checkboxes");
    if (!wrap) return;
    try {
      const data = await apiFetch("/api/v1/roles");
      tenantRoleNames = Array.isArray(data.roles) ? data.roles : [];
      renderTeamAddRoleBoxes(tenantRoleNames);
    } catch (e) {
      tenantRoleNames = [];
      wrap.innerHTML =
        '<p class="muted">' + escapeHtml(e.message || "Cannot load roles") + "</p>";
      throw e;
    }
  }

  async function refreshTeamUsersTable() {
    const tbody = document.getElementById("team-users-body");
    if (!tbody) return;
    tbody.innerHTML =
      '<tr><td colspan="5" class="muted center">Loading…</td></tr>';
    try {
      const users = await apiFetch("/api/v1/users");
      teamUsersCache = Array.isArray(users) ? users : [];
      const selfId = getCurrentUserId();
      if (!teamUsersCache.length) {
        tbody.innerHTML =
          '<tr><td colspan="5" class="muted center">No users yet.</td></tr>';
        return;
      }
      tbody.innerHTML = teamUsersCache
        .map((u) => {
          const active = u.is_active !== false;
          const roles = (u.roles || []).join(", ") || "—";
          const email = u.email ? escapeHtml(u.email) : "—";
          let toggle =
            '<input type="checkbox" class="team-active-cb" data-user-id="' +
            escapeAttr(u.id) +
            '"' +
            (active ? " checked" : "") +
            (u.id === selfId ? " disabled title=\"You cannot disable your own account\"" : "") +
            ' aria-label="Active for ' +
            escapeAttr(u.username || "") +
            '" />';
          let actions =
            '<button type="button" class="btn btn-secondary btn-sm btn-team-roles" data-user-id="' +
            escapeAttr(u.id) +
            '">Roles</button>';
          return (
            "<tr><td>" +
            escapeHtml(u.username || "") +
            "</td><td>" +
            email +
            '</td><td style="max-width:14rem;word-break:break-word">' +
            escapeHtml(roles) +
            '</td><td class="center">' +
            toggle +
            '</td><td class="col-actions"><div class="row-actions">' +
            actions +
            "</div></td></tr>"
          );
        })
        .join("");
    } catch (e) {
      tbody.innerHTML =
        '<tr><td colspan="5" class="muted center">' +
        escapeHtml(e.message || "Failed to load users") +
        "</td></tr>";
    }
  }

  async function refreshTeamPanel() {
    if (!document.getElementById("panel-team")) return;
    await loadTenantRolesForTeam();
    await refreshTeamUsersTable();
  }

  function openTeamRolesDialog(userId) {
    const dlg = document.getElementById("team-roles-dialog");
    const title = document.getElementById("team-roles-dialog-title");
    const sub = document.getElementById("team-roles-dialog-sub");
    const hid = document.getElementById("team-roles-target-user-id");
    const u = teamUsersCache.find((x) => x.id === userId);
    if (!dlg || !hid || !u) return;
    hid.value = userId;
    if (title) title.textContent = "Roles · " + (u.username || "");
    if (sub)
      sub.textContent =
        u.id === getCurrentUserId()
          ? "You must keep a role that can manage users."
          : "Choose one or more roles.";
    renderTeamDialogRoleBoxes(tenantRoleNames, u.roles || []);
    dlg.showModal();
    document.getElementById("team-roles-dialog-close")?.focus();
  }

  function closeTeamRolesDialog() {
    document.getElementById("team-roles-dialog")?.close();
  }

  document.getElementById("team-add-form")?.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const uEl = document.getElementById("team-add-username");
    const pEl = document.getElementById("team-add-password");
    const eEl = document.getElementById("team-add-email");
    const username = (uEl && uEl.value.trim()) || "";
    const password = (pEl && pEl.value) || "";
    const email = (eEl && eEl.value.trim()) || "";
    const roles = Array.from(document.querySelectorAll(".team-role-add-cb:checked")).map(
      (cb) => cb.value
    );
    if (!username || !password) return;
    if (!roles.length) {
      toast("Select at least one role", "error");
      return;
    }
    try {
      await apiFetch("/api/v1/users", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username,
          password,
          roles,
          ...(email ? { email } : {}),
        }),
      });
      toast("User created", "success");
      if (uEl) uEl.value = "";
      if (pEl) pEl.value = "";
      if (eEl) eEl.value = "";
      renderTeamAddRoleBoxes(tenantRoleNames);
      await refreshTeamUsersTable();
      loadTenantSubscription().catch(() => {});
    } catch (e) {
      toast(e.message || "Create failed", "error");
    }
  });

  document.getElementById("btn-refresh-team")?.addEventListener("click", () => {
    refreshTeamUsersTable().catch((e) =>
      toast(e.message || "Refresh failed", "error")
    );
  });

  document.getElementById("team-users-body")?.addEventListener("change", async (ev) => {
    const t = ev.target;
    if (!t.classList || !t.classList.contains("team-active-cb")) return;
    const uid = t.getAttribute("data-user-id");
    const want = t.checked;
    if (!uid) return;
    if (!want && uid === getCurrentUserId()) {
      t.checked = true;
      toast("You cannot disable your own account.", "error");
      return;
    }
    try {
      await apiFetch("/api/v1/users/" + encodeURIComponent(uid), {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ is_active: want }),
      });
      toast(want ? "User enabled" : "User disabled", "success");
      await refreshTeamUsersTable();
      loadTenantSubscription().catch(() => {});
    } catch (e) {
      t.checked = !want;
      toast(e.message || "Update failed", "error");
    }
  });

  document.getElementById("team-users-body")?.addEventListener("click", (ev) => {
    const t = ev.target;
    const rolesBtn = t.closest && t.closest(".btn-team-roles");
    if (rolesBtn) {
      const uid = rolesBtn.getAttribute("data-user-id");
      if (uid) openTeamRolesDialog(uid);
      return;
    }
  });

  document.getElementById("team-roles-dialog-save")?.addEventListener("click", async () => {
    const hid = document.getElementById("team-roles-target-user-id");
    const uid = hid && hid.value;
    if (!uid) return;
    const roles = Array.from(document.querySelectorAll(".team-role-edit-cb:checked")).map(
      (cb) => cb.value
    );
    if (!roles.length) {
      toast("Select at least one role", "error");
      return;
    }
    try {
      await apiFetch("/api/v1/users/" + encodeURIComponent(uid) + "/roles", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ roles }),
      });
      toast("Roles updated", "success");
      closeTeamRolesDialog();
      await refreshTeamUsersTable();
    } catch (e) {
      toast(e.message || "Save failed", "error");
    }
  });

  document.getElementById("team-roles-dialog-cancel")?.addEventListener("click", closeTeamRolesDialog);
  document.getElementById("team-roles-dialog-close")?.addEventListener("click", closeTeamRolesDialog);
  document.getElementById("team-roles-dialog")?.addEventListener("click", (ev) => {
    if (ev.target.id === "team-roles-dialog") closeTeamRolesDialog();
  });

  function renderEmbedSnippetTemplate(secretPlaceholder) {
    const pre = document.getElementById("embed-snippet-template");
    if (!pre) return;
    const o = getAppOrigin();
    const key = secretPlaceholder || "YOUR_EMBED_API_KEY";
    pre.textContent =
      '<script defer src="' +
      o +
      '/static/embed/nexura-chat.js"\n  data-api-key="' +
      key +
      '"\n  data-base-url="' +
      o +
      '"><\\/script>';
  }

  let embedKeysSnapshot = [];

  function parseOriginsInput(raw) {
    const s = (raw || "").trim();
    if (!s) return [];
    return s
      .split(/[\n,]+/)
      .map((x) => x.trim().replace(/\/+$/, ""))
      .filter(Boolean);
  }

  async function populateEmbedAgentSelect() {
    const sel = document.getElementById("embed-key-agent");
    if (!sel) return;
    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = "— Marketplace default (Document Q&A) —";
    sel.innerHTML = "";
    sel.appendChild(placeholder);
    try {
      await loadTenantSubscription();
      const res = await fetch("/api/marketplace/agents");
      const data = await res.json();
      const agents = (data.agents || []).filter(
        (a) => a.installed && agentAllowedByPlan(a.agent_id)
      );
      agents.forEach((a) => {
        const o = document.createElement("option");
        o.value = a.agent_id;
        o.textContent = a.name || a.agent_id;
        sel.appendChild(o);
      });
    } catch {
      /* ignore */
    }
  }

  async function populateEmbedCollectionMultiselect() {
    const sel = document.getElementById("embed-key-collections");
    if (!sel) return;
    sel.innerHTML = "";
    try {
      const data = await apiFetch("/api/collections");
      const items = data.collections || [];
      items.forEach((item) => {
        const id = item.id || "";
        const label = (item.name || item.slug || id) + " (" + (item.slug || "") + ")";
        const o = document.createElement("option");
        o.value = id;
        o.textContent = label;
        sel.appendChild(o);
      });
    } catch {
      sel.innerHTML =
        '<option disabled>No collections — check permissions</option>';
    }
  }

  async function refreshEmbedKeysList() {
    const tbody = document.getElementById("embed-keys-body");
    if (!tbody) return;
    tbody.innerHTML =
      '<tr><td colspan="5" class="muted center">Loading…</td></tr>';
    try {
      const data = await apiFetch("/api/v1/embed-keys");
      const keys = data.keys || [];
      embedKeysSnapshot = keys;
      if (!keys.length) {
        tbody.innerHTML =
          '<tr><td colspan="5" class="muted center">No embed keys yet.</td></tr>';
        return;
      }
      tbody.innerHTML = keys
        .map((k) => {
          const active = k.is_active ? "Active" : "Revoked";
          const badge = k.is_active ? "badge-accent" : "badge-soon";
          const sites = Array.isArray(k.allowed_embed_origins)
            ? k.allowed_embed_origins
            : [];
          const sitesLabel =
            sites.length === 0
              ? '<span class="muted">Platform default</span>'
              : escapeHtml(sites.slice(0, 2).join(", ")) +
                (sites.length > 2 ? " …" : "");
          const btnSites =
            '<button type="button" class="btn btn-secondary btn-sm btn-edit-embed-origins" data-id="' +
            escapeAttr(k.id) +
            '">Sites</button>';
          const btnRevoke =
            '<button type="button" class="btn btn-ghost btn-sm btn-revoke-embed" data-id="' +
            escapeAttr(k.id) +
            '">Revoke</button>';
          const actions =
            k.is_active
              ? '<div class="row-actions">' + btnSites + " " + btnRevoke + "</div>"
              : "—";
          return (
            "<tr><td>" +
            escapeHtml(k.name || "") +
            "</td><td><code>" +
            escapeHtml(k.key_prefix || "") +
            "</code></td><td style=\"max-width:14rem;word-break:break-word;font-size:0.82rem\">" +
            sitesLabel +
            '</td><td><span class="badge ' +
            badge +
            '">' +
            escapeHtml(active) +
            '</span></td><td class="col-actions">' +
            actions +
            "</td></tr>"
          );
        })
        .join("");
    } catch (e) {
      tbody.innerHTML =
        '<tr><td colspan="5" class="muted center">' +
        escapeHtml(e.message || "Failed to load keys") +
        "</td></tr>";
    }
  }

  async function refreshEmbedPanel() {
    renderEmbedSnippetTemplate();
    await populateEmbedAgentSelect();
    await populateEmbedCollectionMultiselect();
    await refreshEmbedKeysList();
  }

  document.getElementById("btn-copy-embed-snippet")?.addEventListener("click", async () => {
    const pre = document.getElementById("embed-snippet-template");
    if (!pre || !pre.textContent) return;
    try {
      await navigator.clipboard.writeText(pre.textContent);
      toast("Snippet copied", "success");
    } catch {
      toast("Could not copy — select and copy manually", "error");
    }
  });

  document.getElementById("btn-refresh-embed-keys")?.addEventListener("click", () => {
    refreshEmbedKeysList().catch((e) =>
      toast(e.message || "Refresh failed", "error")
    );
  });

  document.getElementById("embed-keys-body")?.addEventListener("click", async (ev) => {
    const editBtn = ev.target.closest && ev.target.closest(".btn-edit-embed-origins");
    if (editBtn) {
      const id = editBtn.getAttribute("data-id");
      const k = embedKeysSnapshot.find((x) => x.id === id);
      const dlg = document.getElementById("embed-origins-dialog");
      const hid = document.getElementById("embed-origins-key-id");
      const ta = document.getElementById("embed-origins-textarea");
      const title = document.getElementById("embed-origins-dialog-title");
      if (!dlg || !hid || !ta || !k) return;
      hid.value = id;
      if (title) title.textContent = "Sites · " + (k.name || k.key_prefix || "");
      ta.value = Array.isArray(k.allowed_embed_origins)
        ? k.allowed_embed_origins.join("\n")
        : "";
      dlg.showModal();
      ta.focus();
      return;
    }

    const revokeBtn = ev.target.closest && ev.target.closest(".btn-revoke-embed");
    if (!revokeBtn) return;
    const id = revokeBtn.getAttribute("data-id");
    if (!id || !confirm("Revoke this embed key? Sites using it will stop working."))
      return;
    try {
      await apiFetch("/api/v1/embed-keys/" + encodeURIComponent(id), {
        method: "DELETE",
      });
      toast("Key revoked", "success");
      await refreshEmbedKeysList();
    } catch (e) {
      toast(e.message || "Revoke failed", "error");
    }
  });

  document.getElementById("embed-key-form")?.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const nameEl = document.getElementById("embed-key-name");
    const agentEl = document.getElementById("embed-key-agent");
    const collEl = document.getElementById("embed-key-collections");
    const note = document.getElementById("embed-key-created");
    const originsTa = document.getElementById("embed-key-origins");
    const name = (nameEl && nameEl.value.trim()) || "";
    if (!name) return;

    const ids = collEl
      ? Array.from(collEl.selectedOptions)
          .map((o) => o.value)
          .filter(Boolean)
      : [];

    const body = { name };
    if (agentEl && agentEl.value.trim())
      body.default_agent_id = agentEl.value.trim();
    if (ids.length) body.allowed_collection_ids = ids;
    const olist = originsTa ? parseOriginsInput(originsTa.value) : [];
    if (olist.length) body.allowed_embed_origins = olist;

    try {
      const data = await apiFetch("/api/v1/embed-keys", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (data.api_key) {
        renderEmbedSnippetTemplate(data.api_key);
        if (note) {
          note.style.display = "block";
          note.textContent =
            "Secret shown once — copy the snippet below or store the key securely.";
        }
        toast("Embed key created", "success");
        if (nameEl) nameEl.value = "";
        if (originsTa) originsTa.value = "";
        await refreshEmbedKeysList();
      }
    } catch (e) {
      toast(e.message || "Create failed", "error");
    }
  });

  function closeEmbedOriginsDialog() {
    document.getElementById("embed-origins-dialog")?.close();
  }

  document.getElementById("embed-origins-dialog-save")?.addEventListener("click", async () => {
    const hid = document.getElementById("embed-origins-key-id");
    const ta = document.getElementById("embed-origins-textarea");
    const id = hid && hid.value;
    if (!id || !ta) return;
    const list = parseOriginsInput(ta.value);
    try {
      await apiFetch("/api/v1/embed-keys/" + encodeURIComponent(id), {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ allowed_embed_origins: list }),
      });
      toast("Sites updated", "success");
      closeEmbedOriginsDialog();
      await refreshEmbedKeysList();
    } catch (e) {
      toast(e.message || "Save failed", "error");
    }
  });

  document.getElementById("embed-origins-dialog-cancel")?.addEventListener(
    "click",
    closeEmbedOriginsDialog
  );
  document.getElementById("embed-origins-dialog-close")?.addEventListener(
    "click",
    closeEmbedOriginsDialog
  );
  document.getElementById("embed-origins-dialog")?.addEventListener("click", (ev) => {
    if (ev.target.id === "embed-origins-dialog") closeEmbedOriginsDialog();
  });

  /* Library */
  const collectionSelect = document.getElementById("collection-select");
  const documentsBody = document.getElementById("documents-body");

  async function loadCollections(preserveSelection) {
    const prev = preserveSelection ? collectionSelect?.value : "";
    const data = await apiFetch("/api/collections");
    const items = data.collections || [];
    if (!collectionSelect) return;

    const optionsHtml =
      '<option value="">— All collections (tenant-wide) —</option>' +
      items
        .map((item) => {
          const slug = typeof item === "string" ? item : item.slug || "";
          const label =
            typeof item === "string"
              ? item
              : `${item.name || slug} (${slug})`;
          return `<option value="${escapeAttr(slug)}">${escapeHtml(label)}</option>`;
        })
        .join("");
    collectionSelect.innerHTML = optionsHtml;

    const slugs = items.map((item) =>
      typeof item === "string" ? item : item.slug
    );
    if (prev && slugs.includes(prev)) collectionSelect.value = prev;
    else collectionSelect.value = "";
    await loadDocumentsForSelection();
  }

  async function loadDocumentsForSelection() {
    if (!documentsBody || !collectionSelect) return;
    const name = collectionSelect.value.trim();
    if (!name) {
      documentsBody.innerHTML =
        '<tr><td colspan="3" class="muted center">Choose a collection to list documents (tenant-wide chat works without selecting).</td></tr>';
      return;
    }
    try {
      const data = await apiFetch(
        "/api/documents?" +
          new URLSearchParams({ collection_name: name }).toString()
      );
      const docs = data.documents || [];
      if (!docs.length) {
        documentsBody.innerHTML =
          '<tr><td colspan="3" class="muted center">No documents in this collection.</td></tr>';
        return;
      }
      documentsBody.innerHTML = docs
        .map((d) => {
          const fn = d.file_name || "";
          const mod = d.module || "";
          return `<tr data-file="${escapeAttr(fn)}">
            <td>${escapeHtml(fn)}</td>
            <td>${escapeHtml(mod)}</td>
            <td class="col-actions"><div class="row-actions">
              <button type="button" class="btn btn-secondary btn-sm btn-preview" data-file="${escapeAttr(fn)}">Chunks</button>
              <button type="button" class="btn btn-ghost btn-sm btn-delete" data-file="${escapeAttr(fn)}">Delete</button>
            </div></td>
          </tr>`;
        })
        .join("");
    } catch (e) {
      documentsBody.innerHTML =
        '<tr><td colspan="3" class="muted center">' +
        escapeHtml(e.message || String(e)) +
        "</td></tr>";
      toast(e.message || "Failed to load documents", "error");
    }
  }

  collectionSelect?.addEventListener("change", loadDocumentsForSelection);

  document.getElementById("btn-refresh-library")?.addEventListener("click", async () => {
    try {
      await loadCollections(true);
      toast("Library refreshed", "success");
    } catch (e) {
      toast(e.message || "Refresh failed", "error");
    }
  });

  /* Upload */
  document.getElementById("upload-form")?.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const form = ev.target;
    const fd = new FormData(form);
    try {
      const res = await fetch("/upload-document", {
        method: "POST",
        credentials: "same-origin",
        body: fd,
      });
      if (res.status === 401) {
        window.location.href = "/login";
        return;
      }
      const data = await parseJsonResponse(res);
      if (!res.ok) throw new Error(data.error || res.statusText);
      toast(data.message || "Upload complete", "success");
      form.reset();
      const mod = form.querySelector("[name=module]");
      if (mod) mod.value = "DEFAULT";
      await loadCollections(true);
    } catch (e) {
      toast(e.message || "Upload failed", "error");
    }
  });

  /* Delete & chunks delegation */
  const chunksDialog = document.getElementById("chunks-dialog");
  const chunksBody = document.getElementById("chunks-dialog-body");
  const chunksTitle = document.getElementById("chunks-dialog-title");
  const chunksMeta = document.getElementById("chunks-dialog-meta");

  document.getElementById("chunks-dialog-close")?.addEventListener("click", () => {
    chunksDialog?.close();
  });

  chunksDialog?.addEventListener("click", (ev) => {
    if (ev.target === chunksDialog) chunksDialog.close();
  });

  documentsBody?.addEventListener("click", async (ev) => {
    const t = ev.target;
    if (!(t instanceof HTMLElement)) return;
    const collection = collectionSelect?.value.trim();
    if (!collection) return;

    const delBtn = t.closest(".btn-delete");
    if (delBtn) {
      const file = delBtn.getAttribute("data-file");
      if (!file || !confirm("Delete all chunks for \"" + file + "\" from this collection?")) return;
      try {
        await apiFetch("/delete-document", {
          method: "DELETE",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            collection_name: collection,
            file_name: file,
          }),
        });
        toast("Document removed", "success");
        await loadDocumentsForSelection();
      } catch (e) {
        toast(e.message || "Delete failed", "error");
      }
      return;
    }

    const prevBtn = t.closest(".btn-preview");
    if (prevBtn) {
      const file = prevBtn.getAttribute("data-file");
      if (!file) return;
      try {
        const data = await apiFetch(
          "/api/chunks?" +
            new URLSearchParams({
              collection_name: collection,
              file_name: file,
            }).toString()
        );
        const chunks = data.chunks || [];
        if (chunksTitle) chunksTitle.textContent = "Chunk preview";
        if (chunksMeta)
          chunksMeta.textContent =
            collection + " · " + file + " · " + chunks.length + " chunk(s) shown";
        if (chunksBody) {
          chunksBody.innerHTML = chunks.length
            ? chunks
                .map((c, i) => {
                  const meta =
                    c.metadata && typeof c.metadata === "object"
                      ? JSON.stringify(c.metadata)
                      : "";
                  return (
                    '<div class="chunk-card"><div class="chunk-meta">#' +
                    (i + 1) +
                    (meta ? " · " + escapeHtml(meta) : "") +
                    "</div>" +
                    escapeHtml(c.text || "") +
                    "</div>"
                  );
                })
                .join("")
            : '<p class="muted">No chunks returned.</p>';
        }
        chunksDialog?.showModal();
        document.getElementById("chunks-dialog-close")?.focus();
      } catch (e) {
        toast(e.message || "Could not load chunks", "error");
      }
    }
  });

  refreshMarketplace().catch((e) =>
    toast(e.message || "Marketplace bootstrap failed", "error")
  );
  loadCollections(false).catch((e) =>
    toast(e.message || "Library load failed", "error")
  );

  const tabParam = new URLSearchParams(window.location.search).get("tab");
  if (tabParam && panelCopy[tabParam]) {
    const tabBtn = document.querySelector('.nav-item[data-tab="' + tabParam + '"]');
    if (tabBtn) tabBtn.click();
    try {
      const u = new URL(window.location.href);
      u.searchParams.delete("tab");
      const qs = u.searchParams.toString();
      window.history.replaceState({}, "", u.pathname + (qs ? "?" + qs : "") + u.hash);
    } catch (_) {
      /* ignore */
    }
  }
})();
