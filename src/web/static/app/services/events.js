import { normalizeEvent } from "../lib/format.js";

export function createEventService(store, scheduleRefreshSoon) {
  function connect() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${location.host}/ws/events?tail=50`);

    ws.onopen = () => {
      console.log("[events-ws] connected");
      store.setConnectionStatus("connected");
    };

    ws.onclose = () => {
      console.warn("[events-ws] disconnected");
      store.setConnectionStatus("disconnected (retrying...)");
      setTimeout(connect, 1000);
    };

    ws.onerror = () => {
      console.error("[event-ws] error", err);
      store.setConnectionStatus("error");
    };

    ws.onmessage = (ev) => {
      try {
        const obj = JSON.parse(ev.data);
        const kind = obj ? obj.type || obj.event : null;

        if (kind === "clock") {
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
          scheduleRefreshSoon();
          return;
        }
        store.addLog(normalizeEvent(obj));
      } catch {
        store.addLog(normalizeEvent({ type: "raw", message: ev.data }));
      }
      scheduleRefreshSoon();
    };
  }

  return { connect };
}
