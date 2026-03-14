export function createStore(initialState) {
  const listeners = new Set();
  const state = {
    route: initialState.route,
    connection: initialState.connection,
    sim: initialState.sim,
    data: initialState.data,
    ui: initialState.ui,
    logs: initialState.logs,
  };

  function notify(type) {
    for (const listener of listeners) listener(type, getState());
  }

  function getState() {
    return state;
  }

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
    setFlights(flights) {
      state.data.flightsById = new Map(
        (flights || [])
          .map((flight) => [String((flight && (flight.icao || flight.id)) || ""), flight])
          .filter(([id]) => id),
      );
      notify("flights");
    },
    upsertFlight(flight) {
      const id = String((flight && (flight.icao || flight.id)) || "");
      if (!id) return;
      state.data.flightsById.set(id, flight);
      notify("flights");
    },
    setPlanes(planes) {
      state.data.planesById = new Map(
        (planes || [])
          .map((plane) => [String((plane && plane.id) || ""), plane])
          .filter(([id]) => id),
      );
      notify("planes");
    },
    setSimClock(nowMs, timeScale) {
      state.sim = {
        ...state.sim,
        nowMs: Number.isFinite(nowMs) ? nowMs : state.sim.nowMs,
        timeScale: Number.isFinite(timeScale) ? timeScale : state.sim.timeScale,
        receivedAtMs: Date.now(),
      };

      console.log("[clock_sync][WEB SET]", {
        nowMs: state.sim.nowMs,
        timeScale: state.sim.timeScale,
        receivedAtMs: state.sim.receivedAtMs,
        iso: Number.isFinite(state.sim.nowMs) ? new Date(state.sim.nowMs).toISOString() : null,
      });

      notify("sim");
    },
    advanceSimClock() {
      if (!Number.isFinite(state.sim.nowMs)) return;
      if (!Number.isFinite(state.sim.receivedAtMs)) return;

      const now = Date.now();
      const elapsedMs = now - state.sim.receivedAtMs;
      if (elapsedMs <= 0) return;

      const timeScale = Number.isFinite(state.sim.timeScale) ? state.sim.timeScale : 1;

      state.sim = {
        ...state.sim,
        nowMs: state.sim.nowMs + elapsedMs * timeScale,
        receivedAtMs: now,
      };

      if (now - lastClockAdvanceLogAt >= 2000) {
        lastClockAdvanceLogAt = now;
        console.log("[clock_sync][WEB ADVANCE]", {
          nowMs: state.sim.nowMs,
          timeScale: state.sim.timeScale,
          iso: new Date(state.sim.nowMs).toISOString(),
        });
      }
      
      notify("sim");
    },
    addLog(event) {
      state.logs = [...state.logs, event].slice(-200);
      notify("logs");
    },
    markFlightCompleted(flightId) {
      const current = state.data.flightsById.get(String(flightId));
      if (!current) return;
      state.data.flightsById.set(String(flightId), { ...current, status: "Completed" });
      notify("flights");
    },
  };
}
