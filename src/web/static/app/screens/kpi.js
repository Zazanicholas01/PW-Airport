import { esc } from "../lib/format.js";

export const kpiScreen = {
  async preload({ services }) {
    await services.refresh.refreshDashboard();
  },

  render({ store }) {
    const state = store.getState();
    const flights = state.dashboard.flights || [];
    const planes = state.dashboard.planes || [];
    const completedFlights = flights.filter((flight) => String(flight.status || "") === "Completed");
    const allocatedPlanes = planes.filter((plane) => plane.active_flight_id);

    return `
      <section>
        <div class="overview-grid">
          <article class="placeholder-card">
            <h3>Flights In Window</h3>
            <div class="metric-value">${esc(flights.length)}</div>
          </article>
          <article class="placeholder-card">
            <h3>Completed Flights</h3>
            <div class="metric-value">${esc(completedFlights.length)}</div>
          </article>
          <article class="placeholder-card">
            <h3>Allocated Planes</h3>
            <div class="metric-value">${esc(allocatedPlanes.length)}</div>
          </article>
          <article class="placeholder-card">
            <h3>Total Planes</h3>
            <div class="metric-value">${esc(planes.length)}</div>
          </article>
        </div>
      </section>
    `;
  },
};
