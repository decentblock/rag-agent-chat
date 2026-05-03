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
    "chat-audit": {
      title: "Chat audit",
      desc: "Console and embed transcripts with KB sources (not shown in chat UI).",
    },
    library: {
      title: "Knowledge base",
      desc: "Upload files, browse collections, preview chunks, delete documents.",
    },
    embed: {
      title: "Embed",
      desc: "Snippet, branding, embed keys, CORS.",
    },
    "visitor-leads": {
      title: "Visitor leads",
      desc: "Embed contact form submissions · export CSV.",
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
    if (label) label.textContent = displayNameForAgentId(aid);
    if (badge) {
      if (row && row.badge) {
        badge.hidden = false;
        badge.textContent = row.badge;
      } else {
        badge.hidden = true;
      }
    }
  }

  function displayNameForAgentId(agentId) {
    const row = marketplaceAgents.find((a) => a.agent_id === agentId);
    const catalog = row ? row.name : agentId;
    const names = agentPreference.config && agentPreference.config.agent_display_names;
    if (names && typeof names === "object" && !Array.isArray(names)) {
      const o = names[agentId];
      if (o != null && String(o).trim()) return String(o).trim().slice(0, 120);
    }
    return catalog;
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
          <h4>${escapeHtml(displayNameForAgentId(a.agent_id))}</h4>
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

    const dnInput = document.getElementById("agent-display-name");
    if (dnInput) {
      const names = agentPreference.config && agentPreference.config.agent_display_names;
      const saved =
        names &&
        typeof names === "object" &&
        !Array.isArray(names) &&
        names[agent.agent_id] != null
          ? String(names[agent.agent_id])
          : "";
      dnInput.value = saved.trim();
      dnInput.placeholder = agent.name || "Catalog name";
    }

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
    const prevNamesRaw =
      agentPreference.config && agentPreference.config.agent_display_names;
    const prevNames =
      prevNamesRaw &&
      typeof prevNamesRaw === "object" &&
      !Array.isArray(prevNamesRaw)
        ? Object.assign({}, prevNamesRaw)
        : {};
    const dnRaw = (
      document.getElementById("agent-display-name")?.value || ""
    ).trim();
    const catalogName = (modalEditingAgent.name || "").trim();
    if (dnRaw && dnRaw !== catalogName) {
      prevNames[modalEditingAgent.agent_id] = dnRaw.slice(0, 120);
    } else {
      delete prevNames[modalEditingAgent.agent_id];
    }
    if (Object.keys(prevNames).length) cfg.agent_display_names = prevNames;
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
      if (tab === "chat-audit") {
        chatAuditOffset = 0;
        populateChatAuditKeyFilter()
          .then(() => refreshChatAuditPanel())
          .catch((err) =>
            toast(err.message || "Chat audit failed", "error")
          );
      }
      if (tab === "visitor-leads") {
        visitorLeadsOffset = 0;
        refreshVisitorLeadsPanel().catch((err) =>
          toast(err.message || "Visitor leads failed", "error")
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

  function removeChatTypingIndicator() {
    document.getElementById("chat-typing-indicator")?.remove();
  }

  function appendChatTypingIndicator() {
    if (!transcript) return;
    removeChatTypingIndicator();
    const div = document.createElement("div");
    div.id = "chat-typing-indicator";
    div.className = "chat-bubble assistant typing";
    div.setAttribute("role", "status");
    div.setAttribute("aria-live", "polite");
    div.setAttribute("aria-label", "Assistant is typing");
    div.innerHTML =
      '<span class="typing-dots" aria-hidden="true"><span>.</span><span>.</span><span>.</span></span>';
    transcript.appendChild(div);
    transcript.scrollTop = transcript.scrollHeight;
  }

  chatForm?.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const msg = (chatInput?.value || "").trim();
    if (!msg) return;

    appendBubble("user", escapeHtml(msg));
    chatInput.value = "";

    const coll =
      document.getElementById("collection-select")?.value?.trim() || "";

    const btnSend = document.getElementById("btn-send-chat");
    appendChatTypingIndicator();
    if (btnSend) btnSend.disabled = true;
    if (chatInput) chatInput.disabled = true;

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

      appendBubble("assistant", escapeHtml(answerText));
    } catch (e) {
      toast(e.message || "Chat failed", "error");
      appendBubble(
        "assistant",
        '<span class="muted">Error: ' + escapeHtml(String(e.message || e)) + "</span>"
      );
    } finally {
      removeChatTypingIndicator();
      if (btnSend) btnSend.disabled = false;
      if (chatInput) chatInput.disabled = false;
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
      '"\n  data-collection-ids="general"></script>\n\n' +
      "<!-- Opens enlarged automatically; transcript survives reload until the tab closes. Use data-auto-open=\"false\" for bubble-only. -->\n" +
      "<!-- Change general to your KB slug(s), comma-separated, or remove data-collection-ids when the embed key already restricts collections (omit for all collections when key is unrestricted). -->";
  }

  async function loadEmbedBrandingForm() {
    const nameEl = document.getElementById("embed-brand-agent-name");
    const welcomeEl = document.getElementById("embed-brand-welcome");
    const cb = document.getElementById("embed-brand-collect-contact");
    const nEl = document.getElementById("embed-brand-engagement-count");
    if (!nameEl || !welcomeEl) return;
    try {
      const d = await apiFetch("/api/v1/tenant/embed-branding");
      nameEl.value = d.embed_agent_display_name || "";
      welcomeEl.value = d.embed_welcome_message || "";
      if (cb) cb.checked = d.embed_collect_visitor_contact !== false;
      if (nEl) nEl.textContent = String(d.embed_engagement_count ?? 0);
    } catch {
      if (nEl) nEl.textContent = "—";
    }
  }

  document.getElementById("embed-branding-save")?.addEventListener("click", async () => {
    const nameEl = document.getElementById("embed-brand-agent-name");
    const welcomeEl = document.getElementById("embed-brand-welcome");
    const cb = document.getElementById("embed-brand-collect-contact");
    try {
      await apiFetch("/api/v1/tenant/embed-branding", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          embed_agent_display_name: (nameEl && nameEl.value) || "",
          embed_welcome_message: (welcomeEl && welcomeEl.value) || "",
          embed_collect_visitor_contact: !!(cb && cb.checked),
        }),
      });
      toast("Widget settings saved", "success");
      await loadEmbedBrandingForm();
    } catch (e) {
      toast(e.message || "Save failed", "error");
    }
  });

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
        const slug = item.slug || "";
        const label =
          (item.name || slug || id) + (slug ? " · slug: " + slug : "");
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
      '<tr><td colspan="6" class="muted center">Loading…</td></tr>';
    try {
      const data = await apiFetch("/api/v1/embed-keys");
      const keys = data.keys || [];
      embedKeysSnapshot = keys;
      if (!keys.length) {
        tbody.innerHTML =
          '<tr><td colspan="6" class="muted center">No embed keys yet.</td></tr>';
        return;
      }
      tbody.innerHTML = keys
        .map((k) => {
          const active = k.is_active ? "Active" : "Revoked";
          const badge = k.is_active ? "badge-accent" : "badge-soon";
          const sites = Array.isArray(k.allowed_embed_origins)
            ? k.allowed_embed_origins
            : [];
          let kbCell =
            '<span class="muted">All collections</span>';
          if (Array.isArray(k.allowed_collection_slugs) && k.allowed_collection_slugs.length) {
            kbCell = escapeHtml(k.allowed_collection_slugs.join(", "));
          } else if (
            Array.isArray(k.allowed_collection_ids) &&
            k.allowed_collection_ids.length
          ) {
            kbCell = escapeHtml(k.allowed_collection_ids.join(", "));
          }
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
            "</code></td><td style=\"max-width:12rem;word-break:break-word;font-size:0.82rem\">" +
            kbCell +
            '</td><td style="max-width:12rem;word-break:break-word;font-size:0.82rem">' +
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
        '<tr><td colspan="6" class="muted center">' +
        escapeHtml(e.message || "Failed to load keys") +
        "</td></tr>";
    }
  }

  const CHAT_AUDIT_PAGE = 50;
  let chatAuditOffset = 0;

  function getBootstrapBool(key) {
    const el = document.getElementById("nexura-console-bootstrap");
    return !!(el && el.dataset[key] === "true");
  }

  async function populateChatAuditKeyFilter() {
    const sel = document.getElementById("chat-audit-key-filter");
    if (!sel) return;
    const prev = sel.value || "all";
    sel.innerHTML = "";
    sel.add(new Option("All queries", "all"));
    sel.add(new Option("Console only", "console"));
    if (getBootstrapBool("canManageEmbed")) {
      try {
        const data = await apiFetch("/api/v1/embed-keys");
        const keys = data.keys || [];
        keys.forEach((k) => {
          const label = (k.name || k.key_prefix || k.id).slice(0, 80);
          sel.add(new Option("Embed · " + label, k.id));
        });
      } catch {
        /* Embed keys list unavailable — filter stays All / Console */
      }
    }
    const allowed = Array.from(sel.options).some((o) => o.value === prev);
    sel.value = allowed ? prev : "all";
  }

  function chatAuditColspan() {
    return getBootstrapBool("canDeleteChatAudit") ? 7 : 6;
  }

  function truncateAuditText(s, maxLen) {
    const t = (s || "").trim();
    if (t.length <= maxLen) return t;
    return t.slice(0, maxLen - 1) + "…";
  }

  async function refreshChatAuditPanel(retryOnOverrun) {
    const tbody = document.getElementById("chat-audit-body");
    const meta = document.getElementById("chat-audit-meta");
    const prev = document.getElementById("chat-audit-prev");
    const next = document.getElementById("chat-audit-next");
    const fkEl = document.getElementById("chat-audit-key-filter");
    if (!tbody) return;
    const colspan = chatAuditColspan();
    tbody.innerHTML =
      '<tr><td colspan="' +
      colspan +
      '" class="muted center">Loading…</td></tr>';
    const fk = fkEl ? fkEl.value || "" : "";
    try {
      const qs = new URLSearchParams({
        limit: String(CHAT_AUDIT_PAGE),
        offset: String(chatAuditOffset),
      });
      if (fk && fk !== "all") qs.set("embed_key", fk);
      const data = await apiFetch(
        "/api/v1/tenant/chat-query-audit?" + qs.toString()
      );
      let total = data.total ?? 0;
      let items = data.items || [];
      if (retryOnOverrun !== false && total > 0 && chatAuditOffset >= total) {
        chatAuditOffset =
          Math.max(
            0,
            Math.floor((total - 1) / CHAT_AUDIT_PAGE) * CHAT_AUDIT_PAGE
          );
        return refreshChatAuditPanel(false);
      }
      const start = total === 0 ? 0 : chatAuditOffset + 1;
      const end = chatAuditOffset + items.length;
      if (meta) {
        meta.textContent = total
          ? "Showing " + start + "–" + end + " of " + total
          : "No logged queries yet.";
      }
      if (prev) prev.disabled = chatAuditOffset <= 0;
      if (next) next.disabled = chatAuditOffset + items.length >= total;

      const canDel = getBootstrapBool("canDeleteChatAudit");

      if (!items.length) {
        tbody.innerHTML =
          '<tr><td colspan="' +
          colspan +
          '" class="muted center">' +
          (total ? "No rows on this page." : "No logged queries yet.") +
          "</td></tr>";
        return;
      }

      tbody.innerHTML = items
        .map((row) => {
          let srcLabel =
            row.channel === "embed"
              ? "Embed · " + (row.embed_key_name || row.embed_key_id || "key")
              : "Console · " + (row.actor_username || "—");
          if (row.channel === "embed" && row.visitor_session) {
            srcLabel +=
              " · sess " + truncateAuditText(row.visitor_session, 24);
          }
          const qShort = truncateAuditText(row.query_text, 160);
          let ansShow = "";
          if (row.error_message) {
            ansShow = "Error: " + row.error_message;
          } else {
            ansShow = row.answer_text || "";
          }
          const ansShort = truncateAuditText(ansShow, 220);
          const sources = Array.isArray(row.sources) ? row.sources : [];
          const srcDetail =
            sources.length === 0
              ? '<span class="muted">—</span>'
              : "<details><summary>" +
                escapeHtml(String(sources.length)) +
                ' source(s)</summary><ul style="margin:0.35rem 0 0 1rem;padding:0;font-size:0.82rem;max-width:18rem;">' +
                sources
                  .map(
                    (s) =>
                      '<li style="word-break:break-word;">' +
                      escapeHtml(String(s)) +
                      "</li>"
                  )
                  .join("") +
                "</ul></details>";
          const delCell = canDel
            ? '<td class="col-actions"><button type="button" class="btn btn-ghost btn-sm btn-delete-chat-audit" data-id="' +
              escapeAttr(row.id) +
              '">Delete</button></td>'
            : "";
          return (
            "<tr>" +
            '<td style="font-size:0.82rem;white-space:nowrap">' +
            escapeHtml(row.created_at || "—") +
            "</td>" +
            '<td style="font-size:0.82rem">' +
            escapeHtml(srcLabel) +
            "</td>" +
            "<td>" +
            escapeHtml(row.agent_id || "") +
            "</td>" +
            '<td style="max-width:14rem;font-size:0.82rem" title="' +
            escapeAttr(row.query_text || "") +
            '">' +
            escapeHtml(qShort) +
            "</td>" +
            '<td style="max-width:16rem;font-size:0.82rem" title="' +
            escapeAttr(ansShow) +
            '">' +
            escapeHtml(ansShort) +
            "</td>" +
            "<td>" +
            srcDetail +
            "</td>" +
            delCell +
            "</tr>"
          );
        })
        .join("");
    } catch (e) {
      tbody.innerHTML =
        '<tr><td colspan="' +
        colspan +
        '" class="muted center">' +
        escapeHtml(e.message || "Failed to load") +
        "</td></tr>";
      if (meta) meta.textContent = "—";
      if (prev) prev.disabled = true;
      if (next) next.disabled = true;
    }
  }

  document.getElementById("chat-audit-body")?.addEventListener("click", async (ev) => {
    const btn = ev.target.closest && ev.target.closest(".btn-delete-chat-audit");
    if (!btn) return;
    const id = btn.getAttribute("data-id");
    if (!id || !confirm("Permanently delete this audit row? This cannot be undone."))
      return;
    try {
      await apiFetch("/api/v1/tenant/chat-query-audit/" + encodeURIComponent(id), {
        method: "DELETE",
      });
      toast("Deleted", "success");
      await refreshChatAuditPanel();
    } catch (e) {
      toast(e.message || "Delete failed", "error");
    }
  });

  document.getElementById("btn-refresh-chat-audit")?.addEventListener("click", () => {
    chatAuditOffset = 0;
    populateChatAuditKeyFilter()
      .then(() => refreshChatAuditPanel())
      .catch((e) => toast(e.message || "Refresh failed", "error"));
  });

  document.getElementById("chat-audit-key-filter")?.addEventListener("change", () => {
    chatAuditOffset = 0;
    refreshChatAuditPanel().catch((e) =>
      toast(e.message || "Load failed", "error")
    );
  });

  document.getElementById("chat-audit-prev")?.addEventListener("click", () => {
    chatAuditOffset = Math.max(0, chatAuditOffset - CHAT_AUDIT_PAGE);
    refreshChatAuditPanel().catch((e) =>
      toast(e.message || "Load failed", "error")
    );
  });

  document.getElementById("chat-audit-next")?.addEventListener("click", () => {
    chatAuditOffset += CHAT_AUDIT_PAGE;
    refreshChatAuditPanel().catch((e) =>
      toast(e.message || "Load failed", "error")
    );
  });

  const VISITOR_LEADS_PAGE = 50;
  let visitorLeadsOffset = 0;

  async function refreshVisitorLeadsPanel(retryOnOverrun) {
    const tbody = document.getElementById("visitor-leads-body");
    const meta = document.getElementById("visitor-leads-meta");
    const prev = document.getElementById("visitor-leads-prev");
    const next = document.getElementById("visitor-leads-next");
    if (!tbody) return;
    tbody.innerHTML =
      '<tr><td colspan="6" class="muted center">Loading…</td></tr>';
    try {
      const qs = new URLSearchParams({
        limit: String(VISITOR_LEADS_PAGE),
        offset: String(visitorLeadsOffset),
      });
      const data = await apiFetch(
        "/api/v1/tenant/embed-visitor-leads?" + qs.toString()
      );
      let total = data.total ?? 0;
      let leads = data.leads || [];
      if (retryOnOverrun !== false && total > 0 && visitorLeadsOffset >= total) {
        visitorLeadsOffset =
          Math.max(
            0,
            Math.floor((total - 1) / VISITOR_LEADS_PAGE) * VISITOR_LEADS_PAGE
          );
        return refreshVisitorLeadsPanel(false);
      }
      const start = total === 0 ? 0 : visitorLeadsOffset + 1;
      const end = visitorLeadsOffset + leads.length;
      if (meta) {
        meta.textContent = total
          ? "Showing " + start + "–" + end + " of " + total
          : "No submissions yet.";
      }
      if (prev) prev.disabled = visitorLeadsOffset <= 0;
      if (next)
        next.disabled = visitorLeadsOffset + leads.length >= total;

      if (!leads.length) {
        tbody.innerHTML =
          '<tr><td colspan="6" class="muted center">' +
          (total ? "No rows on this page." : "No submissions yet.") +
          "</td></tr>";
        return;
      }
      tbody.innerHTML = leads
        .map((row) => {
          const msg = row.initial_message || "";
          const msgShort =
            msg.length > 120 ? msg.slice(0, 117) + "…" : msg;
          const keyLabel =
            row.embed_key_name || row.embed_key_id || "—";
          return (
            "<tr>" +
            '<td><span style="font-size:0.82rem">' +
            escapeHtml(row.created_at || "—") +
            "</span></td>" +
            '<td title="' +
            escapeAttr(msg) +
            '"><span style="font-size:0.82rem">' +
            escapeHtml(msgShort) +
            "</span></td>" +
            "<td>" +
            escapeHtml(row.name || "") +
            "</td>" +
            "<td>" +
            escapeHtml(row.email || "") +
            "</td>" +
            "<td>" +
            escapeHtml(row.phone || "") +
            "</td>" +
            '<td><span style="font-size:0.82rem">' +
            escapeHtml(keyLabel) +
            "</span></td>" +
            "</tr>"
          );
        })
        .join("");
    } catch (e) {
      tbody.innerHTML =
        '<tr><td colspan="6" class="muted center">' +
        escapeHtml(e.message || "Failed to load") +
        "</td></tr>";
      if (meta) meta.textContent = "—";
      if (prev) prev.disabled = true;
      if (next) next.disabled = true;
    }
  }

  async function exportVisitorLeadsCsv() {
    const res = await fetch("/api/v1/tenant/embed-visitor-leads/export", {
      credentials: "same-origin",
    });
    if (res.status === 401) {
      window.location.href =
        "/login?next=" + encodeURIComponent(window.location.pathname);
      return;
    }
    if (!res.ok) {
      const data = await parseJsonResponse(res);
      toast(data.error || data.message || "Export failed", "error");
      return;
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "embed-visitor-leads.csv";
    a.rel = "noopener";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    toast("Download started", "success");
  }

  async function refreshEmbedPanel() {
    renderEmbedSnippetTemplate();
    await loadEmbedBrandingForm();
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

  document.getElementById("btn-refresh-visitor-leads")?.addEventListener("click", () => {
    visitorLeadsOffset = 0;
    refreshVisitorLeadsPanel().catch((e) =>
      toast(e.message || "Refresh failed", "error")
    );
  });

  document.getElementById("btn-export-visitor-leads")?.addEventListener("click", () => {
    exportVisitorLeadsCsv().catch((e) =>
      toast(e.message || "Export failed", "error")
    );
  });

  document.getElementById("visitor-leads-prev")?.addEventListener("click", () => {
    visitorLeadsOffset = Math.max(0, visitorLeadsOffset - VISITOR_LEADS_PAGE);
    refreshVisitorLeadsPanel().catch((e) =>
      toast(e.message || "Load failed", "error")
    );
  });

  document.getElementById("visitor-leads-next")?.addEventListener("click", () => {
    visitorLeadsOffset += VISITOR_LEADS_PAGE;
    refreshVisitorLeadsPanel().catch((e) =>
      toast(e.message || "Load failed", "error")
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
  const kbBootstrap = document.getElementById("nexura-console-bootstrap");
  const isSuperuserKb = !!(kbBootstrap && kbBootstrap.dataset.isSuperuser === "true");
  const defaultTenantIdKb = (kbBootstrap && kbBootstrap.dataset.currentTenantId) || "";

  function kbProbeTenantOptionalPayload() {
    if (!isSuperuserKb) return {};
    const el = document.getElementById("kb-probe-tenant-id");
    const raw = el ? String(el.value || "").trim() : "";
    if (raw && raw !== defaultTenantIdKb) return { tenant_id: raw };
    return {};
  }

  function kbIndexDebugUrlSuffix() {
    if (!isSuperuserKb) return "";
    const el = document.getElementById("kb-probe-tenant-id");
    const raw = el ? String(el.value || "").trim() : "";
    if (raw && raw !== defaultTenantIdKb)
      return "?tenant_id=" + encodeURIComponent(raw);
    return "";
  }

  async function loadKbAuditEvents() {
    const ul = document.getElementById("kb-audit-events");
    if (!ul) return;
    const qs = new URLSearchParams({ limit: "35" });
    if (isSuperuserKb) {
      const el = document.getElementById("kb-probe-tenant-id");
      const raw = el ? String(el.value || "").trim() : "";
      if (raw) qs.set("tenant_id", raw);
    }
    ul.innerHTML = '<li class="muted">Loading…</li>';
    try {
      const data = await apiFetch("/api/v1/kb/audit-events?" + qs.toString());
      const evs = data.events || [];
      if (!evs.length) {
        ul.innerHTML = '<li class="muted">No KB audit rows yet (uploads and probes appear here).</li>';
        return;
      }
      ul.innerHTML = evs
        .map((e) => {
          const t = e.created_at || "";
          const ty = escapeHtml(e.event_type || "");
          const msg = escapeHtml(e.message || "");
          return (
            "<li style=\"margin-bottom:0.35rem;\"><time>" +
            escapeHtml(t) +
            "</time> · <code>" +
            ty +
            "</code> — " +
            msg +
            "</li>"
          );
        })
        .join("");
    } catch (err) {
      ul.innerHTML =
        '<li class="muted">' + escapeHtml(err.message || "Audit load failed") + "</li>";
    }
  }

  function syncLibraryCollectionSlugHint() {
    const el = document.getElementById("library-collection-slug-hint");
    if (!el || !collectionSelect) return;
    const slug = collectionSelect.value.trim();
    if (!slug) {
      el.innerHTML =
        '<strong>Tenant-wide</strong> chat searches every KB collection when this dropdown is empty. Pick a collection to list documents here. Match external sites with embed <code>data-collection-ids</code> slugs when needed.';
      return;
    }
    el.innerHTML =
      'Listing slug <strong>' +
      escapeHtml(slug) +
      '</strong> · optional embed override: <code>data-collection-ids="' +
      escapeHtml(slug) +
      '"</code>';
  }

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
    syncLibraryCollectionSlugHint();
    await loadDocumentsForSelection();
  }

  async function loadDocumentsForSelection() {
    if (!documentsBody || !collectionSelect) return;
    syncLibraryCollectionSlugHint();
    const name = collectionSelect.value.trim();
    if (!name) {
      documentsBody.innerHTML =
        '<tr><td colspan="5" class="muted center">Choose a collection to list documents (tenant-wide chat works without selecting).</td></tr>';
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
          '<tr><td colspan="5" class="muted center">No documents in this collection.</td></tr>';
        return;
      }
      documentsBody.innerHTML = docs
        .map((d) => {
          const fn = d.file_name || "";
          const mod = d.module || "";
          const nchunks =
            d.indexed_chunk_count != null ? String(d.indexed_chunk_count) : "—";
          const docId = d.document_id || "";
          const cslug = d.collection_slug || name || "—";
          return `<tr data-file="${escapeAttr(fn)}">
            <td>${escapeHtml(fn)}</td>
            <td><code>${escapeHtml(cslug)}</code></td>
            <td><code>${escapeHtml(nchunks)}</code></td>
            <td>${escapeHtml(mod)}</td>
            <td class="col-actions"><div class="row-actions">
              <button type="button" class="btn btn-secondary btn-sm btn-preview" data-file="${escapeAttr(fn)}">Chunks</button>
              <button type="button" class="btn btn-secondary btn-sm btn-index-debug" data-doc-id="${escapeAttr(docId)}" data-file="${escapeAttr(fn)}">Index debug</button>
              <button type="button" class="btn btn-ghost btn-sm btn-delete" data-file="${escapeAttr(fn)}">Delete</button>
            </div></td>
          </tr>`;
        })
        .join("");
    } catch (e) {
      documentsBody.innerHTML =
        '<tr><td colspan="5" class="muted center">' +
        escapeHtml(e.message || String(e)) +
        "</td></tr>";
      toast(e.message || "Failed to load documents", "error");
    }
  }

  collectionSelect?.addEventListener("change", loadDocumentsForSelection);

  document.getElementById("btn-refresh-library")?.addEventListener("click", async () => {
    try {
      await loadCollections(true);
      await loadKbAuditEvents();
      toast("Library refreshed", "success");
    } catch (e) {
      toast(e.message || "Refresh failed", "error");
    }
  });

  const kbSuperField = document.getElementById("kb-super-tenant-field");
  if (kbSuperField) kbSuperField.hidden = !isSuperuserKb;

  document.getElementById("kb-probe-tenant-id")?.addEventListener("change", () => {
    loadKbAuditEvents().catch(() => {});
  });

  document.getElementById("btn-kb-audit-refresh")?.addEventListener("click", () => {
    loadKbAuditEvents().catch((e) =>
      toast(e.message || "Audit refresh failed", "error")
    );
  });

  document.getElementById("btn-kb-retrieval-probe")?.addEventListener("click", async () => {
    const ta = document.getElementById("kb-probe-query");
    const q = ta ? ta.value.trim() : "";
    if (!q) {
      toast("Enter a question for the probe", "error");
      return;
    }
    const scopeCb = document.getElementById("kb-probe-scope-collection");
    const scopeColl =
      scopeCb &&
      scopeCb.checked &&
      collectionSelect &&
      collectionSelect.value.trim();
    if (scopeCb && scopeCb.checked && !scopeColl) {
      toast("Pick a collection above or turn off “limit to selected collection”", "error");
      return;
    }
    const out = document.getElementById("kb-probe-result");
    if (out) out.textContent = "Running probe…";
    try {
      const body = {
        query: q,
        ...kbProbeTenantOptionalPayload(),
      };
      if (scopeColl) body.collection_slugs = [collectionSelect.value.trim()];
      const data = await apiFetch("/api/v1/kb/retrieval-probe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (out) out.textContent = JSON.stringify(data, null, 2);
      toast(
        data.hits && data.hits.length
          ? "Probe returned " + data.hits.length + " chunk(s)"
          : "Probe returned no chunks — see JSON hints",
        data.hits && data.hits.length ? "success" : "error"
      );
      await loadKbAuditEvents();
    } catch (e) {
      if (out) out.textContent = e.message || "Probe failed";
      toast(e.message || "Probe failed", "error");
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
      if (data.result && data.result.warning === "no_chunks_extracted") {
        toast(
          "Upload saved but no text chunks were extracted (often scanned PDF). Index debug will show 0 chunks.",
          "error"
        );
      }
      form.reset();
      const mod = form.querySelector("[name=module]");
      if (mod) mod.value = "DEFAULT";
      await loadCollections(true);
      await loadKbAuditEvents();
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

  const kbDbgDlg = document.getElementById("kb-index-debug-dialog");
  const kbDbgBody = document.getElementById("kb-index-debug-body");
  const kbDbgTitle = document.getElementById("kb-index-debug-title");
  const kbDbgSub = document.getElementById("kb-index-debug-sub");

  document.getElementById("kb-index-debug-close")?.addEventListener("click", () => {
    kbDbgDlg?.close();
  });

  kbDbgDlg?.addEventListener("click", (ev) => {
    if (ev.target === kbDbgDlg) kbDbgDlg.close();
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
        await loadKbAuditEvents();
      } catch (e) {
        toast(e.message || "Delete failed", "error");
      }
      return;
    }

    const dbgBtn = t.closest(".btn-index-debug");
    if (dbgBtn) {
      const docId = dbgBtn.getAttribute("data-doc-id");
      const file = dbgBtn.getAttribute("data-file") || "";
      if (!docId) return;
      try {
        const url =
          "/api/v1/kb/documents/" +
          encodeURIComponent(docId) +
          "/index-debug" +
          kbIndexDebugUrlSuffix();
        const raw = await apiFetch(url);
        if (kbDbgTitle) kbDbgTitle.textContent = "Index debug";
        if (kbDbgSub) kbDbgSub.textContent = collection + " · " + file;
        if (kbDbgBody) kbDbgBody.textContent = JSON.stringify(raw, null, 2);
        kbDbgDlg?.showModal();
        document.getElementById("kb-index-debug-close")?.focus();
      } catch (e) {
        toast(e.message || "Index debug failed", "error");
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
  loadCollections(false)
    .then(() => loadKbAuditEvents())
    .catch((e) => toast(e.message || "Library load failed", "error"));

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
