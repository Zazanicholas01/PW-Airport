export function createApiService(store) {
  function withNow(params = new URLSearchParams()) {
    const { sim } = store.getState();
    if (sim.nowMs != null) params.set("now_unix_ms", String(sim.nowMs));
    return params;
  }

  return {
    async fetchWindow({ airport, windowMinutes }) {
      const params = withNow(
        new URLSearchParams({
          airport,
          window_minutes: String(windowMinutes),
        }),
      );
      const res = await fetch(`/api/window?${params.toString()}`);
      const data = await res.json();
      return { flights: data.flights || [], now: data.now || null };
    },
    async fetchPlanes() {
      const params = withNow(new URLSearchParams());
      const res = await fetch(`/api/planes?${params.toString()}`);
      const data = await res.json();
      return data.planes || [];
    },
    async fetchFlightById(flightId) {
      const res = await fetch(`/api/flight/${encodeURIComponent(String(flightId))}`);
      if (!res.ok) return null;
      return await res.json();
    },
  };
}
