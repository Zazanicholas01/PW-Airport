import { renderDetailTable } from "../components/detail-table.js";
import { esc, fmtLocalTimeFromIso, fmtVec3, planeImageUrlForModel } from "../lib/format.js";
import { hrefForSchedule } from "../lib/routes.js";

function parseMs(value) {
  if (!value) return null;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function computeReferenceTime(flight, airport) {
  if (flight.origin === airport) {
    return {
      label: "DEP",
      iso: flight.departure_time || null,
    };
  }
  return {
    label: "ARR",
    iso: flight.arrival_time || flight.departure_time || null,
  };
}

function computeDeltaMinutes(referenceIso, nowMs) {
  const refMs = parseMs(referenceIso);
  if (!Number.isFinite(refMs) || !Number.isFinite(nowMs)) return null;
  return Math.round((refMs - nowMs) / 60000);
}

function renderFlightProgress(flight, nowMs) {
  const statusText = String(flight.status || "");
  const depMs = parseMs(flight.departure_time);
  const arrMs = parseMs(flight.arrival_time);

  if (statusText.toLowerCase().includes("completed")) {
    return { completed: true, width: "100%", label: "Progress: Completed", indeterminate: false };
  }

  if (statusText.toLowerCase().includes("disembark")) {
    return {
      completed: false,
      width: "100%",
      label: "Progress: Arrived / Disembarking",
      indeterminate: false,
    };
  }

  if (Number.isFinite(depMs) && Number.isFinite(arrMs) && arrMs > depMs && Number.isFinite(nowMs)) {
    const percent = Math.max(0, Math.min(100, ((nowMs - depMs) / (arrMs - depMs)) * 100));
    return {
      completed: false,
      width: `${percent}%`,
      label: `Progress: ${Math.round(percent)}% en route`,
      indeterminate: false,
    };
  }

  return {
    completed: false,
    width: "0%",
    label: `Progress: ${statusText || "In progress"}`,
    indeterminate: true,
  };
}

function renderPlaneDetail(plane) {
  const route =
    plane.route_source && plane.route_destination
      ? `${plane.route_source} -> ${plane.route_destination}`
      : "";
  return `
    <section>
      <div class="row">
        <a class="app-nav-link" href="${hrefForSchedule()}">Back To Schedule</a>
        <span class="muted">${esc(plane.status ? `Status: ${plane.status}` : "")}</span>
      </div>

      <div class="plane-layout">
        <div class="plane-media">
          <img
            src="${planeImageUrlForModel(plane.model)}"
            alt="Plane image"
            onerror="this.onerror=null;this.src='/static/planes/_default.png';"
          />
        </div>

        <div class="plane-data">
          <h2 style="margin: 0 0 8px;">${esc(plane.model || `Plane ${plane.id}`)}</h2>
          <table>
            <tbody>
              ${renderDetailTable([
                ["ID", plane.id],
                ["Status", plane.status],
                ["Model", plane.model],
                ["Type", plane.type],
                ["Range", plane.range],
                ["Speed", plane.speed],
                ["Position", fmtVec3(plane.position)],
                ["Stand", plane.stand_id],
                ["Stand status", plane.stand_status],
                ["Route", route],
                ["Allocated flight", plane.active_flight_id],
              ])}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  `;
}

function renderFlightDetail(flight, plane, nowMs, airport) {
  const progress = renderFlightProgress(flight, nowMs);
  const reference = computeReferenceTime(flight, airport);
  const liveDelta = computeDeltaMinutes(reference.iso, nowMs);
  const routeTitle =
    flight.origin && flight.destination ? `${flight.origin} -> ${flight.destination}` : "Flight";
  const mediaHidden = progress.completed ? "hidden" : "";
  const tableHidden = progress.completed ? "hidden" : "";

  return `
    <section>
      <div class="row">
        <a class="app-nav-link" href="${hrefForSchedule()}">Back To Schedule</a>
        <span class="muted">${esc(flight.status ? `Status: ${flight.status}` : "")}</span>
      </div>

      <div class="plane-layout">
        <div class="plane-media ${mediaHidden}">
          <img
            src="${planeImageUrlForModel(plane ? plane.model : null)}"
            alt="Flight image"
            onerror="this.onerror=null;this.src='/static/planes/_default.png';"
          />
          <div class="muted section-gap-tight">
            DEP ${fmtLocalTimeFromIso(flight.departure_time) || "-"} · ARR ${fmtLocalTimeFromIso(flight.arrival_time) || "-"}
          </div>
          <div class="flight-progress section-gap-tight ${progress.indeterminate ? "indeterminate" : ""}">
            <div class="flight-progress-bar" style="width:${progress.width};"></div>
          </div>
          <div class="muted section-gap-tight">${esc(progress.label)}</div>
        </div>

        <div class="plane-data">
          <h2 style="margin: 0 0 8px;">${esc(routeTitle)}</h2>
          <div class="flight-completed-banner ${progress.completed ? "" : "hidden"}">
            <div class="flight-completed-check">OK</div>
            <div class="flight-completed-text">
              The flight has been completed. Thank you for choosing LIAG airport.
            </div>
          </div>
          <table class="${tableHidden}">
            <tbody>
              ${renderDetailTable([
                ["ID", flight.id],
                ["ICAO", flight.icao],
                ["Origin", flight.origin],
                ["Destination", flight.destination],
                ["Departure", flight.departure_time],
                ["Arrival", flight.arrival_time],
                ["Type", flight.tipo],
                ["Status", flight.status],
                ["Airplane", flight.airplane_id],
                ["Reference", `${reference.label || ""} ${reference.iso || ""}`.trim()],
                ["Delta minutes", liveDelta],
              ])}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  `;
}

function renderUnsupported(resourceType, id) {
  return `
    <section class="placeholder-screen">
      <h2>${esc(resourceType)} ${esc(id)}</h2>
      <p class="muted">This resource type is reserved for future drill-down routes.</p>
      <a class="app-nav-link" href="${hrefForSchedule()}">Back To Schedule</a>
    </section>
  `;
}

function renderMissing(resourceType, id) {
  return `
    <section class="placeholder-screen">
      <h2>${esc(resourceType)} ${esc(id)}</h2>
      <p class="muted">Resource not found in current dashboard data.</p>
      <a class="app-nav-link" href="${hrefForSchedule()}">Back To Schedule</a>
    </section>
  `;
}

export const resourceDetailScreen = {
  async preload({ store, services, route }) {
    const { resourceType, id } = route.params;
    const state = store.getState();

    if (resourceType === "plane" && !state.dashboard.planesById.has(String(id))) {
      await services.refresh.refreshDashboard();
    }

    if (resourceType === "flight" && !state.dashboard.flightsById.has(String(id))) {
      const flight = await services.api.fetchFlightById(id);
      if (flight) {
        store.upsertFlight(flight);
      }
    }

    const flight = store.getState().dashboard.flightsById.get(String(id));
    if (resourceType === "flight" && flight?.airplane_id) {
      const hasPlane = store.getState().dashboard.planesById.has(String(flight.airplane_id));
      if (!hasPlane) {
        await services.refresh.refreshDashboard();
      }
    }
  },

  render({ store, route }) {
    const { resourceType, id } = route.params;
    const state = store.getState();

    if (resourceType === "plane") {
      const plane = state.dashboard.planesById.get(String(id));
      return plane ? renderPlaneDetail(plane) : renderMissing(resourceType, id);
    }

    if (resourceType === "flight") {
      const flight = state.dashboard.flightsById.get(String(id));
      if (!flight) return renderMissing(resourceType, id);
      const plane = flight.airplane_id
        ? state.dashboard.planesById.get(String(flight.airplane_id)) || null
        : null;
      return renderFlightDetail(flight, plane, state.sim.nowMs, state.ui.airport);
    }

    return renderUnsupported(resourceType, id);
  },
};
