import { normalizeEvent } from "../lib/format.js";

export function createRefreshService(store, api, simClock) {
  let dashboardTimer = null;
  let clockTimer = null;
  let dashboardInFlight = false;
  let clockInFlight = false;
  let lastTimeScaleRevision = null;

  async function refreshDashboard() {
    if (dashboardInFlight) return;
    dashboardInFlight = true;
    const { ui } = store.getState();
    try {
      const snapshot = await api.fetchDashboard({
        airport: ui.airport,
        windowMinutes: ui.windowMinutes,
      });

      store.setDashboardSnapshot(snapshot);
      store.setLogs((snapshot.logs || []).map((item) => normalizeEvent(item)));
    } catch (error) {
      throw error;
    } finally {
      dashboardInFlight = false;
    }
  }

  async function refreshClock() {
    if (clockInFlight) return;
    clockInFlight = true;
    try {
      const clock = await api.fetchClock();
      const nowMs = Number(clock?.sim_unix_ms);
      const timeScale = Number(clock?.time_scale);
      const timeScaleRevision = Number(clock?.time_scale_revision);

      simClock.applyAnchor(nowMs, timeScale);
      store.setConnectionStatus("connected");

      if (
        Number.isFinite(timeScaleRevision) &&
        lastTimeScaleRevision != null &&
        timeScaleRevision !== lastTimeScaleRevision
      ) {
        scheduleDashboardRefreshSoon(0);
      }

      if (Number.isFinite(timeScaleRevision)) {
        lastTimeScaleRevision = timeScaleRevision;
      }
    } catch (error) {
      store.setConnectionStatus("poll failed");
      throw error;
    } finally {
      clockInFlight = false;
    }
  }

  function handleClockSync() {
    // Polling transport uses refreshClock().
  }

  function scheduleDashboardRefreshSoon(delayMs = 50) {
    setTimeout(() => {
      refreshDashboard().catch(() => {});
    }, delayMs);
  }

  function start({ clockIntervalMs = 500, dashboardIntervalMs = 2000 } = {}) {
    simClock.start();
    refreshClock().catch(() => {});
    refreshDashboard().catch(() => {});
    if (clockTimer) {
      clearInterval(clockTimer);
    }
    if (dashboardTimer) {
      clearInterval(dashboardTimer);
    }
    clockTimer = setInterval(() => {
      refreshClock().catch(() => {});
    }, clockIntervalMs);
    dashboardTimer = setInterval(() => {
      refreshDashboard().catch(() => {});
    }, dashboardIntervalMs);
  }

  function stop() {
    if (clockTimer) {
      clearInterval(clockTimer);
      clockTimer = null;
    }
    if (dashboardTimer) {
      clearInterval(dashboardTimer);
      dashboardTimer = null;
    }
  }

  return {
    refreshClock,
    refreshDashboard,
    refreshAll: refreshDashboard,
    handleClockSync,
    scheduleDashboardRefreshSoon,
    scheduleAllRefreshSoon: scheduleDashboardRefreshSoon,
    start,
    stop,
  };
}
