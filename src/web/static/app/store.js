export function createStore(initialState) {
  const listeners = new Set();
  const state = {
    route: initialState.route,
    connection: initialState.connection,
    sim: initialState.sim,
    dashboard: initialState.dashboard,
    ui: initialState.ui,
    logs: initialState.logs,
  };

  function notify(type) {
    for (const listener of listeners) listener(type, getState());
  }

  function getState() {
    return state;
  }

  function rebuildIndexes() {
    state.dashboard.flightsById = new Map(
      (state.dashboard.flights || [])
        .map((flight) => [String((flight && (flight.icao || flight.id)) || ""), flight])
        .filter(([id]) => id),
    );
    state.dashboard.planesById = new Map(
      (state.dashboard.planes || [])
        .map((plane) => [String((plane && plane.id) || ""), plane])
        .filter(([id]) => id),
    );
  }

  rebuildIndexes();

  return {
    getState,
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    setRoute(route) {
      state.route = route;
      notify("route");
    },
    setConnectionStatus(status) {
      state.connection = { ...state.connection, status };
      notify("connection");
    },
    setUi(partial) {
      state.ui = { ...state.ui, ...partial };
      notify("ui");
    },
    setDashboardSnapshot(snapshot) {
      state.dashboard = {
        ...state.dashboard,
        clock: snapshot.clock || state.dashboard.clock,
        window: snapshot.window || state.dashboard.window,
        flights: snapshot.flights || [],
        planes: snapshot.planes || [],
      };
      rebuildIndexes();
      notify("dashboard");
    },
    upsertFlight(flight) {
      const id = String((flight && (flight.icao || flight.id)) || "");
      if (!id) return;
      state.dashboard.flightsById.set(id, flight);
      state.dashboard.flights = Array.from(state.dashboard.flightsById.values());
      notify("dashboard");
    },
    setSimAnchor({ anchorSimMs, anchorClientMs, timeScale }) {
      state.sim = {
        ...state.sim,
        anchorSimMs: Number.isFinite(anchorSimMs) ? anchorSimMs : state.sim.anchorSimMs,
        anchorClientMs: Number.isFinite(anchorClientMs) ? anchorClientMs : state.sim.anchorClientMs,
        timeScale: Number.isFinite(timeScale) ? timeScale : state.sim.timeScale,
      };
      notify("sim");
    },
    setDerivedSimNow(nowMs) {
      state.sim = {
        ...state.sim,
        nowMs: Number.isFinite(nowMs) ? nowMs : state.sim.nowMs,
      };
      notify("sim");
    },
    addLog(event) {
      state.logs = [...state.logs, event].slice(-200);
      notify("logs");
    },
    setLogs(events) {
      state.logs = Array.isArray(events) ? events.slice(-200) : [];
      notify("logs");
    },
  };
}
