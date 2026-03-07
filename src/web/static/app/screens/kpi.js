export const kpiScreen = {
  async preload({ store, services }) {
    const { data } = store.getState();
    if (!data.flightsById.size || !data.planesById.size) {
      await services.refresh.refreshAll();
    }
  },

  render({ store }) {
    const state = store.getState();
    const flights = Array.from(state.data.flightsById.values());
    const planes = Array.from(state.data.planesById.values());
    const completedFlights = flights.filter((flight) => String(flight.status || "") === "Completed");
    const assignedFlights = flights.filter((flight) => flight.airplane_id);
    const parkedPlanes = planes.filter((plane) =>
      String(plane.status || "").toLowerCase().includes("parked"),
    );

    return `
      <section>
        <div class="row">
          <h2 style="margin: 0;">KPI View</h2>
          <span class="muted">Use this screen for throughput, delays, stand occupancy and simulation health.</span>
        </div>

        <div class="overview-grid section-gap">
          <article class="placeholder-card">
            <h3>Flights In Window</h3>
            <div class="metric-value">${flights.length}</div>
          </article>
          <article class="placeholder-card">
            <h3>Completed Flights</h3>
            <div class="metric-value">${completedFlights.length}</div>
          </article>
          <article class="placeholder-card">
            <h3>Assigned Flights</h3>
            <div class="metric-value">${assignedFlights.length}</div>
          </article>
          <article class="placeholder-card">
            <h3>Parked Planes</h3>
            <div class="metric-value">${parkedPlanes.length}</div>
          </article>
        </div>
      </section>
    `;
  },
};
