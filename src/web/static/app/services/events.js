import { normalizeEvent } from "../lib/format.js";

function refreshForBackendEvent(refresh, eventName) {
  switch (eventName) {
    case "departure_assigned":
    case "landing_plane_assigned":
    case "landing_departed":
    case "departure_started":
      refresh.scheduleWindowRefreshSoon();
      refresh.schedulePlanesRefreshSoon();
      return;

    case "landing_stand_reserved":
    case "landing_spawn":
    case "landing_approach_started":
    case "departure_completed":
    case "landing_completed":
    case "plane_left_stand":
    case "disembark_complete":
    case "initial_spawns_scheduled":
      refresh.schedulePlanesRefreshSoon();
      refresh.scheduleWindowRefreshSoon();
      return;

    default:
      refresh.scheduleAllRefreshSoon();
  }
}

export function createEventService(store, refresh) {
  function connect() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${location.host}/ws/events?tail=50`);

    ws.onopen = () => {
      console.log("[events-ws] connected");
      store.setConnectionStatus("connected");
      refresh.scheduleAllRefreshSoon(0);
    };

    ws.onclose = () => {
      console.warn("[events-ws] disconnected");
      store.setConnectionStatus("disconnected (retrying...)");
      setTimeout(connect, 1000);
    };

    ws.onerror = (err) => {
      console.error("[event-ws] error", err);
      store.setConnectionStatus("error");
    };

    ws.onmessage = (ev) => {
      try {
        const obj = JSON.parse(ev.data);
        const kind = obj ? obj.type || obj.event : null;

        if (kind === "clock") {
          const previousTimeScale = Number(store.getState().sim.timeScale);
          const nowMs =
            typeof obj.sim_unix_ms === "number" ? obj.sim_unix_ms : Number(obj.sim_unix_ms);
          const timeScale =
            typeof obj.time_scale === "number" ? obj.time_scale : Number(obj.time_scale);
          const syncId =
            typeof obj.sync_id === "number" ? obj.sync_id : Number(obj.sync_id);
          
          console.log("[clock_sync][WEB<-PY]", {
            syncId,
            nowMs,
            timeScale,
            iso: Number.isFinite(nowMs) ? new Date(nowMs).toISOString() : null,
            raw: obj,
          });

          store.setSimClock(nowMs, timeScale);
          refresh.handleClockSync({
            previousTimeScale: Number.isFinite(previousTimeScale) ? previousTimeScale : null,
            nextTimeScale: Number.isFinite(timeScale) ? timeScale : null,
          });
          return;
        }

        if (kind === "backend_event") {
          store.addLog(normalizeEvent(obj));
          refreshForBackendEvent(refresh, obj.event);
          return;
        }

        store.addLog(normalizeEvent(obj));
      } catch {
        store.addLog(normalizeEvent({ type: "raw", message: ev.data }));
      }
    };
  }

  return { connect };
}
