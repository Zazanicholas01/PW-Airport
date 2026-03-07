const $ = (id) => document.getElementById(id);

let simNowMs = null;
let simTimeScale = null;

const DEBUG_PLANE_PAGE = true;

let planeById = new Map();
let flightById = new Map();
let planeViewsReady = false;
const completedFlightIds = new Set();

// Visible "is the new JS loaded?" signal (also useful if console output is filtered).
try {
  const stamp = new Date().toISOString();
  // eslint-disable-next-line no-console
  console.log(`[dashboard] dashboard.js loaded ${stamp}`);
} catch {}

function dbg(msg, obj) {
  if (!DEBUG_PLANE_PAGE) return;
  try {
    // console.debug is often hidden unless "Verbose" is enabled; use log.
    // eslint-disable-next-line no-console
    console.log(`[dashboard] ${msg}`, obj ?? "");
  } catch {}
}

function toDate(s) {
  return s ? new Date(s) : null;
}

function parseDateMs(s) {
  if (!s) return null;
  const ms = Date.parse(s);
  return Number.isFinite(ms) ? ms : null;
}

function fmtLocalTimeFromIso(iso) {
  try {
    return iso ? new Date(iso).toLocaleTimeString() : "";
  } catch {
    return "";
  }
}

function minsUntil(dt) {
  const base = simNowMs ? new Date(simNowMs) : new Date();
  return Math.round((dt - base) / 60000);
}

function fmtWhen(f) {
  const airport = $("airport").value.trim();
  const isDep = f.origin === airport;
  const t = isDep ? f.departure_time : f.arrival_time || f.departure_time;
  return { t, label: isDep ? "DEP" : "ARR" };
}

function statusClass(status) {
  const s = String(status || "").toLowerCase();
  if (s.includes("scheduled")) return "status-scheduled";
  if (s.includes("boarding")) return "status-boarding";
  if (s.includes("landing")) return "status-landing";
  if (s.includes("parked")) return "status-parked";
  if (s.includes("completed")) return "status-completed";
  return "status-default";
}

function esc(s) {
  return String(s ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function fmtVec3(pos) {
  if (!pos || typeof pos !== "object") return "";
  const x = Number(pos.x),
    y = Number(pos.y),
    z = Number(pos.z);
  if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(z)) return "";
  return `${x.toFixed(1)}, ${y.toFixed(1)}, ${z.toFixed(1)}`;
}

function slugifyModel(model) {
  return String(model ?? "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function planeImageUrlForModel(model) {
  const slug = slugifyModel(model);
  return slug
    ? `/static/planes/models/${encodeURIComponent(slug)}.png`
    : "/static/planes/_default.png";
}

function flightIdForRow(f) {
  return String((f && (f.icao || f.id)) || "");
}

function setPlaneDebug(text) {
  void text;
}

function setFlightDebug(text) {
  void text;
}

function setVisible(el, visible) {
  if (!el) return;
  if (visible) {
    el.classList.remove("hidden");
    el.style.display = "";
  } else {
    el.classList.add("hidden");
    el.style.display = "none";
  }
}

function ensurePlaneViews() {
  if (planeViewsReady) return;
  const panel = document.querySelector(".panel");
  if (!panel) return;

  let listView = $("list_view");
  let planeView = $("plane_view");
  let flightView = $("flight_view");

  if (!listView) {
    listView = document.createElement("div");
    listView.id = "list_view";

    while (panel.firstChild) listView.appendChild(panel.firstChild);
    panel.appendChild(listView);
  }

  if (!planeView) {
    planeView = document.createElement("div");
    planeView.id = "plane_view";
    planeView.classList.add("hidden");
    planeView.style.display = "none";
    planeView.innerHTML = `
      <div class="row">
        <button id="back_to_list">← Back</button>
        <span class="muted" id="plane_status"></span>
      </div>

      <div style="display:flex; gap:16px; margin-top:12px; align-items:flex-start; flex-wrap:wrap;">
        <div style="flex:0 0 420px; max-width:420px; width:100%;">
          <img
            id="plane_img"
            src="/static/planes/_default.png"
            alt="Plane image"
            style="width:100%; height:auto; border-radius:14px; border:1px solid rgba(17,24,39,0.10); box-shadow:0 10px 30px rgba(0,0,0,0.08);"
          />
        </div>
        <div style="flex:1 1 320px; min-width:260px;">
          <h2 id="plane_title" style="margin:0 0 8px;"></h2>
          <table>
            <tbody id="plane_detail_rows"></tbody>
          </table>
        </div>
      </div>
    `;
    panel.appendChild(planeView);
  }

  if (!flightView) {
    flightView = document.createElement("div");
    flightView.id = "flight_view";
    flightView.classList.add("hidden");
    flightView.style.display = "none";
    flightView.innerHTML = `
      <div class="row">
        <button id="back_to_list_flight">← Back</button>
        <span class="muted" id="flight_status"></span>
      </div>

	      <div style="display:flex; gap:16px; margin-top:12px; align-items:flex-start; flex-wrap:wrap;">
	        <div id="flight_media_col" style="flex:0 0 420px; max-width:420px; width:100%;">
	          <img
	            id="flight_img"
	            src="/static/planes/_default.png"
	            alt="Flight image"
	            style="width:100%; height:auto; border-radius:14px; border:1px solid rgba(17,24,39,0.10); box-shadow:0 10px 30px rgba(0,0,0,0.08);"
	          />
          <div id="flight_time_ref" class="muted" style="margin-top:8px;"></div>
          <div id="flight_progress" class="flight-progress" style="margin-top:8px;">
            <div id="flight_progress_bar" class="flight-progress-bar"></div>
          </div>
          <div id="flight_progress_label" class="muted" style="margin-top:6px;"></div>
        </div>
        <div style="flex:1 1 320px; min-width:260px;">
          <h2 id="flight_title" style="margin:0 0 8px;"></h2>
	          <div id="flight_completed_banner" class="flight-completed-banner hidden">
	            <div class="flight-completed-check">✓</div>
	            <div class="flight-completed-text">
	              The flight has been completed. Thank you for choosing LIAG airport.
	            </div>
	          </div>
	          <table id="flight_detail_table">
	            <tbody id="flight_detail_rows"></tbody>
	          </table>
	        </div>
	      </div>
    `;
    panel.appendChild(flightView);
  }

  const backBtn = $("back_to_list");
  if (backBtn) {
    backBtn.onclick = () => {
      location.hash = "";
    };
  }

  const backBtnFlight = $("back_to_list_flight");
  if (backBtnFlight) {
    backBtnFlight.onclick = () => {
      location.hash = "";
    };
  }

  const planeRows = $("plane_rows");
  if (planeRows) {
    planeRows.addEventListener("click", (e) => {
      const tr = e.target.closest("tr");
      if (!tr) return;
      const id = tr.dataset.planeId;
      if (!id) return;
      dbg("plane row clicked", { id });
      location.hash = `#plane/${encodeURIComponent(id)}`;
    });
  }

  const flightRows = $("rows");
  if (flightRows) {
    flightRows.addEventListener("click", (e) => {
      const tr = e.target.closest("tr");
      if (!tr) return;
      const id = tr.dataset.flightId;
      if (!id) return;
      dbg("flight row clicked", { id });
      location.hash = `#flight/${encodeURIComponent(id)}`;
    });
  }

  window.addEventListener("hashchange", () => route().catch(() => {}));
  planeViewsReady = true;
  dbg("plane views ready", {
    hasListView: Boolean($("list_view")),
    hasPlaneView: Boolean($("plane_view")),
    hasPlaneRows: Boolean($("plane_rows")),
    hasFlightView: Boolean($("flight_view")),
    hasFlightRows: Boolean($("rows")),
  });
  setPlaneDebug(`plane view ready\nhash=${location.hash}\nplaneById=${planeById.size}`);
  setFlightDebug(`flight view ready\nhash=${location.hash}\nflightById=${flightById.size}`);
}

function showListView() {
  ensurePlaneViews();
  const lv = $("list_view");
  const pv = $("plane_view");
  const fv = $("flight_view");
  setVisible(lv, true);
  setVisible(pv, false);
  setVisible(fv, false);
}

function showPlaneView() {
  ensurePlaneViews();
  const lv = $("list_view");
  const pv = $("plane_view");
  setVisible(lv, false);
  setVisible(pv, true);
  setVisible($("flight_view"), false);
}

function showFlightView() {
  ensurePlaneViews();
  setVisible($("list_view"), false);
  setVisible($("plane_view"), false);
  setVisible($("flight_view"), true);
}

function kvRow(k, v) {
  return `<tr><td class="muted" style="width:160px;">${esc(k)}</td><td>${esc(v ?? "")}</td></tr>`;
}

function renderPlaneDetail(p) {
  $("plane_title").textContent = p.model ? `${p.model}` : "Plane";
  $("plane_status").textContent = p.status ? `Status: ${p.status}` : "";

  const img = $("plane_img");
  if (img) {
    img.onerror = () => {
      img.onerror = null;
      img.src = "/static/planes/_default.png";
    };
    img.src = planeImageUrlForModel(p.model);
  }

  const pos = p.position ? fmtVec3(p.position) : "";
  const route =
    p.route_source && p.route_destination
      ? `${p.route_source} → ${p.route_destination}`
      : "";

  const rows = [
    ["ID", p.id],
    ["Status", p.status],
    ["Model", p.model],
    ["Type", p.type],
    ["Range", p.range],
    ["Speed", p.speed],
    ["Position", pos],
    ["Stand", p.stand_id],
    ["Stand status", p.stand_status],
    ["Route", route],
  ]
    .map(([k, v]) => kvRow(k, v))
    .join("");

  $("plane_detail_rows").innerHTML = rows || kvRow("Info", "No data");

  dbg("renderPlaneDetail", { id: p.id, keys: Object.keys(p || {}) });
}

function renderFlightDetail(f) {
  const routeTitle = f.origin && f.destination ? `${f.origin} → ${f.destination}` : "Flight";
  $("flight_title").textContent = routeTitle;
  $("flight_status").textContent = f.status ? `Status: ${f.status}` : "";

  const airport = $("airport") ? $("airport").value.trim() : "";
  const isDep = airport && f.origin === airport;
  const mainTime = isDep ? f.departure_time : f.arrival_time || f.departure_time;
  const dt = toDate(mainTime);
  const whenLabel = dt ? `${isDep ? "DEP" : "ARR"} ${dt.toLocaleTimeString()}` : "";

  const depText = fmtLocalTimeFromIso(f.departure_time);
  const arrText = fmtLocalTimeFromIso(f.arrival_time);
  const timeRef = $("flight_time_ref");
  if (timeRef) {
    timeRef.textContent = `DEP ${depText || "—"}  ·  ARR ${arrText || "—"}`;
  }

  const nowMs = simNowMs != null ? Number(simNowMs) : Date.now();
  const depMs = parseDateMs(f.departure_time);
  const arrMs = parseDateMs(f.arrival_time);
  const progressEl = $("flight_progress");
  const barEl = $("flight_progress_bar");
  const labelEl = $("flight_progress_label");
  if (progressEl && barEl) {
    progressEl.classList.remove("indeterminate");

    let label = "";
    if (depMs != null && arrMs != null && arrMs > depMs) {
      const pct = Math.max(0, Math.min(1, (nowMs - depMs) / (arrMs - depMs))) * 100;
      barEl.style.width = `${pct.toFixed(1)}%`;
      label = `Progress: ${pct.toFixed(0)}%`;
    } else if (depMs != null && nowMs < depMs) {
      barEl.style.width = "0%";
      label = "Progress: not departed yet";
    } else {
      progressEl.classList.add("indeterminate");
      barEl.style.width = "30%";
      label = "Progress: in progress";
    }

    if (labelEl) labelEl.textContent = label;
  }

  const rows = [
    ["ID", f.id],
    ["ICAO", f.icao],
    ["When", whenLabel],
    ["Origin", f.origin],
    ["Destination", f.destination],
    ["Departure", f.departure_time],
    ["Arrival", f.arrival_time],
    ["Type", f.tipo],
    ["Status", f.status],
    ["Airplane", f.airplane_id],
  ]
    .map(([k, v]) => kvRow(k, v))
    .join("");

  $("flight_detail_rows").innerHTML = rows || kvRow("Info", "No data");
  setFlightDebug(
    DEBUG_PLANE_PAGE
      ? `hash=${location.hash}\nflightById=${flightById.size}\n\n${JSON.stringify(f, null, 2)}`
      : "",
  );

  dbg("renderFlightDetail", { id: flightIdForRow(f), keys: Object.keys(f || {}) });
}

function setFlightImageForModel(model) {
  const img = $("flight_img");
  if (!img) return;
  img.onerror = () => {
    img.onerror = null;
    img.src = "/static/planes/_default.png";
  };
  img.src = planeImageUrlForModel(model);
}

async function fetchPlanesAndCache() {
  const params = new URLSearchParams();
  if (simNowMs != null) params.set("now_unix_ms", String(simNowMs));
  const res = await fetch(`/api/planes?${params.toString()}`);
  const data = await res.json();
  const map = new Map();
  for (const p of data.planes || []) {
    if (p && p.id != null) map.set(String(p.id), p);
  }
  planeById = map;
  dbg("fetchPlanesAndCache", { count: (data.planes || []).length, cached: planeById.size });
  return data.planes || [];
}

async function fetchWindowAndCache() {
  const airport = $("airport") ? $("airport").value.trim() : "LIAG";
  const windowMin = Number(($("window") && $("window").value) || "60");
  const params = new URLSearchParams({
    airport: airport,
    window_minutes: String(windowMin),
  });
  if (simNowMs != null) params.set("now_unix_ms", String(simNowMs));

  const res = await fetch(`/api/window?${params.toString()}`);
  const data = await res.json();

  const map = new Map();
  for (const f of data.flights || []) {
    const id = flightIdForRow(f);
    if (id) map.set(String(id), f);
  }
  flightById = map;
  dbg("fetchWindowAndCache", { count: (data.flights || []).length, cached: flightById.size });
  return data.flights || [];
}

async function fetchFlightById(flightId) {
  const res = await fetch(`/api/flight/${encodeURIComponent(String(flightId))}`);
  if (!res.ok) return null;
  return await res.json();
}

function setCompletedBannerVisible(visible) {
  const el = $("flight_completed_banner");
  if (!el) return;
  el.classList.toggle("hidden", !visible);
}

function setFlightDataVisible(visible) {
  const ids = [
    "flight_media_col",
    "flight_title",
    "flight_status",
    "flight_time_ref",
    "flight_progress",
    "flight_progress_label",
    "flight_detail_table",
  ];
  for (const id of ids) {
    const el = $(id);
    if (!el) continue;
    el.classList.toggle("hidden", !visible);
  }
}

function clearFlightDetailUI() {
  const rows = $("flight_detail_rows");
  if (rows) rows.innerHTML = "";
  const timeRef = $("flight_time_ref");
  if (timeRef) timeRef.textContent = "";
  const barEl = $("flight_progress_bar");
  if (barEl) barEl.style.width = "0%";
  const labelEl = $("flight_progress_label");
  if (labelEl) labelEl.textContent = "";
  setFlightDebug("");
}

async function route() {
  try {
    ensurePlaneViews();
    const mPlane = location.hash.match(/^#plane\/(.+)$/);
    const mFlight = location.hash.match(/^#flight\/(.+)$/);
    if (!mPlane && !mFlight) {
      showListView();
      setPlaneDebug("");
      setFlightDebug("");
      return;
    }

    if (mPlane) {
      const id = decodeURIComponent(mPlane[1]);
      dbg("route: plane", { id, hash: location.hash, cached: planeById.size });
      setPlaneDebug(`routing...\nhash=${location.hash}\nrequested=${id}\nplaneById=${planeById.size}`);
      showPlaneView();

      let p = planeById.get(String(id)) || null;
      if (!p) {
        setPlaneDebug(
          `routing...\nhash=${location.hash}\nrequested=${id}\nplaneById=${planeById.size}\n\ncache miss -> refetching /api/planes`,
        );
        await fetchPlanesAndCache();
        p = planeById.get(String(id)) || null;
      }

      if (!p) {
        $("plane_title").textContent = `Plane ${id}`;
        $("plane_status").textContent = "";
        $("plane_detail_rows").innerHTML = kvRow("Error", "Plane not found");
        setPlaneDebug(
          `hash=${location.hash}\nrequested=${id}\nplaneById=${planeById.size}\n\nPlane not found in cache.`,
        );
        dbg("route: plane not found", { id, cached: planeById.size });
        return;
      }

      renderPlaneDetail(p);
      showPlaneView();
      return;
    }

    const id = decodeURIComponent(mFlight[1]);
    dbg("route: flight", { id, hash: location.hash, cached: flightById.size });
    setFlightDebug(`routing...\nhash=${location.hash}\nrequested=${id}\nflightById=${flightById.size}`);
    showFlightView();

    // Default: normal view (banner hidden, details visible).
    setCompletedBannerVisible(false);
    setFlightDataVisible(true);

    // Once a flight is completed, stop fetching and only show the banner.
    if (completedFlightIds.has(String(id))) {
      const titleEl = $("flight_title");
      if (titleEl) titleEl.textContent = "";
      const statusEl = $("flight_status");
      if (statusEl) statusEl.textContent = "";
      clearFlightDetailUI();
      setFlightDataVisible(false);
      setCompletedBannerVisible(true);
      return;
    }

    let f = flightById.get(String(id)) || null;
    if (!f) {
      setFlightDebug(
        `routing...\nhash=${location.hash}\nrequested=${id}\nflightById=${flightById.size}\n\ncache miss -> fetching /api/flight/${id}`,
      );
      f = await fetchFlightById(id);
      if (f && flightIdForRow(f)) flightById.set(String(flightIdForRow(f)), f);
    }

    if (!f) {
      $("flight_title").textContent = `Flight`;
      $("flight_status").textContent = "";
      $("flight_detail_rows").innerHTML = kvRow("Error", "Flight not found");
      setFlightDebug(
        `hash=${location.hash}\nrequested=${id}\nflightById=${flightById.size}\n\nFlight not found in cache.`,
      );
      dbg("route: flight not found", { id, cached: flightById.size });
      return;
    }

    if (String(f.status || "") === "Completed") {
      completedFlightIds.add(String(id));
      const titleEl = $("flight_title");
      if (titleEl) titleEl.textContent = "";
      const statusEl = $("flight_status");
      if (statusEl) statusEl.textContent = "";
      clearFlightDetailUI();
      setFlightDataVisible(false);
      setCompletedBannerVisible(true);
      return;
    }

    // If a flight is assigned to a plane, show the plane's model image (same convention as plane page).
    let planeModel = null;
    if (f.airplane_id) {
      const cachedPlane = planeById.get(String(f.airplane_id)) || null;
      planeModel = cachedPlane ? cachedPlane.model : null;
      if (!planeModel) {
        await fetchPlanesAndCache();
        const fetchedPlane = planeById.get(String(f.airplane_id)) || null;
        planeModel = fetchedPlane ? fetchedPlane.model : null;
      }
    }
    setFlightImageForModel(planeModel);

    renderFlightDetail(f);
    showFlightView();
  } catch (err) {
    try {
      // eslint-disable-next-line no-console
      console.error("[dashboard] route error", err);
    } catch {}
    if (location.hash.startsWith("#flight/")) {
      showFlightView();
      setFlightDebug(`route error:\n${String(err && err.stack ? err.stack : err)}`);
    } else {
      showPlaneView();
      setPlaneDebug(`route error:\n${String(err && err.stack ? err.stack : err)}`);
    }
  }
}

async function refreshWindow() {
  const airport = $("airport").value.trim();
  const windowMin = Number($("window").value || "60");
  const params = new URLSearchParams({
    airport: airport,
    window_minutes: String(windowMin),
  });
  if (simNowMs != null) params.set("now_unix_ms", String(simNowMs));

  const res = await fetch(`/api/window?${params.toString()}`);
  const data = await res.json();

  if (simNowMs == null && data && data.now) {
    const parsed = Date.parse(data.now);
    if (!Number.isNaN(parsed)) simNowMs = parsed;
  }

  const rows = data.flights
    .map((f) => {
      const flightId = flightIdForRow(f);
      const w = fmtWhen(f);
      const dt = toDate(w.t);
      const delta = dt ? minsUntil(dt) : "";
      const route = `${esc(f.origin)} → ${esc(f.destination)}`;
      const flightCode = esc(f.icao || f.id);
      const whenCell = dt ? `${w.label} ${dt.toLocaleTimeString()}` : "";
      return `
	          <tr class="flight-row" data-flight-id="${esc(flightId)}" style="cursor:pointer;">
	            <td>${whenCell}</td>
	            <td>${delta}</td>
	            <td>${flightCode}</td>
	            <td>${route}</td>
	            <td>${esc(f.tipo || "")}</td>
	            <td><span class="pill ${statusClass(f.status)}">${esc(f.status || "")}</span></td>
	            <td class="muted">${esc(f.airplane_id || "")}</td>
	          </tr>
	        `;
    })
    .join("");

  $("rows").innerHTML =
    rows || `<tr><td colspan="7" class="muted">No flights found.</td></tr>`;

  const map = new Map();
  for (const f of data.flights || []) {
    const id = flightIdForRow(f);
    if (id) map.set(String(id), f);
  }
  flightById = map;
  dbg("refreshWindow cached", { cached: flightById.size });

  if (location.hash.startsWith("#flight/")) route().catch(() => {});
}

async function refreshPlanes() {
  const params = new URLSearchParams();
  if (simNowMs != null) params.set("now_unix_ms", String(simNowMs));
  const res = await fetch(`/api/planes?${params.toString()}`);
  const data = await res.json();

  const map = new Map();
  for (const p of data.planes || []) {
    if (p && p.id != null) map.set(String(p.id), p);
  }
  planeById = map;
  dbg("refreshPlanes cached", { cached: planeById.size });

  const rows = (data.planes || [])
    .map((p) => {
      const route =
        p.route_source && p.route_destination
          ? `${esc(p.route_source)} → ${esc(p.route_destination)}`
          : "";
      const stand = p.stand_id ? esc(p.stand_id) : "";
      const speed = p.speed == null ? "" : Number(p.speed).toFixed(2);
      return `
	          <tr class="plane-row" data-plane-id="${esc(p.id || "")}" style="cursor:pointer;">
	            <td>${esc(p.id || "")}</td>
	            <td><span class="pill ${statusClass(p.status)}">${esc(p.status || "")}</span></td>
	            <td class="muted">${esc(p.model || "")}</td>
	            <td>${esc(p.type || "")}</td>
	            <td>${esc(p.range || "")}</td>
	            <td class="muted">${esc(speed)}</td>
	            <td class="muted">${stand}</td>
	            <td class="muted" title="${route}">${route}</td>
	          </tr>
	        `;
    })
    .join("");

  $("plane_rows").innerHTML =
    rows || `<tr><td colspan="8" class="muted">No planes found.</td></tr>`;

  if (location.hash.startsWith("#plane/")) route().catch(() => {});
}

let refreshTimer = null;
function scheduleRefreshSoon() {
  if (refreshTimer) return;
  refreshTimer = setTimeout(async () => {
    refreshTimer = null;
    try {
      await Promise.all([refreshWindow(), refreshPlanes()]);
    } catch (e) {}
  }, 200);
}

const ALLOWED_LEVELS = new Set(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]);

function shortTime(iso) {
  try {
    return new Date(iso).toLocaleTimeString();
  } catch {
    return "";
  }
}

function normalizeEvent(obj) {
  const evt =
    obj && typeof obj === "object" ? obj : { type: "raw", message: String(obj ?? "") };
  const levelRaw = String(evt.level || evt.type || "INFO").toUpperCase();
  const level = ALLOWED_LEVELS.has(levelRaw) ? levelRaw : "INFO";
  const ts = evt.sim_ts || evt.ts || null;
  const subsystem = evt.subsystem || evt.logger || "";
  const message = evt.message || "";
  const fields = evt.fields && typeof evt.fields === "object" ? evt.fields : null;
  return { level, ts, subsystem, message, fields };
}

function renderEvent(obj) {
  const box = $("events");
  const { level, ts, subsystem, message, fields } = normalizeEvent(obj);
  const fieldsText = fields ? JSON.stringify(fields) : "";

  const line = document.createElement("div");
  line.className = `logline lvl-${level}`;
  line.innerHTML = `
	      <div class="ts">${esc(ts ? shortTime(ts) : "")}</div>
	      <div class="lvl">${esc(level)}</div>
	      <div class="sub" title="${esc(subsystem)}">${esc(subsystem)}</div>
	      <div class="msg" title="${esc(message)}">${esc(message)}</div>
	      <div class="fields" title="${esc(fieldsText)}">${esc(fieldsText)}</div>
	    `;
  box.appendChild(line);
  while (box.childNodes.length > 200) box.removeChild(box.firstChild);
  box.scrollTop = box.scrollHeight;
}

function connectEvents() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws/events?tail=50`);

  ws.onopen = () => {
    $("status").textContent = "connected";
  };
  ws.onclose = () => {
    $("status").textContent = "disconnected (retrying…)";
    setTimeout(connectEvents, 1000);
  };
  ws.onerror = () => {
    $("status").textContent = "error";
  };

  ws.onmessage = (ev) => {
    try {
      const obj = JSON.parse(ev.data);
      const kind = obj ? obj.type || obj.event : null;
      if (kind === "clock") {
        const ms =
          typeof obj.sim_unix_ms === "number" ? obj.sim_unix_ms : Number(obj.sim_unix_ms);
        if (Number.isFinite(ms)) simNowMs = ms;
        const scale =
          typeof obj.time_scale === "number" ? obj.time_scale : Number(obj.time_scale);
        if (Number.isFinite(scale)) simTimeScale = scale;
        scheduleRefreshSoon();
        return;
      }
      renderEvent(obj);
    } catch {
      renderEvent({ type: "raw", message: ev.data });
    }
    scheduleRefreshSoon();
  };
}

$("refresh").onclick = () => refreshWindow();
setInterval(() => refreshWindow().catch(() => {}), 10000);
setInterval(() => refreshPlanes().catch(() => {}), 2000);

refreshWindow().catch(() => {});
refreshPlanes().catch(() => {});
connectEvents();
ensurePlaneViews();
route().catch(() => {});
