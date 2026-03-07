import { esc } from "../lib/format.js";
import { hrefForKpi, hrefForOverview, hrefForSchedule } from "../lib/routes.js";

function navClass(current, expected) {
  return current === expected ? "app-nav-link active" : "app-nav-link";
}

export function renderAppShell({ route, connection, sim, screenHtml }) {
  const clockLabel = sim.nowMs != null ? new Date(sim.nowMs).toLocaleString() : "syncing";
  const scaleLabel = sim.timeScale != null ? `${sim.timeScale}x` : "n/a";

  return `
    <div class="app-shell">
      <div class="app-bar">
        <div>
          <div class="app-title">PW Airport Ops</div>
          <div class="muted">Route-driven dashboard ready for overview, schedule, resource and KPI views</div>
        </div>
        <nav class="app-nav">
          <a class="${navClass(route.name, "overview")}" href="${hrefForOverview()}">Overview</a>
          <a class="${navClass(route.name, "schedule")}" href="${hrefForSchedule()}">Schedule</a>
          <a class="${navClass(route.name, "kpi")}" href="${hrefForKpi()}">KPI</a>
        </nav>
      </div>

      <div class="app-status">
        <span id="ws_status" class="pill status-default">WS ${esc(connection.status)}</span>
        <span id="sim_time" class="app-status-item">Sim Time ${esc(clockLabel)}</span>
        <span id="sim_scale" class="app-status-item">Scale ${esc(scaleLabel)}</span>
      </div>

      <div id="app_screen">${screenHtml}</div>
    </div>
  `;
}

export function updateAppShell(root, { route, connection, sim }) {
  const navLinks = root.querySelectorAll(".app-nav-link");
  for (const link of navLinks) {
    const href = link.getAttribute("href");
    const isActive =
      (route.name === "overview" && href === hrefForOverview()) ||
      (route.name === "schedule" && href === hrefForSchedule()) ||
      (route.name === "kpi" && href === hrefForKpi());
    link.classList.toggle("active", isActive);
  }

  const wsStatus = root.querySelector("#ws_status");
  if (wsStatus) wsStatus.textContent = `WS ${connection.status}`;

  const simTime = root.querySelector("#sim_time");
  if (simTime) {
    simTime.textContent = `Sim Time ${
      sim.nowMs != null ? new Date(sim.nowMs).toLocaleString() : "syncing"
    }`;
  }

  const simScale = root.querySelector("#sim_scale");
  if (simScale) {
    simScale.textContent = `Scale ${sim.timeScale != null ? `${sim.timeScale}x` : "n/a"}`;
  }
}
