import { esc, flightIdForRow, fmtWhen, minsUntil, statusClass, toDate } from "../lib/format.js";

export function renderFlightTable(flights, { airport, nowMs }) {
  const rows = (flights || [])
    .map((flight) => {
      const flightId = flightIdForRow(flight);
      const when = fmtWhen(flight, airport);
      const dt = toDate(when.t);
      const delta = dt ? minsUntil(dt, nowMs) : "";
      const whenCell = dt ? `${when.label} ${dt.toLocaleTimeString()}` : "";
      return `
        <tr class="flight-row clickable-row" data-flight-id="${esc(flightId)}">
          <td>${esc(whenCell)}</td>
          <td>${esc(delta)}</td>
          <td>${esc(flight.icao || flight.id)}</td>
          <td>${esc(flight.origin)} → ${esc(flight.destination)}</td>
          <td>${esc(flight.tipo || "")}</td>
          <td><span class="pill ${statusClass(flight.status)}">${esc(flight.status || "")}</span></td>
          <td class="muted">${esc(flight.airplane_id || "")}</td>
        </tr>
      `;
    })
    .join("");

  return rows || `<tr><td colspan="7" class="muted">No flights found.</td></tr>`;
}
