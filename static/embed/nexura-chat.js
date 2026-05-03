/**
 * Nexura embeddable chat widget.
 * Include once per page:
 *   <script defer src="https://YOUR-NEXURA-HOST/static/embed/nexura-chat.js"
 *     data-api-key="nxemb_..."
 *     data-base-url="https://YOUR-NEXURA-HOST"
 *     data-collection-ids="general,support"></script>
 * Optional data-collection-ids: comma/space-separated KB slugs or UUIDs (must fall within embed key scope).
 * Org-managed agent title, welcome message, and visitor contact form are loaded from GET /api/embed/widget-config.
 */
(function () {
  "use strict";

  var script = document.currentScript;
  if (!script) return;

  var apiKey = (script.getAttribute("data-api-key") || "").trim();
  var baseUrl = (script.getAttribute("data-base-url") || "").replace(/\/$/, "");
  var titleFallback = (script.getAttribute("data-title") || "Ask us").trim();
  var accent = (script.getAttribute("data-accent") || "#0f766e").trim();
  var collRaw = (script.getAttribute("data-collection-ids") || "").trim();
  var collectionIds = collRaw
    ? collRaw.split(/[\s,]+/).map(function (s) {
        return s.trim();
      }).filter(Boolean)
    : [];
  if (!/^#[0-9a-fA-F]{6}$/.test(accent)) accent = "#0f766e";

  if (!apiKey || !baseUrl) {
    console.warn("[Nexura] data-api-key and data-base-url are required.");
    return;
  }

  var storageKeySuffix = apiKey.slice(-16);
  var visitorStorageKey = "nexura_visitor_" + storageKeySuffix;
  var leadDoneStorageKey = "nexura_lead_ok_" + storageKeySuffix;

  function visitorId() {
    try {
      var v = localStorage.getItem(visitorStorageKey);
      if (!v) {
        v =
          "v_" +
          Math.random().toString(36).slice(2) +
          "_" +
          Date.now().toString(36);
        localStorage.setItem(visitorStorageKey, v);
      }
      return v;
    } catch {
      return "sess_" + Math.random().toString(36).slice(2);
    }
  }

  function leadGatePassed() {
    try {
      return localStorage.getItem(leadDoneStorageKey) === "1";
    } catch {
      return false;
    }
  }

  function markLeadGatePassed() {
    try {
      localStorage.setItem(leadDoneStorageKey, "1");
    } catch {
      /* ignore */
    }
  }

  var css =
    ".nexura-emb{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;box-sizing:border-box}" +
    ".nexura-emb *,.nexura-emb *::before,.nexura-emb *::after{box-sizing:inherit}" +
    ".nexura-launcher{position:fixed;bottom:1.25rem;right:1.25rem;z-index:2147483000;width:3.5rem;height:3.5rem;border-radius:50%;border:none;cursor:pointer;box-shadow:0 4px 24px rgba(15,23,42,.18);background:" +
    accent +
    ";color:#fff;font-size:1.35rem;line-height:1;display:flex;align-items:center;justify-content:center}" +
    ".nexura-launcher:hover{filter:brightness(1.06)}" +
    ".nexura-panel{position:fixed;bottom:5.5rem;right:1.25rem;z-index:2147483000;width:min(100vw - 2rem,380px);height:min(100vh - 7rem,520px);background:#fff;border-radius:14px;box-shadow:0 12px 48px rgba(15,23,42,.15);border:1px solid #e2e8f0;display:none;flex-direction:column;overflow:hidden}" +
    ".nexura-panel.open{display:flex}" +
    ".nexura-head{padding:.85rem 1rem;background:#f8fafc;border-bottom:1px solid #e2e8f0;font-weight:700;font-size:.95rem;color:#0f172a;display:flex;justify-content:space-between;align-items:center;gap:.5rem;flex-shrink:0}" +
    ".nexura-close{background:transparent;border:none;font-size:1.25rem;line-height:1;cursor:pointer;color:#64748b;padding:.15rem}" +
    ".nexura-body{flex:1;display:flex;flex-direction:column;min-height:0}" +
    ".nexura-lead-wrap{padding:.75rem;display:none;flex-direction:column;gap:.55rem;flex:1;overflow-y:auto}" +
    ".nexura-lead-wrap.nexura-show{display:flex}" +
    ".nexura-lead-wrap label{font-size:.76rem;color:#334155;display:flex;flex-direction:column;gap:.2rem;font-weight:600}" +
    ".nexura-lead-wrap input,.nexura-lead-wrap textarea{font-weight:400;border:1px solid #cbd5e1;border-radius:8px;padding:.45rem .55rem;font:inherit;font-size:.88rem}" +
    ".nexura-lead-wrap .nexura-req{color:#b91c1c;font-weight:700}" +
    ".nexura-lead-submit{margin-top:.25rem;padding:.55rem;border:none;border-radius:10px;background:" +
    accent +
    ";color:#fff;font-weight:600;cursor:pointer;font-size:.88rem}" +
    ".nexura-lead-submit:disabled{opacity:.55;cursor:not-allowed}" +
    ".nexura-main-wrap{display:none;flex-direction:column;flex:1;min-height:0}" +
    ".nexura-main-wrap.nexura-show{display:flex}" +
    ".nexura-msgs{flex:1;overflow-y:auto;padding:.75rem;display:flex;flex-direction:column;gap:.6rem;background:#fff}" +
    ".nexura-msg{max-width:92%;padding:.55rem .75rem;border-radius:10px;font-size:.88rem;line-height:1.45;white-space:pre-wrap;word-break:break-word}" +
    ".nexura-msg.u{align-self:flex-end;background:#ecfdf5;color:#0f172a;border:1px solid #99f6e4}" +
    ".nexura-msg.a{align-self:flex-start;background:#f1f5f9;color:#334155;border:1px solid #e2e8f0}" +
    ".nexura-cites{font-size:.75rem;color:#64748b;margin-top:.35rem}" +
    ".nexura-foot{padding:.65rem;border-top:1px solid #e2e8f0;display:flex;gap:.45rem;align-items:flex-end;background:#fafafa;flex-shrink:0}" +
    ".nexura-inp{flex:1;min-height:2.5rem;max-height:5rem;padding:.5rem .65rem;border:1px solid #cbd5e1;border-radius:10px;font:inherit;resize:none}" +
    ".nexura-send{padding:.5rem .85rem;border:none;border-radius:10px;background:" +
    accent +
    ";color:#fff;font-weight:600;cursor:pointer;font-size:.85rem}" +
    ".nexura-send:disabled{opacity:.55;cursor:not-allowed}" +
    ".nexura-brand{font-size:.68rem;color:#94a3b8;text-align:center;padding:.25rem;flex-shrink:0}" +
    ".nexura-lead-err{color:#b91c1c;font-size:.78rem;margin:0}" +
    ".nexura-msg.typing{color:#64748b;font-size:.88rem;letter-spacing:.12em}" +
    ".nexura-msg.typing .nexura-tdot span{display:inline-block;animation:nexura-emb-dot 1.2s ease-in-out infinite both}" +
    ".nexura-msg.typing .nexura-tdot span:nth-child(1){animation-delay:0s}" +
    ".nexura-msg.typing .nexura-tdot span:nth-child(2){animation-delay:.15s}" +
    ".nexura-msg.typing .nexura-tdot span:nth-child(3){animation-delay:.3s}" +
    "@keyframes nexura-emb-dot{0%,80%,100%{opacity:.35}40%{opacity:1}}";

  var style = document.createElement("style");
  style.textContent = css;
  document.head.appendChild(style);

  var root = document.createElement("div");
  root.className = "nexura-emb";
  root.innerHTML =
    '<button type="button" class="nexura-launcher" aria-label="Open chat">💬</button>' +
    '<div class="nexura-panel" role="dialog" aria-label="Chat">' +
    '<div class="nexura-head"><span></span><button type="button" class="nexura-close" aria-label="Close">×</button></div>' +
    '<div class="nexura-body">' +
    '<div class="nexura-lead-wrap">' +
    '<p class="muted nexura-lead-intro" style="margin:0;font-size:.82rem;color:#475569;line-height:1.45"></p>' +
    '<label>Comments or details (optional)<textarea class="nexura-in-msg" rows="3" maxlength="2000" placeholder="What should we know? Questions, context, or how we can help…"></textarea></label>' +
    '<label>Name <span class="nexura-req">*</span><input type="text" class="nexura-in-name" autocomplete="name" maxlength="255" /></label>' +
    '<label>Email <span class="nexura-req">*</span><input type="email" class="nexura-in-email" autocomplete="email" maxlength="255" /></label>' +
    '<label>Phone <span class="nexura-req">*</span><input type="tel" class="nexura-in-phone" autocomplete="tel" maxlength="64" placeholder="So we can reach you" /></label>' +
    '<p class="nexura-lead-err" hidden></p>' +
    '<button type="button" class="nexura-lead-submit">Continue to chat</button>' +
    "</div>" +
    '<div class="nexura-main-wrap">' +
    '<div class="nexura-msgs"></div>' +
    '<div class="nexura-foot">' +
    '<textarea class="nexura-inp" rows="1" placeholder="Message…"></textarea>' +
    '<button type="button" class="nexura-send">Send</button>' +
    "</div>" +
    "</div>" +
    "</div>" +
    '<div class="nexura-brand">Powered by Nexura</div>' +
    "</div>";

  document.body.appendChild(root);

  var launcher = root.querySelector(".nexura-launcher");
  var panel = root.querySelector(".nexura-panel");
  var headTitle = root.querySelector(".nexura-head span");
  var btnClose = root.querySelector(".nexura-close");
  var leadWrap = root.querySelector(".nexura-lead-wrap");
  var leadIntro = root.querySelector(".nexura-lead-intro");
  var inName = root.querySelector(".nexura-in-name");
  var inEmail = root.querySelector(".nexura-in-email");
  var inPhone = root.querySelector(".nexura-in-phone");
  var inLeadMsg = root.querySelector(".nexura-in-msg");
  var leadErr = root.querySelector(".nexura-lead-err");
  var btnLead = root.querySelector(".nexura-lead-submit");
  var mainWrap = root.querySelector(".nexura-main-wrap");
  var msgs = root.querySelector(".nexura-msgs");
  var inp = root.querySelector(".nexura-inp");
  var btnSend = root.querySelector(".nexura-send");

  var widgetCfg = {};
  var cfgLoaded = false;
  var welcomeShown = false;

  function fetchWidgetConfig() {
    return fetch(baseUrl + "/api/embed/widget-config", {
      method: "GET",
      headers: {
        Authorization: "Bearer " + apiKey,
      },
    })
      .then(function (r) {
        return r.json().then(function (j) {
          return { ok: r.ok, body: j };
        });
      })
      .then(function (x) {
        cfgLoaded = true;
        if (x.ok && x.body && typeof x.body === "object") {
          widgetCfg = x.body;
        } else {
          widgetCfg = {};
        }
        applyHeadTitle();
        return widgetCfg;
      })
      .catch(function () {
        cfgLoaded = true;
        widgetCfg = {};
        applyHeadTitle();
        return widgetCfg;
      });
  }

  function applyHeadTitle() {
    var t =
      (widgetCfg.agent_display_name && String(widgetCfg.agent_display_name).trim()) ||
      titleFallback ||
      "Ask us";
    headTitle.textContent = t;
  }

  applyHeadTitle();
  fetchWidgetConfig();

  function toggle(open) {
    panel.classList.toggle("open", open);
    launcher.setAttribute("aria-expanded", open ? "true" : "false");
  }

  function syncLeadVsChatLayout() {
    var collect = widgetCfg.collect_visitor_contact !== false;
    var needLead = collect && !leadGatePassed();
    leadWrap.classList.toggle("nexura-show", needLead);
    mainWrap.classList.toggle("nexura-show", !needLead);
    if (needLead) {
      leadIntro.textContent =
        "Use the comment box above for context if you like. Name, email, and phone are required so our team can follow up.";
      inp.disabled = true;
      btnSend.disabled = true;
    } else {
      inp.disabled = false;
      btnSend.disabled = false;
      maybeShowWelcome();
    }
  }

  function maybeShowWelcome() {
    if (welcomeShown) return;
    var w = widgetCfg.welcome_message && String(widgetCfg.welcome_message).trim();
    if (w) {
      welcomeShown = true;
      addMsg("assistant", w);
    }
  }

  launcher.addEventListener("click", function () {
    var opening = !panel.classList.contains("open");
    if (!opening) {
      toggle(false);
      return;
    }
    function finalizeOpen() {
      toggle(true);
      syncLeadVsChatLayout();
      if (leadWrap.classList.contains("nexura-show")) {
        inLeadMsg.focus();
      } else {
        inp.focus();
      }
    }
    if (cfgLoaded) finalizeOpen();
    else fetchWidgetConfig().then(finalizeOpen);
  });

  btnClose.addEventListener("click", function () {
    toggle(false);
  });

  function removeTypingMsg() {
    var el = msgs.querySelector(".nexura-msg.typing");
    if (el) el.remove();
  }

  function addTypingMsg() {
    removeTypingMsg();
    var div = document.createElement("div");
    div.className = "nexura-msg a typing";
    div.setAttribute("role", "status");
    div.setAttribute("aria-live", "polite");
    div.setAttribute("aria-label", "Assistant is typing");
    div.innerHTML =
      '<span class="nexura-tdot" aria-hidden="true"><span>.</span><span>.</span><span>.</span></span>';
    msgs.appendChild(div);
    msgs.scrollTop = msgs.scrollHeight;
  }

  function addMsg(role, text) {
    var div = document.createElement("div");
    div.className = "nexura-msg " + (role === "user" ? "u" : "a");
    div.textContent = text;
    msgs.appendChild(div);
    msgs.scrollTop = msgs.scrollHeight;
  }

  function send() {
    var text = (inp.value || "").trim();
    if (!text) return;
    inp.value = "";
    addMsg("user", text);
    btnSend.disabled = true;
    inp.disabled = true;
    addTypingMsg();

    fetch(baseUrl + "/api/embed/chat", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: "Bearer " + apiKey,
      },
      body: JSON.stringify(
        Object.assign(
          {
            chat_message: text,
            visitor_session: visitorId(),
          },
          collectionIds.length ? { collection_ids: collectionIds } : {}
        )
      ),
    })
      .then(function (r) {
        return r.json().then(function (j) {
          return { ok: r.ok, body: j };
        });
      })
      .then(function (_ref) {
        removeTypingMsg();
        var ok = _ref.ok;
        var data = _ref.body;
        if (!ok) {
          addMsg(
            "assistant",
            data.error || "Something went wrong. Please try again."
          );
          return;
        }
        addMsg(
          "assistant",
          typeof data.answer === "string"
            ? data.answer
            : JSON.stringify(data.answer)
        );
      })
      .catch(function () {
        removeTypingMsg();
        addMsg(
          "assistant",
          "Network error. Check your connection and CORS settings."
        );
      })
      .finally(function () {
        removeTypingMsg();
        btnSend.disabled = false;
        inp.disabled = false;
      });
  }

  btnSend.addEventListener("click", send);
  inp.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  });

  btnLead.addEventListener("click", function () {
    leadErr.hidden = true;
    leadErr.textContent = "";
    var nm = (inName.value || "").trim();
    var em = (inEmail.value || "").trim();
    var ph = (inPhone.value || "").trim();
    var lm = (inLeadMsg.value || "").trim();
    if (!nm || !em || !ph) {
      leadErr.textContent = "Name, email, and phone are required.";
      leadErr.hidden = false;
      return;
    }
    btnLead.disabled = true;
    fetch(baseUrl + "/api/embed/visitor-contact", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: "Bearer " + apiKey,
      },
      body: JSON.stringify({
        visitor_session: visitorId(),
        name: nm,
        email: em,
        phone: ph || undefined,
        message: lm || undefined,
      }),
    })
      .then(function (r) {
        return r.json().then(function (j) {
          return { ok: r.ok, body: j };
        });
      })
      .then(function (_ref2) {
        var ok = _ref2.ok;
        var data = _ref2.body;
        if (!ok) {
          leadErr.textContent = data.error || "Could not save your details.";
          leadErr.hidden = false;
          return;
        }
        markLeadGatePassed();
        syncLeadVsChatLayout();
        inp.focus();
      })
      .catch(function () {
        leadErr.textContent = "Network error. Try again.";
        leadErr.hidden = false;
      })
      .finally(function () {
        btnLead.disabled = false;
      });
  });
})();
