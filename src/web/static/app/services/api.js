export function createApiService(store) {
  return {
    async fetchWindow({ airport, windowMinutes }) {
      const params = new URLSearchParams({
        airport,
        window_minutes: String(windowMinutes),
      });
      const res = await fetch(`/api/window?${params.toString()}`);
      const data = await res.json();
      return {
        flights: data.flights || [],
        now: data.now || null,
        nowSource: data.now_source || null,
        timeScale: data.time_scale ?? null,
      };
    },
    async fetchPlanes() {
      const res = await fetch("/api/planes");
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
