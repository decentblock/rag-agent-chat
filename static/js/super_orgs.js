(function () {
  const tbody = document.getElementById("orgs-tbody");
  const flash = document.getElementById("orgs-flash");
  const btnRefresh = document.getElementById("orgs-refresh");
  const detailEmpty = document.getElementById("orgs-detail-empty");
  const detailPanel = document.getElementById("orgs-detail-panel");
  const agentsBox = document.getElementById("orgs-agents-box");
  const customAgentsCb = document.getElementById("orgs-custom-agents");
  const usersTbody = document.getElementById("orgs-users-tbody");
  const planSel = document.getElementById("orgs-plan");

  let marketplaceAgents = [];
  /** @type {Record<string, { allowed_agent_ids: string[] | null }>} */
  let planOptionsMap = {};
  /** @type {string | null} */
  let selectedTenantId = null;

  function currentUserId() {
    const el = document.getElementById("nexura-console-bootstrap");
    return (el && el.dataset.currentUserId) || "";
  }

  function showFlash(kind, msg) {
    flash.textContent = msg || "";
    flash.className = "orgs-flash visible " + (kind === "ok" ? "ok" : "err");
  }

  function clearFlash() {
    flash.className = "orgs-flash";
    flash.textContent = "";
  }

  async function fetchJSON(url, opts) {
    const headers = { Accept: "application/json" };
    if (opts && opts.body != null) headers["Content-Type"] = "application/json";
    const r = await fetch(url, {
      credentials: "same-origin",
      headers,
      ...opts,
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.error || r.statusText || "Request failed");
    return data;
  }

  function agentSelectable(planAllowed, agentId) {
    if (planAllowed == null || planAllowed.length === 0) return true;
    const set = new Set(planAllowed.map((x) => String(x).toLowerCase()));
    return set.has(String(agentId).toLowerCase());
  }

  function currentPlanAllowedFromSelection() {
    const slug = planSel.value;
    const po = planOptionsMap[slug];
    return po ? po.allowed_agent_ids : null;
  }

  function collectEnabledSelections() {
    const ids = new Set();
    agentsBox.querySelectorAll('input[type="checkbox"]:not(:disabled)').forEach((cb) => {
      if (cb.checked) ids.add(cb.value);
    });
    return ids;
  }

  function fillPlanSelect(options, current) {
    planOptionsMap = {};
    planSel.innerHTML = "";
    for (const o of options || []) {
      planOptionsMap[o.slug] = { allowed_agent_ids: o.allowed_agent_ids ?? null };
      const opt = document.createElement("option");
      opt.value = o.slug;
      opt.textContent = o.label + " (" + o.slug + ")";
      if (o.slug === current) opt.selected = true;
      planSel.appendChild(opt);
    }
  }

  function selectedSetFromTenant(tenant, planAllowed) {
    const hasOverride = tenant.has_agent_override;
    const selected = new Set();
    if (hasOverride && Array.isArray(tenant.allowed_agent_ids_override)) {
      tenant.allowed_agent_ids_override.forEach((x) => selected.add(String(x).toLowerCase()));
    } else if (!hasOverride && planAllowed && planAllowed.length) {
      planAllowed.forEach((x) => selected.add(String(x).toLowerCase()));
    } else if (!hasOverride && (!planAllowed || planAllowed.length === 0)) {
      marketplaceAgents.forEach((a) => {
        const aid = String(a.agent_id).toLowerCase();
        if (a.installed && agentSelectable(planAllowed, aid)) selected.add(aid);
      });
    }
    return selected;
  }

  function renderAgentCheckboxes(planAllowed, selectedSet) {
    agentsBox.innerHTML = "";
    for (const a of marketplaceAgents) {
      const id = String(a.agent_id).toLowerCase();
      const installed = !!a.installed;
      const onPlan = agentSelectable(planAllowed, id);
      const locked = !installed || !onPlan;

      const row = document.createElement("div");
      row.className = "orgs-agent-row" + (locked ? " orgs-agent-locked" : "");

      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.value = id;
      cb.disabled = locked;
      cb.checked = locked ? false : selectedSet.has(id);

      row.appendChild(cb);
      row.appendChild(document.createTextNode(" " + (a.name || id)));

      let note = "";
      if (!installed) note = "Not installed.";
      else if (!onPlan) note = "Not on plan — upgrade tier first.";
      if (note) {
        const span = document.createElement("span");
        span.className = "orgs-agent-note";
        span.textContent = " · " + note;
        row.appendChild(span);
      }

      agentsBox.appendChild(row);
    }
  }

  function applyAgentsUI(detail) {
    const tenant = detail.tenant;
    const planAllowed =
      detail.plan_allowed_agent_ids ??
      planOptionsMap[tenant.plan_slug]?.allowed_agent_ids ??
      null;
    const selected = selectedSetFromTenant(tenant, planAllowed);
    customAgentsCb.checked = !!tenant.has_agent_override;
    agentsBox.hidden = !customAgentsCb.checked;
    renderAgentCheckboxes(planAllowed, selected);

    planSel.onchange = () => {
      if (!customAgentsCb.checked) return;
      renderAgentCheckboxes(currentPlanAllowedFromSelection(), collectEnabledSelections());
    };
    customAgentsCb.onchange = () => {
      agentsBox.hidden = !customAgentsCb.checked;
    };
  }

  function applyDetail(detail, usersListOptional) {
    const tenant = detail.tenant;
    document.getElementById("orgs-edit-id").value = tenant.id;
    document.getElementById("orgs-slug").value = tenant.slug;
    document.getElementById("orgs-name").value = tenant.name;
    fillPlanSelect(detail.plan_options, tenant.plan_slug);
    document.getElementById("orgs-active").checked = !!tenant.is_active;
    document.getElementById("orgs-billing-email").value = tenant.billing_contact_email || "";
    document.getElementById("orgs-payment-id").value = tenant.payment_provider_customer_id || "";
    document.getElementById("orgs-notes").value = tenant.notes || "";

    applyAgentsUI(detail);
    if (usersListOptional !== undefined) renderUsers(usersListOptional);
  }

  async function ensureMarketplace() {
    if (marketplaceAgents.length) return;
    const data = await fetchJSON("/api/marketplace/agents");
    marketplaceAgents = (data.agents || []).filter((a) => a.available !== false);
    marketplaceAgents.sort((a, b) =>
      String(a.name || a.agent_id).localeCompare(String(b.name || b.agent_id))
    );
  }

  function renderUsers(users) {
    usersTbody.innerHTML = "";
    const selfId = currentUserId();
    for (const u of users || []) {
      const tr = document.createElement("tr");
      const roles = (u.roles || []).join(", ");
      const email = u.email || "—";
      const disableToggle = u.id === selfId;
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.checked = !!u.is_active;
      cb.disabled = disableToggle;
      cb.title = disableToggle ? "Cannot disable your own account" : "Allow sign-in";
      cb.className = "orgs-user-active";
      cb.addEventListener("change", async () => {
        const want = cb.checked;
        try {
          await fetchJSON("/api/super/users/" + encodeURIComponent(u.id), {
            method: "PATCH",
            body: JSON.stringify({ is_active: want }),
          });
          showFlash("ok", "User updated.");
          setTimeout(clearFlash, 1800);
          loadListQuiet();
        } catch (e) {
          showFlash("err", e.message);
          cb.checked = !want;
        }
      });

      tr.innerHTML =
        "<td>" +
        escapeHtml(u.username) +
        (u.is_superuser ? ' <span class="muted">· super</span>' : "") +
        "</td>" +
        "<td>" +
        escapeHtml(email) +
        "</td>" +
        "<td>" +
        escapeHtml(roles) +
        "</td>" +
        "<td></td>";
      tr.lastElementChild.appendChild(cb);
      usersTbody.appendChild(tr);
    }
  }

  function setRowHighlight(id) {
    tbody.querySelectorAll("tr[data-tenant-id]").forEach((tr) => {
      tr.classList.toggle("orgs-row-selected", tr.getAttribute("data-tenant-id") === id);
    });
  }

  function renderTenantRows(tenants) {
    tbody.innerHTML = "";
    if (!tenants.length) {
      tbody.innerHTML = '<tr><td colspan="3" class="muted">No organisations.</td></tr>';
      return;
    }
    for (const t of tenants) {
      const tr = document.createElement("tr");
      tr.setAttribute("data-tenant-id", t.id);
      const ok = t.is_active ? "●" : '<span class="pill-inactive">off</span>';
      tr.innerHTML =
        "<td><code>" +
        escapeHtml(t.slug) +
        "</code></td>" +
        "<td>" +
        escapeHtml(t.plan_slug) +
        "</td>" +
        "<td>" +
        ok +
        "</td>";
      tr.addEventListener("click", () => selectOrg(t.id));
      tbody.appendChild(tr);
    }
    if (selectedTenantId) setRowHighlight(selectedTenantId);
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) =>
      ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      }[c])
    );
  }

  async function loadListQuiet() {
    const data = await fetchJSON("/api/super/tenants");
    renderTenantRows(data.tenants || []);
  }

  async function loadList() {
    clearFlash();
    try {
      await loadListQuiet();
    } catch (e) {
      showFlash("err", e.message);
      tbody.innerHTML = '<tr><td colspan="3" class="muted">Failed to load.</td></tr>';
    }
  }

  async function patchTenant(body) {
    const id = document.getElementById("orgs-edit-id").value;
    if (!id) throw new Error("No organisation selected");
    return fetchJSON("/api/super/tenants/" + encodeURIComponent(id), {
      method: "PATCH",
      body: JSON.stringify(body),
    });
  }

  async function selectOrg(tenantId) {
    clearFlash();
    selectedTenantId = tenantId;
    setRowHighlight(tenantId);
    try {
      await ensureMarketplace();
      const [detail, usersData] = await Promise.all([
        fetchJSON("/api/super/tenants/" + encodeURIComponent(tenantId)),
        fetchJSON("/api/super/tenants/" + encodeURIComponent(tenantId) + "/users"),
      ]);
      detailEmpty.hidden = true;
      detailPanel.hidden = false;
      applyDetail(detail, usersData.users || []);
    } catch (e) {
      showFlash("err", e.message);
    }
  }

  document.getElementById("orgs-form-profile").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    clearFlash();
    const name = document.getElementById("orgs-name").value.trim();
    if (!name) {
      showFlash("err", "Display name is required.");
      return;
    }
    try {
      const detail = await patchTenant({ name });
      applyDetail(detail);
      const uid = document.getElementById("orgs-edit-id").value;
      const usersData = await fetchJSON("/api/super/tenants/" + encodeURIComponent(uid) + "/users");
      renderUsers(usersData.users || []);
      showFlash("ok", "Profile saved.");
      loadListQuiet();
      setTimeout(clearFlash, 2200);
    } catch (e) {
      showFlash("err", e.message);
    }
  });

  document.getElementById("orgs-form-plan").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    clearFlash();
    try {
      const detail = await patchTenant({
        plan_slug: planSel.value,
        is_active: document.getElementById("orgs-active").checked,
      });
      applyDetail(detail);
      const uid = document.getElementById("orgs-edit-id").value;
      const usersData = await fetchJSON("/api/super/tenants/" + encodeURIComponent(uid) + "/users");
      renderUsers(usersData.users || []);
      showFlash("ok", "Plan & access saved.");
      loadListQuiet();
      setTimeout(clearFlash, 2200);
    } catch (e) {
      showFlash("err", e.message);
    }
  });

  document.getElementById("orgs-form-billing").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    clearFlash();
    try {
      const detail = await patchTenant({
        billing_contact_email: document.getElementById("orgs-billing-email").value.trim(),
        payment_provider_customer_id: document.getElementById("orgs-payment-id").value.trim(),
        notes: document.getElementById("orgs-notes").value.trim(),
      });
      document.getElementById("orgs-billing-email").value =
        detail.tenant.billing_contact_email || "";
      document.getElementById("orgs-payment-id").value =
        detail.tenant.payment_provider_customer_id || "";
      document.getElementById("orgs-notes").value = detail.tenant.notes || "";
      showFlash("ok", "Billing fields saved.");
      loadListQuiet();
      setTimeout(clearFlash, 2200);
    } catch (e) {
      showFlash("err", e.message);
    }
  });

  document.getElementById("orgs-form-agents").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    clearFlash();
    const body = {};
    if (customAgentsCb.checked) {
      const ids = [];
      agentsBox.querySelectorAll('input[type="checkbox"]').forEach((cb) => {
        if (!cb.disabled && cb.checked) ids.push(cb.value);
      });
      body.allowed_agent_ids = ids;
    } else {
      body.allowed_agent_ids = null;
    }
    try {
      const detail = await patchTenant(body);
      applyDetail(detail);
      const uid = document.getElementById("orgs-edit-id").value;
      const usersData = await fetchJSON("/api/super/tenants/" + encodeURIComponent(uid) + "/users");
      renderUsers(usersData.users || []);
      showFlash("ok", "Agents saved.");
      loadListQuiet();
      setTimeout(clearFlash, 2200);
    } catch (e) {
      showFlash("err", e.message);
    }
  });

  btnRefresh.addEventListener("click", loadList);

  loadList();
})();
