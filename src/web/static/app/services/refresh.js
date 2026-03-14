export function createRefreshService(store, api) {
  const WINDOW_SIM_SECONDS = 60;
  const PLANES_SIM_SECONDS = 15;
  const WINDOW_POLL_MIN_MS = 500;
  const WINDOW_POLL_MAX_MS = 5000;
  const PLANES_POLL_MIN_MS = 250;
  const PLANES_POLL_MAX_MS = 2000;
  let allRefreshTimer = null;
  let windowRefreshTimer = null;
  let planesRefreshTimer = null;
  let windowPollTimer = null;
  let planesPollTimer = null;
  let started = false;

  function currentTimeScale() {
    const { sim } = store.getState();
    const scale = Number(sim.timeScale);
    return Number.isFinite(scale) && scale > 0 ? scale : 1;
  }

  function clamp(value, min, max) {
    return Math.min(max, Math.max(min, value));
  }

  function nextWindowPollMs() {
    return clamp(
      (WINDOW_SIM_SECONDS * 1000) / currentTimeScale(),
      WINDOW_POLL_MIN_MS,
      WINDOW_POLL_MAX_MS,
    );
  }

  function nextPlanesPollMs() {
    return clamp(
      (PLANES_SIM_SECONDS * 1000) / currentTimeScale(),
      PLANES_POLL_MIN_MS,
      PLANES_POLL_MAX_MS,
    );
  }

  function scheduleWindowPoll() {
    windowPollTimer = setTimeout(async () => {
      try {
        await refreshWindow();
      } catch {}
      scheduleWindowPoll();
    }, nextWindowPollMs());
  }

  function schedulePlanesPoll() {
    planesPollTimer = setTimeout(async () => {
      try {
        await refreshPlanes();
      } catch {}
      schedulePlanesPoll();
    }, nextPlanesPollMs());
  }

  async function refreshWindow() {
    const { ui, sim } = store.getState();
    const { flights, now, nowSource, timeScale } = await api.fetchWindow({
      airport: ui.airport,
      windowMinutes: ui.windowMinutes,
    });
    store.setFlights(flights);

    if (sim.nowMs == null && now && nowSource !== "realtime") {
      const parsed = Date.parse(now);
      if (!Number.isNaN(parsed)) {
        store.setSimClock(parsed, timeScale ?? sim.timeScale);
      }
    }
  }

  async function refreshPlanes() {
    const planes = await api.fetchPlanes();
    store.setPlanes(planes);
  }

  async function refreshAll() {
    await Promise.all([refreshWindow(), refreshPlanes()]);
  }

  async function initialRefresh() {
    await store.waitForSimClock(5000);
    await refreshAll();
  }

  function restartAdaptivePolls() {
    if (windowPollTimer) {
      clearTimeout(windowPollTimer);
      windowPollTimer = null;
    }
    if (planesPollTimer) {
      clearTimeout(planesPollTimer);
      planesPollTimer = null;
    }
    if (!started) return;
    scheduleWindowPoll();
    schedulePlanesPoll();
  }

  function handleClockSync({ previousTimeScale, nextTimeScale }) {
    restartAdaptivePolls();

    if (previousTimeScale !== nextTimeScale) {
      scheduleWindowRefreshSoon(0);
      schedulePlanesRefreshSoon(0);
    }
  }

  function scheduleAllRefreshSoon(delayMs = 75) {
    if (allRefreshTimer) return;
    allRefreshTimer = setTimeout(async () => {
      allRefreshTimer = null;
      try {
        await refreshAll();
      } catch {}
    }, delayMs);
  }

  function scheduleWindowRefreshSoon(delayMs = 50) {
    if (windowRefreshTimer) return;
    windowRefreshTimer = setTimeout(async () => {
      windowRefreshTimer = null;
      try {
        await refreshWindow();
      } catch {}
    }, delayMs);
  }

  function schedulePlanesRefreshSoon(delayMs = 50) {
    if (planesRefreshTimer) return;
    planesRefreshTimer = setTimeout(async () => {
      planesRefreshTimer = null;
      try {
        await refreshPlanes();
      } catch {}
    }, delayMs);
  }

  function start() {
    if (started) return;
    started = true;
    initialRefresh().catch(() => {});
    // Observer events are the primary refresh driver; polling adapts to simulation speed as fallback.
    scheduleWindowPoll();
    schedulePlanesPoll();
  }

  return {
    refreshAll,
    refreshWindow,
    refreshPlanes,
    handleClockSync,
    scheduleAllRefreshSoon,
    scheduleWindowRefreshSoon,
    schedulePlanesRefreshSoon,
    start,
  };
}
