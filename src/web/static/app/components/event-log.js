import { esc, shortTime } from "../lib/format.js";

export function renderEventLog(events) {
  const lines = (events || [])
    .map((event) => {
      const fieldsText = event.fields ? JSON.stringify(event.fields) : "";
      return `
        <div class="logline lvl-${esc(event.level)}">
          <div class="ts">${esc(shortTime(event.ts))}</div>
          <div class="lvl">${esc(event.level)}</div>
          <div class="sub" title="${esc(event.subsystem)}">${esc(event.subsystem)}</div>
          <div class="msg" title="${esc(event.message)}">${esc(event.message)}</div>
          <div class="fields" title="${esc(fieldsText)}">${esc(fieldsText)}</div>
        </div>
      `;
    })
    .join("");

  return `
    <div class="board-block">
      <div class="board-title">Live Events</div>
      <div id="events">${lines}</div>
    </div>
  `;
}
