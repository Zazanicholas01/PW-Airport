export function createSimClockService(store) {
  let timer = null;

  function getSimNowMs() {
    const sim = store.getState().sim;
    if (!Number.isFinite(sim.anchorSimMs) || !Number.isFinite(sim.anchorClientMs)) {
      return null;
    }

    const scale = Number.isFinite(sim.timeScale) ? sim.timeScale : 1;
    const elapsedClientMs = Date.now() - sim.anchorClientMs;
    return sim.anchorSimMs + elapsedClientMs * scale;
  }

  function tick() {
    const simNowMs = getSimNowMs();
    if (Number.isFinite(simNowMs)) {
      store.setDerivedSimNow(simNowMs);
    }
  }

  function applyAnchor(simUnixMs, timeScale) {
    if (!Number.isFinite(simUnixMs)) return;
    store.setSimAnchor({
      anchorSimMs: simUnixMs,
      anchorClientMs: Date.now(),
      timeScale: Number.isFinite(timeScale) ? timeScale : store.getState().sim.timeScale,
    });
    tick();
  }

  function start(intervalMs = 200) {
    if (timer) {
      clearInterval(timer);
    }
    timer = setInterval(tick, intervalMs);
    tick();
  }

  function stop() {
    if (timer) {
      clearInterval(timer);
      timer = null;
    }
  }

  return {
    applyAnchor,
    getSimNowMs,
    start,
    stop,
  };
}
