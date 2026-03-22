(function () {
  const pageRoot = document.querySelector(".page");
  if (!pageRoot) return;

  const progressRoot = document.querySelector(".detail-progress");
  const apiPath = pageRoot.dataset.detailApiPath || "";

  const titleEl = document.querySelector(".detail-title");
  const subtitleEl = document.querySelector(".detail-subtitle");
  const imageEl = document.querySelector(".detail-image");
  const labelEl = progressRoot ? progressRoot.querySelector(".js-progress-label") : null;
  const percentEl = progressRoot ? progressRoot.querySelector(".js-progress-percent") : null;

  let latestClock = null;

  function buildFieldMap() {
    const map = new Map();
    document.querySelectorAll(".detail-field[data-field-key]").forEach((node) => {
      const key = node.dataset.fieldKey;
      const valueNode = node.querySelector(".detail-value");
      if (key && valueNode) map.set(key, valueNode);
    });
    return map;
  }

  const fields = buildFieldMap();

  function computeProgress(nowMs, startMs, endMs) {
    const total = Math.max(1, endMs - startMs);
    const elapsed = nowMs - startMs;
    const percent = Math.max(0, Math.min(100, Math.round((elapsed / total) * 100)));

    let label = "Live Tracking";
    if (nowMs < startMs) label = "Scheduled";
    else if (nowMs > endMs) label = "Arrived";

    return { percent, label };
  }

  function getNowMs() {
    if (!latestClock) return Date.now();
    const elapsedRealMs = Math.max(0, Date.now() - latestClock.receivedAtMs);
    return latestClock.simUnixMs + (elapsedRealMs * latestClock.timeScale);
  }

  function renderProgress() {
    if (!progressRoot) return;

    const startMs = Number(progressRoot.dataset.progressStartUnixMs || "");
    const endMs = Number(progressRoot.dataset.progressEndUnixMs || "");

    if (!Number.isFinite(startMs) || !Number.isFinite(endMs) || endMs <= startMs) return;

    const result = computeProgress(getNowMs(), startMs, endMs);
    progressRoot.style.setProperty("--progress-percent", String(result.percent));

    if (labelEl) labelEl.textContent = result.label;
    if (percentEl) percentEl.textContent = String(result.percent) + "%";
  }

  function applySnapshot(snapshot) {
    if (!snapshot) return;

    if (titleEl && snapshot.title) titleEl.textContent = snapshot.title;
    if (subtitleEl && snapshot.subtitle) subtitleEl.textContent = snapshot.subtitle;
    if (imageEl && snapshot.image_url) imageEl.src = snapshot.image_url;
    if (imageEl && snapshot.image_alt) imageEl.alt = snapshot.image_alt;

    const incomingFields = Array.isArray(snapshot.fields) ? snapshot.fields : [];
    incomingFields.forEach((field) => {
      if (!Array.isArray(field) || field.length < 3) return;
      const key = field[2];
      const value = field[1];
      const node = fields.get(key);
      if (node) node.textContent = value ?? "";
    });
  }

  async function refreshDetail() {
    if (!apiPath) return;

    try {
      const response = await fetch(apiPath, {
        method: "GET",
        headers: { "Accept": "application/json" },
        cache: "no-store",
      });

      if (!response.ok) return;

      const snapshot = await response.json();
      applySnapshot(snapshot);
    } catch (_) {
    }
  }

  function connectClock() {
    const scheme = window.location.protocol === "https:" ? "wss" : "ws";
    const socket = new WebSocket(scheme + "://" + window.location.host + "/ws/clock");

    socket.addEventListener("message", (event) => {
      try {
        const payload = JSON.parse(event.data);
        if (payload.kind !== "sync" || !payload.clock) return;

        latestClock = {
          simUnixMs: Number(payload.clock.sim_unix_ms),
          timeScale: Number(payload.clock.time_scale ?? 1),
          receivedAtMs: Date.now(),
        };

        renderProgress();
      } catch (_) {
      }
    });

    socket.addEventListener("open", renderProgress);
  }

  connectClock();
  renderProgress();
  window.setInterval(renderProgress, 250);
  window.setInterval(refreshDetail, 3000);
})();
