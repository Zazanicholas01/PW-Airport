import { normalizeEvent } from "../lib/format.js";

export function createEventService(store, scheduleRefreshSoon) {
  function connect() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${location.host}/ws/events?tail=50`);

    ws.onopen = () => {
      store.setConnectionStatus("connected");
    };

    ws.onclose = () => {
      store.setConnectionStatus("disconnected (retrying...)");
      setTimeout(connect, 1000);
    };

    ws.onerror = () => {
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
