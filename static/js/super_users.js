(function () {
  const tenantSel = document.getElementById("su-tenant-select");
  const tbody = document.getElementById("su-users-body");
  const flash = document.getElementById("su-flash");
  const btnRefresh = document.getElementById("su-refresh-users");
  const dlg = document.getElementById("su-pw-dialog");

  let tenantsCache = [];
  let usersCache = [];

  function showFlash(kind, msg) {
    flash.textContent = msg || "";
    flash.className = "su-flash visible " + (kind === "ok" ? "ok" : "err");
  }

  function clearFlash() {
    flash.className = "su-flash";
    flash.textContent = "";
  }

  async function fetchJSON(url, opts) {
    const headers = { Accept: "application/json" };
    if (opts && opts.body != null) headers["Content-Type"] = "application/json";
    const r = await fetch(url, { credentials: "same-origin", headers, ...opts });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.error || r.statusText || "Request failed");
    return data;
  }

  async function loadTenants() {
    const data = await fetchJSON("/api/super/tenants");
    tenantsCache = data.tenants || [];
    tenantSel.innerHTML = '<option value="">Select organisation…</option>';
    for (const t of tenantsCache) {
      const opt = document.createElement("option");
      opt.value = t.id;
      opt.textContent = t.name + " (" + t.slug + ")";
      tenantSel.appendChild(opt);
    }
  }

  function selectedTenantId() {
    return tenantSel.value || "";
  }

  function currentUserId() {
    const el = document.getElementById("nexura-console-bootstrap");
    return (el && el.dataset.currentUserId) || "";
  }

  async function loadUsers() {
    const tid = selectedTenantId();
    if (!tid) {
      tbody.innerHTML =
        '<tr><td colspan="6" class="muted center">Select an organisation.</td></tr>';
      usersCache = [];
      return;
    }
    clearFlash();
    tbody.innerHTML = '<tr><td colspan="6" class="muted center">Loading…</td></tr>';
    const data = await fetchJSON("/api/super/tenants/" + encodeURIComponent(tid) + "/users");
    usersCache = data.users || [];
    if (!usersCache.length) {
      tbody.innerHTML = '<tr><td colspan="6" class="muted center">No users.</td></tr>';
      return;
    }
    tbody.innerHTML = "";
    const selfId = currentUserId();
    for (const u of usersCache) {
      const tr = document.createElement("tr");
      const roles = (u.roles || []).join(", ");
      const email = u.email || "—";
      const disableToggle = u.id === selfId;

      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.checked = !!u.is_active;
      cb.disabled = disableToggle;
      cb.title = disableToggle ? "Cannot disable your own account" : "Allow sign-in";
      cb.addEventListener("change", async () => {
        const want = cb.checked;
        try {
          await fetchJSON("/api/super/users/" + encodeURIComponent(u.id), {
            method: "PATCH",
            body: JSON.stringify({ is_active: want }),
          });
          showFlash("ok", "User updated.");
          setTimeout(clearFlash, 2000);
          await loadUsers();
        } catch (e) {
          showFlash("err", e.message);
          cb.checked = !want;
        }
      });

      const tdAct = document.createElement("td");
      tdAct.className = "col-actions";
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "btn btn-secondary btn-sm su-reset-pw";
      btn.setAttribute("data-user-id", u.id);
      btn.textContent = "Reset password";
      btn.addEventListener("click", () => openPwDialog(u.id));
      tdAct.appendChild(btn);

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
      tr.children[3].appendChild(cb);
      tr.appendChild(tdAct);
      tbody.appendChild(tr);
    }
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

  function escapeAttr(s) {
    return String(s).replace(/"/g, "&quot;");
  }

  function openPwDialog(userId) {
    const u = usersCache.find((x) => x.id === userId);
    document.getElementById("su-pw-target-user-id").value = userId;
    document.getElementById("su-pw-dialog-title").textContent = "Reset password";
    document.getElementById("su-pw-dialog-sub").textContent = u
      ? u.username + " · " + (u.email || "no email")
      : "";
    document.getElementById("su-pw-new").value = "";
    document.getElementById("su-pw-confirm").value = "";
    dlg.showModal();
    document.getElementById("su-pw-new").focus();
  }

  function closePwDialog() {
    dlg.close();
  }

  tenantSel.addEventListener("change", () => {
    loadUsers().catch((e) => showFlash("err", e.message));
  });

  btnRefresh.addEventListener("click", () => {
    loadUsers().catch((e) => showFlash("err", e.message));
  });

  document.getElementById("su-pw-cancel").addEventListener("click", closePwDialog);
  document.getElementById("su-pw-dialog-close").addEventListener("click", closePwDialog);
  dlg.addEventListener("click", (ev) => {
    if (ev.target === dlg) closePwDialog();
  });

  document.getElementById("su-pw-save").addEventListener("click", async () => {
    const uid = document.getElementById("su-pw-target-user-id").value;
    const p1 = document.getElementById("su-pw-new").value;
    const p2 = document.getElementById("su-pw-confirm").value;
    if (p1.length < 8) {
      showFlash("err", "Password must be at least 8 characters.");
      return;
    }
    if (p1 !== p2) {
      showFlash("err", "Passwords do not match.");
      return;
    }
    try {
      await fetchJSON("/api/super/users/" + encodeURIComponent(uid), {
        method: "PATCH",
        body: JSON.stringify({ password: p1 }),
      });
      closePwDialog();
      showFlash("ok", "Password updated.");
      setTimeout(clearFlash, 2500);
    } catch (e) {
      showFlash("err", e.message);
    }
  });

  loadTenants()
    .then(() => loadUsers())
    .catch((e) => showFlash("err", e.message));
})();
