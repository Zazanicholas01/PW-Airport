import { createRouter } from "./app/router.js";
import { createStore } from "./app/store.js";
import { createApiService } from "./app/services/api.js";
import { createEventService } from "./app/services/events.js";
import { createRefreshService } from "./app/services/refresh.js";

function boot() {
  const mount = document.getElementById("app");
  if (!mount) {
    throw new Error("Missing #app mount point");
  }

  const store = createStore({
    route: { name: "overview", params: {}, canonicalHash: "#/overview" },
    connection: { status: "connecting" },
    sim: { nowMs: null, timeScale: null, receivedAtMs: null },
    data: {
      flightsById: new Map(),
      planesById: new Map(),
      standsById: new Map(),
      pathsById: new Map(),
    },
    ui: {
      airport: "LIAG",
      windowMinutes: 60,
    },
    logs: [],
  });

  const api = createApiService(store);
  const refresh = createRefreshService(store, api);
  const events = createEventService(store, refresh.scheduleRefreshSoon);
  const router = createRouter(mount, store, { api, refresh, events });

  refresh.start();
  events.connect();
  router.start();
}

boot();
