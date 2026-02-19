# src/web/dashboard_app.py
import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse

from src.db.db_functions import list_flights_in_sliding_window
from src.utils.event_log import log_dir

app = FastAPI()

EVENTS_FILE = Path(log_dir()) / "events.jsonl"
BACKGROUND_IMAGE = Path(__file__).with_name("background-airport.png")

HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>PW Airport - Scheduling Window</title>
  <style>
    body {
      font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto;
      margin: 0;
      background: url('/background-airport.png') no-repeat center center fixed;
      background-size: cover;
      color: #0b1220;
      position: relative;
    }
    body::before {
      content: "";
      position: fixed;
      inset: 0;
      background: rgba(0, 0, 0, 0.38);
      pointer-events: none;
      z-index: 0;
    }
    .shell {
      min-height: 100vh;
      padding: 16px;
      background: transparent;
      position: relative;
      z-index: 1;
    }
    .panel {
      max-width: 1200px;
      margin: 0 auto;
      padding: 14px 14px 16px;
      border-radius: 14px;
      background: rgba(255, 255, 255, 0.80);
      border: 1px solid rgba(17, 24, 39, 0.10);
      box-shadow: 0 10px 30px rgba(0, 0, 0, 0.08);
    }
    .row { display:flex; gap:12px; align-items:center; flex-wrap:wrap; }
    input { padding: 6px 8px; }
    button { padding: 6px 10px; cursor:pointer; }
    table { border-collapse: collapse; width: 100%; margin-top: 12px; }
    th, td { border-bottom: 1px solid #eee; padding: 8px; text-align: left; font-size: 14px; }
    tr:hover { background: #fafafa; }
    .pill { padding: 2px 8px; border-radius: 999px; font-size: 12px; background: #f3f4f6; display:inline-block; }
    .muted { color:#6b7280; }
    #events { margin-top: 8px; border: 1px solid #111827; border-radius: 10px; overflow: hidden; }
    .logline { display:flex; gap:10px; padding:6px 10px; font: 12px ui-monospace, SFMono-Regular, Menlo, monospace; border-top: 1px solid #0f172a; background:#0b1020; color:#d1d5db; }
    .logline:first-child { border-top: 0; }
    .logline .ts { color:#93c5fd; width: 92px; flex: 0 0 auto; }
    .logline .lvl { width: 64px; flex: 0 0 auto; }
    .logline .sub { color:#a7f3d0; width: 140px; flex: 0 0 auto; overflow:hidden; text-overflow: ellipsis; white-space: nowrap; }
    .logline .msg { flex: 1 1 auto; overflow:hidden; text-overflow: ellipsis; white-space: nowrap; }
    .logline .fields { color:#9ca3af; white-space: nowrap; flex: 0 0 auto; max-width: 40%; overflow:hidden; text-overflow: ellipsis; }
    .lvl-DEBUG .lvl { color:#c4b5fd; }
    .lvl-INFO .lvl { color:#93c5fd; }
    .lvl-WARNING .lvl { color:#fbbf24; }
    .lvl-ERROR .lvl, .lvl-CRITICAL .lvl { color:#fb7185; }
  </style>
</head>
<body>
  <div class="shell">
  <div class="panel">
  <div class="row">
    <h2 style="margin:0;">Scheduling Window</h2>
    <span class="muted" id="status">connecting…</span>
  </div>

  <div class="row" style="margin-top:10px;">
    <label>Airport <input id="airport" value="LIAG" size="6"/></label>
    <label>Window (min) <input id="window" value="60" size="4"/></label>
    <button id="refresh">Refresh</button>
    <span class="muted">Auto-refresh on events + every 10s</span>
  </div>

  <table>
    <thead>
      <tr>
        <th>When</th>
        <th>Δ min</th>
        <th>Flight</th>
        <th>Route</th>
        <th>Type</th>
        <th>Status</th>
        <th>Airplane</th>
      </tr>
    </thead>
    <tbody id="rows"></tbody>
  </table>

  <h3 style="margin-top:18px;">Planes</h3>
  <table>
    <thead>
      <tr>
        <th>Airplane</th>
        <th>Status</th>
        <th>Model</th>
        <th>Type</th>
        <th>Range</th>
        <th>Speed</th>
        <th>Position</th>
        <th>Stand</th>
        <th>Route</th>
      </tr>
    </thead>
    <tbody id="plane_rows"></tbody>
  </table>

  <h3 style="margin-top:18px;">Live events</h3>
  <div id="events" style="height:180px; overflow:auto;"></div>

<script>
  const $ = (id) => document.getElementById(id);

  let simNowMs = null;
  let simTimeScale = null;

  function toDate(s) { return s ? new Date(s) : null; }
  function minsUntil(dt) {
    const base = simNowMs ? new Date(simNowMs) : new Date();
    return Math.round((dt - base) / 60000);
  }

  function fmtWhen(f) {
    const airport = $("airport").value.trim();
    const isDep = f.origin === airport;
    const t = isDep ? f.departure_time : (f.arrival_time || f.departure_time);
    return { t, label: isDep ? "DEP" : "ARR" };
  }

  function esc(s) {
    return String(s ?? "")
      .replaceAll("&","&amp;")
      .replaceAll("<","&lt;")
      .replaceAll(">","&gt;")
      .replaceAll('"',"&quot;")
      .replaceAll("'","&#39;");
  }

  function fmtVec3(pos) {
    if (!pos || typeof pos !== "object") return "";
    const x = Number(pos.x), y = Number(pos.y), z = Number(pos.z);
    if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(z)) return "";
    return `${x.toFixed(1)}, ${y.toFixed(1)}, ${z.toFixed(1)}`;
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
      .map(f => {
        const w = fmtWhen(f);
        const dt = toDate(w.t);
        const delta = dt ? minsUntil(dt) : "";
        const route = `${esc(f.origin)} → ${esc(f.destination)}`;
        const flightCode = esc(f.icao || f.id);
        const whenCell = dt ? `${w.label} ${dt.toLocaleTimeString()}` : "";
        return `
          <tr>
            <td>${whenCell}</td>
            <td>${delta}</td>
            <td>${flightCode}</td>
            <td>${route}</td>
            <td>${esc(f.tipo || "")}</td>
            <td><span class="pill">${esc(f.status || "")}</span></td>
            <td class="muted">${esc(f.airplane_id || "")}</td>
          </tr>
        `;
      })
      .join("");

    $("rows").innerHTML = rows || `<tr><td colspan="7" class="muted">No flights found.</td></tr>`;
  }

  async function refreshPlanes() {
    const params = new URLSearchParams();
    if (simNowMs != null) params.set("now_unix_ms", String(simNowMs));
    const res = await fetch(`/api/planes?${params.toString()}`);
    const data = await res.json();

    const rows = (data.planes || [])
      .map(p => {
        const pos = fmtVec3(p.position);
        const route = (p.route_source && p.route_destination) ? `${esc(p.route_source)} → ${esc(p.route_destination)}` : "";
        const stand = p.stand_id ? esc(p.stand_id) : "";
        const speed = (p.speed == null) ? "" : Number(p.speed).toFixed(2);
        return `
          <tr>
            <td>${esc(p.id || "")}</td>
            <td><span class="pill">${esc(p.status || "")}</span></td>
            <td class="muted">${esc(p.model || "")}</td>
            <td>${esc(p.type || "")}</td>
            <td>${esc(p.range || "")}</td>
            <td class="muted">${esc(speed)}</td>
            <td class="muted" title="${esc(pos)}">${esc(pos)}</td>
            <td class="muted">${stand}</td>
            <td class="muted" title="${route}">${route}</td>
          </tr>
        `;
      })
      .join("");

    $("plane_rows").innerHTML = rows || `<tr><td colspan="9" class="muted">No planes found.</td></tr>`;
  }

  let refreshTimer = null;
  function scheduleRefreshSoon() {
    if (refreshTimer) return;
    refreshTimer = setTimeout(async () => {
      refreshTimer = null;
      try { await Promise.all([refreshWindow(), refreshPlanes()]); } catch (e) {}
    }, 200);
  }

  const ALLOWED_LEVELS = new Set(["DEBUG","INFO","WARNING","ERROR","CRITICAL"]);

  function shortTime(iso) {
    try { return new Date(iso).toLocaleTimeString(); } catch { return ""; }
  }

  function normalizeEvent(obj) {
    const evt = (obj && typeof obj === "object") ? obj : { type: "raw", message: String(obj ?? "") };
    const levelRaw = String(evt.level || evt.type || "INFO").toUpperCase();
    const level = ALLOWED_LEVELS.has(levelRaw) ? levelRaw : "INFO";
    const ts = evt.sim_ts || evt.ts || null;
    const subsystem = evt.subsystem || evt.logger || "";
    const message = evt.message || "";
    const fields = (evt.fields && typeof evt.fields === "object") ? evt.fields : null;
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
    const proto = (location.protocol === "https:") ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${location.host}/ws/events?tail=50`);

    ws.onopen = () => { $("status").textContent = "connected"; };
    ws.onclose = () => { $("status").textContent = "disconnected (retrying…)"; setTimeout(connectEvents, 1000); };
    ws.onerror = () => { $("status").textContent = "error"; };

    ws.onmessage = (ev) => {
      try {
        const obj = JSON.parse(ev.data);
        const kind = obj ? (obj.type || obj.event) : null;
        if (kind === "clock") {
          const ms = (typeof obj.sim_unix_ms === "number") ? obj.sim_unix_ms : Number(obj.sim_unix_ms);
          if (Number.isFinite(ms)) simNowMs = ms;
          const scale = (typeof obj.time_scale === "number") ? obj.time_scale : Number(obj.time_scale);
          if (Number.isFinite(scale)) simTimeScale = scale;
          scheduleRefreshSoon();
          return;
        }
        renderEvent(obj);
      } catch {
        renderEvent({ type:"raw", message: ev.data });
      }
      scheduleRefreshSoon();
    };
  }

  $("refresh").onclick = () => refreshWindow();
  setInterval(() => refreshWindow().catch(()=>{}), 10000);
  setInterval(() => refreshPlanes().catch(()=>{}), 2000);

  refreshWindow().catch(()=>{});
  refreshPlanes().catch(()=>{});
  connectEvents();
</script>
  </div>
  </div>
</body>
</html>
"""

def _to_iso(dt: Any) -> str | None:
    if dt is None:
        return None
    if isinstance(dt, str):
        return dt
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    return str(dt)

def _flight_to_dict(f: Any) -> dict[str, Any]:
    return {
        "id": getattr(f, "id", None),
        "icao": getattr(f, "icao", None),
        "origin": getattr(f, "origin", None),
        "destination": getattr(f, "destination", None),
        "departure_time": _to_iso(getattr(f, "departure_time", None)),
        "arrival_time": _to_iso(getattr(f, "arrival_time", None)),
        "tipo": getattr(f, "tipo", None),
        "status": getattr(f, "status", None),
        "airplane_id": getattr(f, "airplane_id", None),
    }

@app.get("/")
def index() -> HTMLResponse:
    return HTMLResponse(HTML)

@app.get("/background-airport.png")
def background_airport_png() -> FileResponse:
    return FileResponse(BACKGROUND_IMAGE, media_type="image/png")

@app.get("/api/window")
def api_window(
    airport: str = "LIAG", 
    window_minutes: int = 60,
    now_unix_ms: int | None = None) -> dict[str, Any]:
    
    now = (
        datetime.fromtimestamp(now_unix_ms / 1000.0, tz=timezone.utc)
        if now_unix_ms is not None
        else datetime.now(timezone.utc)
        )
    
    flights = list_flights_in_sliding_window(
        airport_icao=airport,
        now_utc=now,
        window=timedelta(minutes=window_minutes),
    )
    # Optional: stable ordering (soonest first)
    def sort_key(f: Any):
        dep = getattr(f, "departure_time", None)
        arr = getattr(f, "arrival_time", None)
        t = dep or arr
        if isinstance(t, datetime) and t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        return t or datetime.max.replace(tzinfo=timezone.utc)
    flights = sorted(flights, key=sort_key)

    return {"now": now.isoformat(), "count": len(flights), "flights": [_flight_to_dict(f) for f in flights]}

from sqlalchemy import select
from src.db.engine import get_engine
from sqlalchemy.orm import sessionmaker
from src.db import models

Engine = get_engine()
Session = sessionmaker(bind=Engine, future=True)

@app.get("/api/planes")
def api_planes(now_unix_ms: int | None = None) -> dict[str, Any]:
    with Session() as session:
        planes = list(session.scalars(select(models.Airplane)).all())
        stands = list(session.scalars(select(models.Stand)).all())
        paths = list(session.scalars(select(models.Path)).all())
    
    stand_by_plane: dict[str, Any] = {
        s.airplane_id: s for s in stands
        if isinstance(getattr(s, "airplane_id", None), str) and s.airplane_id
    }
    path_by_id: dict[int, Any] = {
        p.id: p for p in paths
        if isinstance(getattr(p, "id", None), int)
    }

    def plane_row(p: Any) -> dict[str, Any]:
        pid = getattr(p, "id", None)
        stand = stand_by_plane.get(pid) if isinstance(pid, str) else None
        route_id = getattr(p, "route_id", None)
        path = path_by_id.get(route_id) if isinstance(route_id, int) else None

        return {
            "id": pid,
            "status": getattr(p, "status", None),
            "type": getattr(p, "type", None),
            "range": getattr(p, "range", None),
            "model": getattr(p, "model", None),
            "speed": getattr(p, "speed", None),
            "position": getattr(stand, "position", None),

            "stand_id": getattr(stand, "id", None),
            "stand_status": getattr(stand, "status", None),

            "route_id": route_id,
            "route_source": getattr(path, "source", None),
            "route_destination": getattr(path, "destination", None),
        }

    status_rank = {"Parked": 0, "Disembarking": 1}
    items = sorted(
        (plane_row(p) for p in planes),
        key=lambda x: (status_rank.get(x.get("status"), 99), str(x.get("id") or "")),
    )

    return {"count": len(items), "planes": items}

@app.websocket("/ws/events")
async def ws_events(ws: WebSocket, tail: int = 50) -> None:
    await ws.accept()

    EVENTS_FILE.parent.mkdir(parents=True, exist_ok=True)

    # Send last N lines (best-effort).
    if EVENTS_FILE.exists():
        try:
            lines = EVENTS_FILE.read_text(encoding="utf-8").splitlines()[-max(0, int(tail)):]
            for line in lines:
                if line.strip():
                    await ws.send_text(line)
        except Exception:
            pass

    # Tail from end.
    f = EVENTS_FILE.open("a+", encoding="utf-8")
    f.seek(0, 2)

    try:
        while True:
            line = f.readline()
            if line:
                await ws.send_text(line.rstrip("\n"))
            else:
                await asyncio.sleep(0.25)
    except WebSocketDisconnect:
        return
    finally:
        f.close()
