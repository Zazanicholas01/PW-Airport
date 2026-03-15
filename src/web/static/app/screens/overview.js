import { esc } from "../lib/format.js";
import { hrefForSchedule } from "../lib/routes.js";

export const overviewScreen = {
  async preload({ services }) {
    await services.refresh.refreshDashboard();
  },

  render({ store }) {
    const state = store.getState();
    const flights = state.dashboard.flights || [];
    const allocatedPlanes = (state.dashboard.planes || []).filter((plane) => plane.active_flight_id);

    return `
      <section class="placeholder-screen">
        <h2>Operations Overview</h2>
        <p class="muted">
          The schedule board is now the primary dashboard view. It currently tracks
          ${esc(flights.length)} flights and ${esc(allocatedPlanes.length)} allocated planes from one backend snapshot.
        </p>
        <a class="app-nav-link" href="${hrefForSchedule()}">Open Schedule Board</a>
      </section>
    `;
  },
};
