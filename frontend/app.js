(() => {
  const chatLog = document.getElementById("chat-log");
  const form = document.getElementById("chat-form");
  const input = document.getElementById("chat-input");
  const sendBtn = document.getElementById("send-btn");
  const statusLine = document.getElementById("status-line");
  const overlay = document.getElementById("terms-overlay");
  const termsText = document.getElementById("terms-text");
  const acceptBtn = document.getElementById("accept-btn");
  const turnstileContainer = document.getElementById("turnstile-container");
  const kbStatus = document.getElementById("kb-status");

  const TERMS_KEY = "tr4_terms_accepted";

  let config = { api_key: "", turnstile_site_key: "" };
  let turnstileWidgetId = null;
  let pendingTurnstileResolve = null;

  function setStatus(text, isError) {
    statusLine.textContent = text || "";
    statusLine.classList.toggle("error", Boolean(isError));
  }

  function addMessage(role, text) {
    const el = document.createElement("div");
    el.className = `msg ${role}`;
    el.textContent = text;
    chatLog.appendChild(el);
    chatLog.scrollTop = chatLog.scrollHeight;
    return el;
  }

  function addBotReply(reply, disclaimer) {
    const el = document.createElement("div");
    el.className = "msg bot";

    const replyP = document.createElement("div");
    replyP.textContent = reply;
    el.appendChild(replyP);

    if (disclaimer) {
      const disc = document.createElement("div");
      disc.className = "disclaimer";
      disc.textContent = disclaimer;
      el.appendChild(disc);
    }

    chatLog.appendChild(el);
    chatLog.scrollTop = chatLog.scrollHeight;
  }

  async function loadConfig() {
    // One retry: an intermittent pooled-DB hiccup on the backend (rare, but
    // real — see store.py) shouldn't permanently strand a page load with no
    // api_key, which breaks every /chat call for the rest of that session.
    for (let attempt = 0; attempt < 2; attempt++) {
      try {
        const res = await fetch("/config");
        if (!res.ok) throw new Error(`config ${res.status}`);
        config = await res.json();
        break;
      } catch (e) {
        config = { api_key: "", turnstile_site_key: "" };
        if (attempt === 0) await new Promise((r) => setTimeout(r, 1500));
      }
    }
    renderKbStatus();
  }

  function renderKbStatus() {
    if (!kbStatus) return;
    const parts = [];
    if (config.kb_updated_at) {
      const d = new Date(config.kb_updated_at);
      parts.push(`Base atualizada em ${d.toLocaleDateString("pt-BR")}`);
    }
    if (config.kb_chunks) {
      parts.push(`${config.kb_chunks.toLocaleString("pt-BR")} trechos indexados`);
    }
    if (config.version) {
      parts.push(`v${config.version}`);
    }
    kbStatus.textContent = parts.join(" · ");
  }

  async function loadTerms() {
    try {
      const res = await fetch("/terms");
      const data = await res.json();
      termsText.textContent = data.terms;
    } catch (e) {
      termsText.textContent =
        "Não foi possível carregar os termos agora. Recarregue a página antes de continuar.";
      acceptBtn.disabled = true;
    }
  }

  function renderTurnstileIfNeeded() {
    if (!config.turnstile_site_key) return;
    const trySetup = () => {
      if (typeof turnstile === "undefined") {
        setTimeout(trySetup, 200);
        return;
      }
      turnstileWidgetId = turnstile.render(turnstileContainer, {
        sitekey: config.turnstile_site_key,
        appearance: "interaction-only",
        execution: "execute",
        callback: (token) => {
          if (pendingTurnstileResolve) {
            pendingTurnstileResolve(token);
            pendingTurnstileResolve = null;
          }
        },
      });
    };
    trySetup();
  }

  function getTurnstileToken() {
    if (!config.turnstile_site_key || turnstileWidgetId === null) {
      return Promise.resolve(null);
    }
    return new Promise((resolve) => {
      pendingTurnstileResolve = resolve;
      turnstile.reset(turnstileWidgetId);
      turnstile.execute(turnstileWidgetId);
    });
  }

  function termsAccepted() {
    return localStorage.getItem(TERMS_KEY) === "true";
  }

  async function showTermsGate() {
    if (termsAccepted()) return;
    overlay.hidden = false;
    await loadTerms();
    await new Promise((resolve) => {
      acceptBtn.addEventListener(
        "click",
        () => {
          localStorage.setItem(TERMS_KEY, "true");
          overlay.hidden = true;
          resolve();
        },
        { once: true }
      );
    });
  }

  async function sendMessage(message) {
    const captchaToken = await getTurnstileToken();
    const headers = { "Content-Type": "application/json" };
    if (config.api_key) headers["X-API-Key"] = config.api_key;

    const res = await fetch("/chat", {
      method: "POST",
      headers,
      body: JSON.stringify({
        message,
        accepted_terms: true,
        captcha_token: captchaToken,
      }),
    });

    if (res.status === 403) {
      const data = await res.json().catch(() => ({}));
      if (data.detail && data.detail.error === "terms_not_accepted") {
        localStorage.removeItem(TERMS_KEY);
        await showTermsGate();
        return sendMessage(message);
      }
      throw new Error("Verificação anti-robô falhou. Tente de novo.");
    }
    if (res.status === 429) {
      throw new Error("Muitas perguntas em pouco tempo. Espere um minuto e tente de novo.");
    }
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || `Erro ${res.status} ao consultar o assistente.`);
    }
    return res.json();
  }

  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const message = input.value.trim();
    if (!message) return;

    addMessage("user", message);
    input.value = "";
    input.style.height = "auto";
    sendBtn.disabled = true;
    setStatus("Consultando base do TR4...");

    try {
      const data = await sendMessage(message);
      addBotReply(data.reply, data.disclaimer);
      setStatus("");
    } catch (err) {
      addMessage("error", err.message || "Erro inesperado. Tente de novo.");
      setStatus("Falha ao responder.", true);
    } finally {
      sendBtn.disabled = false;
      input.focus();
    }
  });

  input.addEventListener("input", () => {
    input.style.height = "auto";
    input.style.height = `${Math.min(input.scrollHeight, 140)}px`;
  });

  input.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter" && !ev.shiftKey) {
      ev.preventDefault();
      form.requestSubmit();
    }
  });

  (async () => {
    await loadConfig();
    renderTurnstileIfNeeded();
    await showTermsGate();
    addMessage(
      "bot",
      "Oi! Pergunte sobre peça, manutenção ou instalação do Pajero TR4."
    );
  })();
})();
