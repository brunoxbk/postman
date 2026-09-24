document.querySelectorAll(".message-close").forEach((btn) => {
  btn.addEventListener("click", () => {
    btn.closest(".message").remove();
  });
});

document.querySelectorAll(".toggle-raw").forEach((btn) => {
  btn.addEventListener("click", () => {
    const raw = btn.nextElementSibling;
    raw.hidden = !raw.hidden;
  });
});

document.querySelectorAll(".js-lock").forEach((form) => {
  form.addEventListener("submit", () => {
    const btn = form.querySelector('button[type="submit"]');
    if (btn) {
      btn.disabled = true;
      btn.textContent = "Sincronizando…";
    }
  });
});

const copyBtn = document.getElementById("copy-code");
if (copyBtn) {
  copyBtn.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(copyBtn.dataset.code);
      copyBtn.classList.add("copied");
      copyBtn.textContent = "Copiado ✓";
      setTimeout(() => {
        copyBtn.classList.remove("copied");
        copyBtn.textContent = "Copiar código";
      }, 1500);
    } catch {
      /* clipboard indisponível — ignora */
    }
  });
}

if (document.body.hasAttribute("data-auto-refresh")) {
  const interval = Number(document.body.dataset.interval) || 60000;
  const url = document.body.dataset.refreshUrl || window.location.href;

  const replaceFrom = (selector, doc) => {
    const current = document.querySelector(selector);
    const fresh = doc.querySelector(selector);
    if (current && fresh) current.replaceWith(fresh);
  };

  async function refreshDashboard() {
    if (document.hidden) return;
    try {
      const res = await fetch(url, {
        headers: { "X-Requested-With": "XMLHttpRequest" },
      });
      if (!res.ok) return;
      const doc = new DOMParser().parseFromString(await res.text(), "text/html");
      replaceFrom(".cards", doc);
      replaceFrom(".quota", doc);
      replaceFrom(".table-scroll", doc);
      replaceFrom(".pagination", doc);
    } catch {
      /* falha silenciosa — tenta de novo no próximo ciclo */
    }
  }

  setInterval(refreshDashboard, interval);
}