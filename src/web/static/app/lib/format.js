const ALLOWED_LEVELS = new Set(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]);
const TIME_ONLY_FORMAT = {
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
};
const DATE_TIME_FORMAT = {
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
};
const BACKEND_EVENT_LABELS = {
  departure_assigned: "Departure plane assigned",
  landing_plane_assigned: "Arrival plane assigned",
  landing_departed: "Inbound plane departed remote airport",
  departure_started: "Departure started",
  landing_stand_reserved: "Arrival stand reserved",
  landing_spawn: "Inbound plane spawned",
  landing_approach_started: "Landing approach started",
  departure_completed: "Departure completed",
  landing_completed: "Landing completed",
  plane_left_stand: "Plane left stand",
  disembark_complete: "Disembark completed",
  initial_spawns_scheduled: "Initial spawns scheduled",
};

export function toDate(value) {
  return value ? new Date(value) : null;
}

export function parseDateMs(value) {
  if (!value) return null;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function fmtLocalTimeFromIso(value) {
  try {
    return value ? new Date(value).toLocaleTimeString([], TIME_ONLY_FORMAT) : "";
  } catch {
    return "";
  }
}

export function fmtLocalDateTime(value) {
  try {
    return value ? new Date(value).toLocaleString([], DATE_TIME_FORMAT) : "";
  } catch {
    return "";
  }
}

export function minsUntil(dt, nowMs) {
  const base = nowMs != null ? new Date(nowMs) : new Date();
  return Math.round((dt - base) / 60000);
}

export function fmtWhen(flight, airport) {
  const isDeparture = flight.origin === airport;
  return {
    t: isDeparture ? flight.departure_time : flight.arrival_time || flight.departure_time,
    label: isDeparture ? "DEP" : "ARR",
  };
}

export function statusClass(status) {
  const text = String(status || "").toLowerCase();
  if (text.includes("scheduled")) return "status-scheduled";
  if (text.includes("boarding") || text.includes("depart")) return "status-boarding";
  if (text.includes("landing") || text.includes("ongoing") || text.includes("flight")) return "status-landing";
  if (text.includes("reserved")) return "status-boarding";
  if (text.includes("parked")) return "status-parked";
  if (text.includes("disembarking")) return "status-parked";
  if (text.includes("completed")) return "status-completed";
  return "status-default";
}

export function esc(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

export function fmtVec3(position) {
  if (!position || typeof position !== "object") return "";
  const x = Number(position.x);
  const y = Number(position.y);
  const z = Number(position.z);
  if (![x, y, z].every(Number.isFinite)) return "";
  return `${x.toFixed(1)}, ${y.toFixed(1)}, ${z.toFixed(1)}`;
}

export function slugifyModel(model) {
  return String(model ?? "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

export function planeImageUrlForModel(model) {
  const slug = slugifyModel(model);
  return slug
    ? `/static/planes/models/${encodeURIComponent(slug)}.png`
    : "/static/planes/_default.png";
}

export function flightIdForRow(flight) {
  return String((flight && (flight.icao || flight.id)) || "");
}

export function shortTime(value) {
  try {
    return value ? new Date(value).toLocaleTimeString([], TIME_ONLY_FORMAT) : "";
  } catch {
    return "";
  }
}

function startCase(value) {
  return String(value || "")
    .replaceAll(/[_-]+/g, " ")
    .replaceAll(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (match) => match.toUpperCase());
}

function prettySubsystem(value) {
  const raw = String(value || "").trim();
  if (!raw) return "";
  if (raw.includes(".")) {
    return raw.split(".").at(-1) || raw;
  }
  return startCase(raw);
}

function collectFields(event) {
  if (event.fields && typeof event.fields === "object") {
    return event.fields;
  }
  return Object.fromEntries(
    Object.entries(event || {}).filter(([key]) =>
      !["type", "level", "logger", "subsystem", "message", "ts", "sim_ts", "event"].includes(key),
    ),
  );
}

function summarizeFields(fields) {
  if (!fields || typeof fields !== "object") return "";
  return Object.entries(fields)
    .filter(([, value]) => value != null && value !== "")
    .slice(0, 4)
    .map(([key, value]) => `${startCase(key)}: ${String(value)}`)
    .join(" · ");
}

function humanMessage(event, fields) {
  if (event.event) {
    return BACKEND_EVENT_LABELS[event.event] || startCase(event.event);
  }
  const raw = String(event.message || event.type || "").trim();
  if (!raw) {
    return "";
  }
  if (raw.startsWith("backend:")) {
    return startCase(raw.slice("backend:".length));
  }
  return raw;
}

export function normalizeEvent(obj) {
  const event = obj && typeof obj === "object" ? obj : { type: "raw", message: String(obj ?? "") };
  const levelRaw = String(event.level || event.type || "INFO").toUpperCase();
  const fields = collectFields(event);
  const details = summarizeFields(fields);
  return {
    level: ALLOWED_LEVELS.has(levelRaw) ? levelRaw : "INFO",
    ts: event.sim_ts || event.ts || null,
    subsystem: prettySubsystem(event.subsystem || event.logger || ""),
    message: humanMessage(event, fields),
    details,
    fields: Object.keys(fields).length ? fields : null,
  };
}
