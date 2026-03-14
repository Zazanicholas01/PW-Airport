import { renderAppShell, updateAppShell } from "./components/app-shell.js";
import { parseHash } from "./lib/routes.js";
import { kpiScreen } from "./screens/kpi.js";
import { notFoundScreen } from "./screens/not-found.js";
import { overviewScreen } from "./screens/overview.js";
import { resourceDetailScreen } from "./screens/resource-detail.js";
import { scheduleScreen } from "./screens/schedule.js";

const SCREENS = {
  overview: overviewScreen,
  schedule: scheduleScreen,
  "resource-detail": resourceDetailScreen,
  kpi: kpiScreen,
  "not-found": notFoundScreen,
};

export function createRouter(mount, store, services) {
  let preloadToken = 0;
  let shellReady = false;
  let screenRoot = null;

  function currentContext() {
    return {
      store,
      services,
      route: store.getState().route,
    };
  }

  function ensureShell() {
    if (shellReady) return;
    const state = store.getState();
    mount.innerHTML = renderAppShell({
      route: state.route,
      connection: state.connection,
      sim: state.sim,
      screenHtml: "",
    });
    screenRoot = mount.querySelector("#app_screen");
    shellReady = true;
  }

  function renderScreen() {
    ensureShell();
    const route = store.getState().route;
    const screen = SCREENS[route.name] || notFoundScreen;
    const screenHtml = screen.render(currentContext());
    screenRoot.innerHTML = screenHtml;

    if (screen.bind) {
      screen.bind(screenRoot, currentContext());
    }
  }

  function renderShellState() {
    ensureShell();
    updateAppShell(mount, store.getState());
  }

  async function preloadRoute() {
    const route = store.getState().route;
    const screen = SCREENS[route.name] || notFoundScreen;
    const token = ++preloadToken;

    if (!screen.preload) return;
    await screen.preload(currentContext());
    if (token !== preloadToken) return;
    renderScreen();
  }

  function syncRoute() {
    store.setRoute(parseHash(location.hash));
  }

  function start() {
    store.subscribe((type) => {
      if (type === "route") {
        renderShellState();
        renderScreen();
        preloadRoute().catch(() => {});
        return;
      }

      if (type === "connection") {
        renderShellState();
        return;
      }

      if (type === "sim") {
        renderShellState();
        renderScreen();
        return;
      }

      if (["ui", "flights", "planes", "logs"].includes(type)) {
        renderScreen();
      }
    });

    window.addEventListener("hashchange", syncRoute);
    window.setInterval(() => store.advanceSimClock(), 1000);
    ensureShell();
    syncRoute();
  }

  return { start, render: renderScreen };
}
