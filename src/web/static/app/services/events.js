export function createEventService(_store, refresh, _simClock) {
  function connect() {
    // Polling transport: no persistent browser stream.
  }

  function updateSubscription() {
    refresh.refreshDashboard().catch(() => {});
  }

  function requestSnapshot() {
    refresh.refreshDashboard().catch(() => {});
  }

  function disconnect() {
    // Polling transport: no persistent browser stream.
  }

  return {
    connect,
    updateSubscription,
    requestSnapshot,
    disconnect,
  };
}
