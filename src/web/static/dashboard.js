import { createRouter } from "./app/router.js";
import { createStore } from "./app/store.js";
import { createApiService } from "./app/services/api.js";
import { createEventService } from "./app/services/events.js";
import { createRefreshService } from "./app/services/refresh.js";
import { createSimClockService } from "./app/services/sim-clock.js";

function boot() {
  const mount = document.getElementById("app");
  if (!mount) {
    throw new Error("Missing #app mount point");
  }

  const store = createStore({
    route: { name: "schedule", params: {}, canonicalHash: "#/schedule" },
    connection: { status: "starting" },
    sim: { anchorSimMs: null, anchorClientMs: null, nowMs: null, timeScale: null },
    dashboard: {
      clock: null,
      window: {
        airport: "LIAG",
        window_minutes: 60,
        count: 0,
        active_count: 0,
        allocated_planes_count: 0,
        timeline_markers: [],
      },
      flights: [],
      planes: [],
      flightsById: new Map(),
      planesById: new Map(),
    },
    ui: {
      airport: "LIAG",
      windowMinutes: 60,
    },
    logs: [],
  });

  const api = createApiService(store);
  const simClock = createSimClockService(store);
  const refresh = createRefreshService(store, api, simClock);
  const events = createEventService(store, refresh, simClock);
  const router = createRouter(mount, store, { api, refresh, events });

  refresh.start();
  router.start();
}

boot();
