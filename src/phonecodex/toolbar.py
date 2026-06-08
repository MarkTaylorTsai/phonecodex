from __future__ import annotations


def toolbar_js(index_port: int) -> str:
    return f"""
(function () {{
  const apiBase = window.PHONECODEX_API_BASE || `${{location.protocol}}//${{location.hostname}}:{index_port}`;
  const configuredSessionName = window.PHONECODEX_SESSION_NAME || "";
  let sessionName = "";

  function focusTerminal() {{
    const textarea = document.querySelector(".xterm-helper-textarea");
    const terminal = document.querySelector(".xterm");
    if (textarea) textarea.focus();
    else if (terminal) terminal.focus();
  }}

  function setStatus(text) {{
    const status = document.getElementById("pcx-status");
    if (!status) return;
    status.textContent = text;
    window.clearTimeout(setStatus.timer);
    setStatus.timer = window.setTimeout(() => {{
      status.textContent = sessionName || "";
    }}, 1600);
  }}

  async function api(path, body) {{
    const response = await fetch(`${{apiBase}}${{path}}`, {{
      method: "POST",
      headers: {{ "Content-Type": "application/json" }},
      body: JSON.stringify(body),
    }});
    if (!response.ok) throw new Error(await response.text());
    return response.json();
  }}

  async function sendKey(key) {{
    if (!sessionName) return;
    try {{
      await api("/api/key", {{ session: sessionName, key }});
      focusTerminal();
    }} catch (error) {{
      setStatus("error");
    }}
  }}

  async function sendPasteText(text, submit) {{
    if (!sessionName || !text) return;
    try {{
      await api("/api/paste", {{ session: sessionName, text, submit: !!submit }});
      setStatus(submit ? "asked" : "pasted");
      focusTerminal();
    }} catch (error) {{
      setStatus("paste error");
    }}
  }}

  function showPastePanel(initialText) {{
    let panel = document.getElementById("pcx-paste-panel");
    if (!panel) {{
      panel = document.createElement("div");
      panel.id = "pcx-paste-panel";
      panel.innerHTML = `
        <div class="pcx-modal-box">
          <textarea id="pcx-paste-text" spellcheck="false" autocapitalize="off" autocomplete="off" placeholder="Long-press here and tap Paste, then Insert or Ask"></textarea>
          <div class="pcx-modal-actions">
            <button id="pcx-paste-read" type="button">Read Clipboard</button>
            <button id="pcx-paste-insert" type="button">Insert</button>
            <button id="pcx-paste-ask" type="button">Ask</button>
            <button id="pcx-paste-close" type="button">Close</button>
          </div>
        </div>`;
      document.body.appendChild(panel);

      const textarea = panel.querySelector("#pcx-paste-text");
      const close = () => panel.remove();
      const send = async (submit) => {{
        const text = textarea.value;
        close();
        await sendPasteText(text, submit);
      }};

      panel.querySelector("#pcx-paste-close").addEventListener("click", close);
      panel.querySelector("#pcx-paste-insert").addEventListener("click", () => send(false));
      panel.querySelector("#pcx-paste-ask").addEventListener("click", () => send(true));
      panel.querySelector("#pcx-paste-read").addEventListener("click", async () => {{
        try {{
          textarea.value = await navigator.clipboard.readText();
          setStatus("clipboard read");
        }} catch (error) {{
          setStatus("long-press paste");
          textarea.focus();
        }}
      }});
      textarea.addEventListener("keydown", (event) => {{
        if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {{
          event.preventDefault();
          send(true);
        }}
      }});
    }}

    const textarea = panel.querySelector("#pcx-paste-text");
    textarea.value = initialText || "";
    window.setTimeout(() => textarea.focus(), 80);
    setStatus("paste box");
  }}

  async function pasteClipboard() {{
    if (!sessionName) return;
    if (!window.isSecureContext || !navigator.clipboard?.readText) {{
      showPastePanel("");
      return;
    }}
    try {{
      const text = await navigator.clipboard.readText();
      if (text) {{
        showPastePanel(text);
        return;
      }}
    }} catch (error) {{
      // Mobile browsers often block clipboard reads outside HTTPS or without a
      // direct permission grant, so the manual paste box remains the fallback.
    }}
    showPastePanel("");
  }}

  function showCopyPanel(text) {{
    let panel = document.getElementById("pcx-copy-panel");
    if (!panel) {{
      panel = document.createElement("div");
      panel.id = "pcx-copy-panel";
      panel.innerHTML = `
        <div class="pcx-modal-box">
          <textarea id="pcx-copy-text" spellcheck="false"></textarea>
          <div class="pcx-modal-actions">
            <button id="pcx-copy-close" type="button">Close</button>
          </div>
        </div>`;
      document.body.appendChild(panel);
      panel.querySelector("#pcx-copy-close").addEventListener("click", () => panel.remove());
    }}
    const textarea = panel.querySelector("#pcx-copy-text");
    textarea.value = text;
    textarea.focus();
    textarea.select();
  }}

  async function copyScreen() {{
    if (!sessionName) return;
    try {{
      const response = await fetch(`${{apiBase}}/api/capture?session=${{encodeURIComponent(sessionName)}}`);
      if (!response.ok) throw new Error(await response.text());
      const data = await response.json();
      try {{
        await navigator.clipboard.writeText(data.text || "");
        setStatus("copied");
      }} catch (error) {{
        showCopyPanel(data.text || "");
        setStatus("select text");
      }}
    }} catch (error) {{
      setStatus("copy error");
    }}
  }}

  function button(label, action, cssClass) {{
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = label;
    if (cssClass) btn.className = cssClass;
    btn.addEventListener("click", action);
    return btn;
  }}

  function installToolbar() {{
    if (document.getElementById("pcx-toolbar")) return;

    const style = document.createElement("style");
    style.textContent = `
      :root {{ --pcx-toolbar-height: 104px; }}
      body.pcx-mobile-toolbar #terminal-container {{
        height: calc(100% - var(--pcx-toolbar-height)) !important;
      }}
      #pcx-toolbar {{
        position: fixed;
        left: 0;
        right: 0;
        bottom: 0;
        z-index: 2147483647;
        min-height: var(--pcx-toolbar-height);
        box-sizing: border-box;
        padding: 7px 8px calc(7px + env(safe-area-inset-bottom));
        background: #17191f;
        border-top: 1px solid #343741;
        color: #f4f4f5;
        font: 13px system-ui, sans-serif;
      }}
      #pcx-toolbar .pcx-row {{
        display: flex;
        gap: 6px;
        overflow-x: auto;
        padding: 2px 0;
      }}
      #pcx-toolbar button {{
        flex: 0 0 auto;
        min-width: 44px;
        height: 34px;
        border: 1px solid #3f4350;
        border-radius: 7px;
        background: #252934;
        color: #f4f4f5;
        font: 600 13px system-ui, sans-serif;
      }}
      #pcx-toolbar button:active {{ background: #3a4050; }}
      #pcx-toolbar .pcx-wide {{ min-width: 64px; }}
      #pcx-status {{
        min-width: 84px;
        align-content: center;
        color: #a1a1aa;
        padding-left: 4px;
        white-space: nowrap;
      }}
      #pcx-toolbar.pcx-collapsed {{
        min-height: 48px;
        --pcx-toolbar-height: 48px;
      }}
      #pcx-toolbar.pcx-collapsed .pcx-extra {{ display: none; }}
      #pcx-copy-panel,
      #pcx-paste-panel {{
        position: fixed;
        inset: 12px;
        z-index: 2147483647;
        background: rgba(0, 0, 0, 0.62);
        display: flex;
        align-items: center;
        justify-content: center;
      }}
      .pcx-modal-box {{
        width: min(760px, 94vw);
        height: min(520px, 72vh);
        background: #17191f;
        border: 1px solid #3f4350;
        border-radius: 8px;
        padding: 10px;
        box-sizing: border-box;
        display: flex;
        flex-direction: column;
        gap: 8px;
      }}
      #pcx-copy-text,
      #pcx-paste-text {{
        flex: 1;
        min-height: 0;
        resize: none;
        background: #0b0d12;
        color: #f4f4f5;
        border: 1px solid #3f4350;
        border-radius: 6px;
        padding: 8px;
        font: 12px ui-monospace, SFMono-Regular, Menlo, monospace;
      }}
      .pcx-modal-actions {{
        display: flex;
        justify-content: flex-end;
        gap: 8px;
        flex-wrap: wrap;
      }}
    `;
    document.head.appendChild(style);
    document.body.classList.add("pcx-mobile-toolbar");

    const toolbar = document.createElement("div");
    toolbar.id = "pcx-toolbar";

    const row1 = document.createElement("div");
    row1.className = "pcx-row";
    row1.append(
      button("Esc", () => sendKey("esc")),
      button("Tab", () => sendKey("tab")),
      button("C-C", () => sendKey("ctrl-c")),
      button("C-D", () => sendKey("ctrl-d")),
      button("C-U", () => sendKey("ctrl-u")),
      button("C-K", () => sendKey("ctrl-k")),
      button("Paste", pasteClipboard, "pcx-wide"),
      button("Copy", copyScreen, "pcx-wide"),
      button("KB", focusTerminal),
      button("Hide", () => {{
        toolbar.classList.toggle("pcx-collapsed");
        document.documentElement.style.setProperty(
          "--pcx-toolbar-height",
          toolbar.classList.contains("pcx-collapsed") ? "48px" : "104px"
        );
      }})
    );

    const row2 = document.createElement("div");
    row2.className = "pcx-row pcx-extra";
    row2.append(
      button("Home", () => sendKey("home"), "pcx-wide"),
      button("Up", () => sendKey("up")),
      button("End", () => sendKey("end"), "pcx-wide"),
      button("Left", () => sendKey("left"), "pcx-wide"),
      button("Down", () => sendKey("down"), "pcx-wide"),
      button("Right", () => sendKey("right"), "pcx-wide"),
      button("Enter", () => sendKey("enter"), "pcx-wide"),
      button("Bksp", () => sendKey("backspace"), "pcx-wide"),
      button("Del", () => sendKey("delete")),
      Object.assign(document.createElement("div"), {{ id: "pcx-status", textContent: "" }})
    );

    toolbar.append(row1, row2);
    document.body.appendChild(toolbar);
  }}

  async function init() {{
    installToolbar();
    if (configuredSessionName) {{
      sessionName = configuredSessionName;
      setStatus(sessionName);
      return;
    }}
    try {{
      const response = await fetch(`${{apiBase}}/api/session?port=${{encodeURIComponent(location.port)}}`);
      if (!response.ok) throw new Error(await response.text());
      const data = await response.json();
      sessionName = data.name || "";
      setStatus(sessionName);
    }} catch (error) {{
      setStatus("no session");
    }}
  }}

  if (document.readyState === "loading") {{
    document.addEventListener("DOMContentLoaded", init);
  }} else {{
    init();
  }}
}})();
"""
