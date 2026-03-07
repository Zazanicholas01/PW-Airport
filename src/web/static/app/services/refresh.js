export function createRefreshService(store, api) {
  let refreshTimer = null;
  let started = false;

  async function refreshWindow() {
    const { ui, sim } = store.getState();
    const { flights, now } = await api.fetchWindow({
      airport: ui.airport,
      windowMinutes: ui.windowMinutes,
    });
    store.setFlights(flights);

    if (sim.nowMs == null && now) {
      const parsed = Date.parse(now);
      if (!Number.isNaN(parsed)) {
        store.setSimClock(parsed, sim.timeScale);
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

  function scheduleRefreshSoon() {
    if (refreshTimer) return;
    refreshTimer = setTimeout(async () => {
      refreshTimer = null;
      try {
        await refreshAll();
      } catch {}
    }, 200);
  }

  function start() {
    if (started) return;
    started = true;
    refreshAll().catch(() => {});
    setInterval(() => refreshWindow().catch(() => {}), 10000);
    setInterval(() => refreshPlanes().catch(() => {}), 2000);
  }

  return {
    refreshAll,
    refreshWindow,
    refreshPlanes,
    scheduleRefreshSoon,
    start,
  };
}
