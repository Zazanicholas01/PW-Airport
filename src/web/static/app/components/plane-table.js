import { esc, statusClass } from "../lib/format.js";

export function renderPlaneTable(planes) {
  const rows = (planes || [])
    .map((plane) => {
      const route =
        plane.route_source && plane.route_destination
          ? `${plane.route_source} → ${plane.route_destination}`
          : "";
      const speed = plane.speed == null ? "" : Number(plane.speed).toFixed(2);
      return `
        <tr class="plane-row clickable-row" data-plane-id="${esc(plane.id || "")}">
          <td>${esc(plane.id || "")}</td>
          <td><span class="pill ${statusClass(plane.status)}">${esc(plane.status || "")}</span></td>
          <td class="muted">${esc(plane.model || "")}</td>
          <td>${esc(plane.type || "")}</td>
          <td>${esc(plane.range || "")}</td>
          <td class="muted">${esc(speed)}</td>
          <td class="muted">${esc(plane.stand_id || "")}</td>
          <td class="muted" title="${esc(route)}">${esc(route)}</td>
        </tr>
      `;
    })
    .join("");

  return rows || `<tr><td colspan="8" class="muted">No planes found.</td></tr>`;
}
