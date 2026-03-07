import { esc } from "../lib/format.js";
import { hrefForKpi, hrefForResource, hrefForSchedule } from "../lib/routes.js";

export const overviewScreen = {
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
    const activeFlights = flights.filter((flight) => String(flight.status || "") !== "Completed");
    const parkedPlanes = planes.filter((plane) => String(plane.status || "").includes("Parked"));
    const firstPlane = planes[0];
    const firstFlight = flights[0];

    return `
      <section>
        <div class="row">
          <h2 style="margin: 0;">Airport Overview</h2>
          <span class="muted">This screen is the shell for the future live airport map and big-picture simulation view.</span>
        </div>

        <div class="overview-grid">
          <article class="placeholder-card">
            <h3>Airport Map</h3>
            <p class="muted">Reserve this area for a real-time apron, taxiway and stand view with drill-down links.</p>
            <a class="app-nav-link" href="${hrefForSchedule()}">Open Schedule Screen</a>
          </article>
          <article class="placeholder-card">
            <h3>Movement Snapshot</h3>
            <div class="metric-value">${activeFlights.length}</div>
            <p class="muted">Active flights in current window</p>
          </article>
          <article class="placeholder-card">
            <h3>Ground Snapshot</h3>
            <div class="metric-value">${parkedPlanes.length}</div>
            <p class="muted">Planes currently parked</p>
          </article>
          <article class="placeholder-card">
            <h3>Operations KPI</h3>
            <p class="muted">Keep KPI and map separate so they can evolve independently.</p>
            <a class="app-nav-link" href="${hrefForKpi()}">Open KPI Screen</a>
          </article>
        </div>

        <div class="overview-grid section-gap">
          <article class="placeholder-card">
            <h3>Sample Resource Drilldown</h3>
            <p class="muted">Future map entities should link into the generic resource route.</p>
            ${
              firstPlane
                ? `<a class="app-nav-link" href="${hrefForResource("plane", firstPlane.id)}">Open Plane ${esc(firstPlane.id)}</a>`
                : `<span class="muted">No plane data loaded yet.</span>`
            }
          </article>
          <article class="placeholder-card">
            <h3>Flight Drilldown</h3>
            ${
              firstFlight
                ? `<a class="app-nav-link" href="${hrefForResource("flight", firstFlight.icao || firstFlight.id)}">Open Flight ${esc(firstFlight.icao || firstFlight.id)}</a>`
                : `<span class="muted">No flight data loaded yet.</span>`
            }
          </article>
        </div>
      </section>
    `;
  },
};
