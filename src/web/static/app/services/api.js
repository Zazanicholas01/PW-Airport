export function createApiService() {
  return {
    async fetchClock() {
      const res = await fetch("/api/clock");
      return await res.json();
    },
    async fetchDashboard({ airport, windowMinutes }) {
      const params = new URLSearchParams({
        airport,
        window_minutes: String(windowMinutes),
      });
      const res = await fetch(`/api/dashboard?${params.toString()}`);
      return await res.json();
    },
    async fetchFlightById(flightId) {
      const res = await fetch(`/api/flight/${encodeURIComponent(String(flightId))}`);
      if (!res.ok) return null;
      return await res.json();
    },
  };
}
