import { esc } from "../lib/format.js";

export function renderDetailTable(rows) {
  const body = (rows || [])
    .map(
      ([key, value]) =>
        `<tr><td class="muted detail-key">${esc(key)}</td><td>${esc(value ?? "")}</td></tr>`,
    )
    .join("");

  return body || `<tr><td class="muted detail-key">Info</td><td>No data</td></tr>`;
}
