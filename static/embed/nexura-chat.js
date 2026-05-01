/**
 * Nexura embeddable chat widget.
 * Include once per page:
 *   <script defer src="https://YOUR-NEXURA-HOST/static/embed/nexura-chat.js"
 *     data-api-key="nxemb_..."
 *     data-base-url="https://YOUR-NEXURA-HOST"></script>
 */
(function () {
  "use strict";

  var script = document.currentScript;
  if (!script) return;

  var apiKey = (script.getAttribute("data-api-key") || "").trim();
  var baseUrl = (script.getAttribute("data-base-url") || "").replace(/\/$/, "");
  var title = (script.getAttribute("data-title") || "Ask us").trim();
  var accent = (script.getAttribute("data-accent") || "#0f766e").trim();
  if (!/^#[0-9a-fA-F]{6}$/.test(accent)) accent = "#0f766e";

  if (!apiKey || !baseUrl) {
    console.warn("[Nexura] data-api-key and data-base-url are required.");
    return;
  }

  var storageKey = "nexura_visitor_" + apiKey.slice(-16);
  function visitorId() {
    try {
      var v = localStorage.getItem(storageKey);
      if (!v) {
        v =
          "v_" +
          Math.random().toString(36).slice(2) +
          "_" +
          Date.now().toString(36);
        localStorage.setItem(storageKey, v);
      }
      return v;
    } catch {
      return "sess_" + Math.random().toString(36).slice(2);
    }
  }

  var css =
    ".nexura-emb{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;box-sizing:border-box}" +
    ".nexura-emb *,.nexura-emb *::before,.nexura-emb *::after{box-sizing:inherit}" +
    ".nexura-launcher{position:fixed;bottom:1.25rem;right:1.25rem;z-index:2147483000;width:3.5rem;height:3.5rem;border-radius:50%;border:none;cursor:pointer;box-shadow:0 4px 24px rgba(15,23,42,.18);background:" +
    accent +
    ";color:#fff;font-size:1.35rem;line-height:1;display:flex;align-items:center;justify-content:center}" +
    ".nexura-launcher:hover{filter:brightness(1.06)}" +
    ".nexura-panel{position:fixed;bottom:5.5rem;right:1.25rem;z-index:2147483000;width:min(100vw - 2rem,380px);height:min(100vh - 7rem,460px);background:#fff;border-radius:14px;box-shadow:0 12px 48px rgba(15,23,42,.15);border:1px solid #e2e8f0;display:none;flex-direction:column;overflow:hidden}" +
    ".nexura-panel.open{display:flex}" +
    ".nexura-head{padding:.85rem 1rem;background:#f8fafc;border-bottom:1px solid #e2e8f0;font-weight:700;font-size:.95rem;color:#0f172a;display:flex;justify-content:space-between;align-items:center;gap:.5rem}" +
    ".nexura-close{background:transparent;border:none;font-size:1.25rem;line-height:1;cursor:pointer;color:#64748b;padding:.15rem}" +
    ".nexura-msgs{flex:1;overflow-y:auto;padding:.75rem;display:flex;flex-direction:column;gap:.6rem;background:#fff}" +
    ".nexura-msg{max-width:92%;padding:.55rem .75rem;border-radius:10px;font-size:.88rem;line-height:1.45;white-space:pre-wrap;word-break:break-word}" +
    ".nexura-msg.u{align-self:flex-end;background:#ecfdf5;color:#0f172a;border:1px solid #99f6e4}" +
    ".nexura-msg.a{align-self:flex-start;background:#f1f5f9;color:#334155;border:1px solid #e2e8f0}" +
    ".nexura-cites{font-size:.75rem;color:#64748b;margin-top:.35rem}" +
    ".nexura-foot{padding:.65rem;border-top:1px solid #e2e8f0;display:flex;gap:.45rem;align-items:flex-end;background:#fafafa}" +
    ".nexura-inp{flex:1;min-height:2.5rem;max-height:5rem;padding:.5rem .65rem;border:1px solid #cbd5e1;border-radius:10px;font:inherit;resize:none}" +
    ".nexura-send{padding:.5rem .85rem;border:none;border-radius:10px;background:" +
    accent +
    ";color:#fff;font-weight:600;cursor:pointer;font-size:.85rem}" +
    ".nexura-send:disabled{opacity:.55;cursor:not-allowed}" +
    ".nexura-brand{font-size:.68rem;color:#94a3b8;text-align:center;padding:.25rem}";

  var style = document.createElement("style");
  style.textContent = css;
  document.head.appendChild(style);

  var root = document.createElement("div");
  root.className = "nexura-emb";
  root.innerHTML =
    '<button type="button" class="nexura-launcher" aria-label="Open chat">💬</button>' +
    '<div class="nexura-panel" role="dialog" aria-label="Chat">' +
    '<div class="nexura-head"><span></span><button type="button" class="nexura-close" aria-label="Close">×</button></div>' +
    '<div class="nexura-msgs"></div>' +
    '<div class="nexura-foot">' +
    '<textarea class="nexura-inp" rows="1" placeholder="Message…"></textarea>' +
    '<button type="button" class="nexura-send">Send</button>' +
    "</div>" +
    '<div class="nexura-brand">Powered by Nexura</div>' +
    "</div>";

  document.body.appendChild(root);

  var launcher = root.querySelector(".nexura-launcher");
  var panel = root.querySelector(".nexura-panel");
  var headTitle = root.querySelector(".nexura-head span");
  var btnClose = root.querySelector(".nexura-close");
  var msgs = root.querySelector(".nexura-msgs");
  var inp = root.querySelector(".nexura-inp");
  var btnSend = root.querySelector(".nexura-send");

  headTitle.textContent = title;

  function toggle(open) {
    panel.classList.toggle("open", open);
    launcher.setAttribute("aria-expanded", open ? "true" : "false");
  }

  launcher.addEventListener("click", function () {
    toggle(!panel.classList.contains("open"));
  });
  btnClose.addEventListener("click", function () {
    toggle(false);
  });

  function addMsg(role, text, citations) {
    var div = document.createElement("div");
    div.className = "nexura-msg " + (role === "user" ? "u" : "a");
    div.textContent = text;
    if (citations && citations.length) {
      var c = document.createElement("div");
      c.className = "nexura-cites";
      c.textContent = "Sources: " + citations.join(", ");
      div.appendChild(c);
    }
    msgs.appendChild(div);
    msgs.scrollTop = msgs.scrollHeight;
  }

  function send() {
    var text = (inp.value || "").trim();
    if (!text) return;
    inp.value = "";
    addMsg("user", text);
    btnSend.disabled = true;

    fetch(baseUrl + "/api/embed/chat", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: "Bearer " + apiKey,
      },
      body: JSON.stringify({
        chat_message: text,
        visitor_session: visitorId(),
      }),
    })
      .then(function (r) {
        return r.json().then(function (j) {
          return { ok: r.ok, body: j };
        });
      })
      .then(function (_ref) {
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
            : JSON.stringify(data.answer),
          data.citations
        );
      })
      .catch(function () {
        addMsg("assistant", "Network error. Check your connection and CORS settings.");
      })
      .finally(function () {
        btnSend.disabled = false;
      });
  }

  btnSend.addEventListener("click", send);
  inp.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  });
})();
