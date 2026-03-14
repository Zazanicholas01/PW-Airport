import { renderEventLog } from "../components/event-log.js";
import { renderFlightTable } from "../components/flight-table.js";
import { renderPlaneTable } from "../components/plane-table.js";
import { delegate } from "../lib/dom.js";
import { esc } from "../lib/format.js";
import { hrefForResource } from "../lib/routes.js";

export const scheduleScreen = {
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

    return `
      <section>
        <div class="row">
          <h2 style="margin: 0;">Scheduling Window</h2>
          <span class="muted">Auto-refresh on events, plus 5s flights and 2s planes polling</span>
        </div>

        <div class="row control-row">
          <label>Airport <input id="airport" value="${esc(state.ui.airport)}" size="6" /></label>
          <label>Window (min) <input id="window" value="${esc(state.ui.windowMinutes)}" size="4" /></label>
          <button id="refresh">Refresh</button>
        </div>

        <div class="board-block">
          <div class="board-title">Flight Information</div>
          <table class="board-table flights-board">
            <thead>
              <tr>
                <th>When</th>
                <th>Δ Min</th>
                <th>Flight</th>
                <th>Route</th>
                <th>Type</th>
                <th>Status</th>
                <th>Airplane</th>
              </tr>
            </thead>
            <tbody id="rows">${renderFlightTable(flights, {
              airport: state.ui.airport,
              nowMs: state.sim.nowMs,
            })}</tbody>
          </table>
        </div>

        <div class="board-block section-gap">
          <div class="board-title">Planes On Ground</div>
          <table class="board-table planes-board">
            <thead>
              <tr>
                <th>Airplane</th>
                <th>Status</th>
                <th>Model</th>
                <th>Type</th>
                <th>Range</th>
                <th>Speed</th>
                <th>Stand</th>
                <th>Route</th>
              </tr>
            </thead>
            <tbody id="plane_rows">${renderPlaneTable(planes)}</tbody>
          </table>
        </div>

        <div class="section-gap">${renderEventLog(state.logs)}</div>
      </section>
    `;
  },

  bind(root, { store, services }) {
    const refreshButton = root.querySelector("#refresh");
    const airportInput = root.querySelector("#airport");
    const windowInput = root.querySelector("#window");

    if (refreshButton) {
      refreshButton.onclick = () => {
        store.setUi({
          airport: airportInput.value.trim() || "LIAG",
          windowMinutes: Number(windowInput.value || "60"),
        });
        services.refresh.refreshAll().catch(() => {});
      };
    }

    if (airportInput) {
      airportInput.onchange = () => {
        store.setUi({ airport: airportInput.value.trim() || "LIAG" });
      };
    }

    if (windowInput) {
      windowInput.onchange = () => {
        store.setUi({ windowMinutes: Number(windowInput.value || "60") });
      };
    }

    delegate(root, "tr[data-flight-id]", "click", (_event, target) => {
      location.hash = hrefForResource("flight", target.dataset.flightId);
    });

    delegate(root, "tr[data-plane-id]", "click", (_event, target) => {
      location.hash = hrefForResource("plane", target.dataset.planeId);
    });

    const events = root.querySelector("#events");
    if (events) {
      events.scrollTop = events.scrollHeight;
    }
  },
};
