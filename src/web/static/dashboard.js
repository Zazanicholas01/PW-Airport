(function () {
  const eventsRoot = document.getElementById("events");
  const departureRows = document.getElementById("departure_rows");
  const arrivalRows = document.getElementById("arrival_rows");
  const planesRows = document.getElementById("plane_rows");
  const simTimeStatus = document.getElementById("sim-time-status");
  const simScaleStatus = document.getElementById("sim-scale-status");
  const airportStatus = document.getElementById("airport-status");
  const flightsCountStatus = document.getElementById("flights-count-status");
  const weatherStatus = document.getElementById("weather-status");
  const maxRows = 20;

  let clockAnchor = null;
  let latestFlightRows = [];

  weatherStatus.textContent = "Unavailable";

  function makeCell(className, value) {
    const node = document.createElement("div");
    node.className = className;
    node.textContent = value || "";
    return node;
  }

  function renderEvent(event) {
    const row = document.createElement("div");
    row.className = "logline lvl-" + (event.level || "INFO");
    row.appendChild(makeCell("ts", event.ts || "--:--:--"));
    row.appendChild(makeCell("lvl", event.level || "INFO"));
    row.appendChild(makeCell("sub", event.subsystem || "-"));
    row.appendChild(makeCell("msg", event.message || ""));
    row.appendChild(makeCell("fields", event.fields || ""));
    return row;
  }

  function renderSnapshot(events) {
    eventsRoot.innerHTML = "";
    if (!events.length) {
      eventsRoot.appendChild(
        renderEvent({
          ts: "--:--:--",
          level: "INFO",
          subsystem: "dashboard",
          message: "No log events found in data/logs/events.jsonl.",
          fields: "",
        })
      );
      return;
    }

    events.forEach((event) => {
      eventsRoot.appendChild(renderEvent(event));
    });
    eventsRoot.scrollTop = eventsRoot.scrollHeight;
  }

  function appendEvents(events) {
    if (!events.length) return;

    const placeholder = eventsRoot.querySelector(".logline .msg");
    if (placeholder && placeholder.textContent.includes("Connecting")) {
      eventsRoot.innerHTML = "";
    }

    events.forEach((event) => {
      eventsRoot.appendChild(renderEvent(event));
    });

    while (eventsRoot.children.length > maxRows) {
      eventsRoot.removeChild(eventsRoot.firstElementChild);
    }

    eventsRoot.scrollTop = eventsRoot.scrollHeight;
  }

  function currentSimUnixMs() {
    if (!clockAnchor) return null;
    const elapsedRealMs = Date.now() - clockAnchor.receivedAtMs;
    return clockAnchor.simUnixMs + elapsedRealMs * clockAnchor.timeScale;
  }

  function formatDeltaMinutes(referenceUnixMs) {
    const simUnixMs = currentSimUnixMs();
    if (simUnixMs === null || referenceUnixMs === null || referenceUnixMs === undefined) {
      return "--";
    }
    return String(Math.round((referenceUnixMs - simUnixMs) / 60000));
  }

  function renderFlightRows(targetBody, rows, emptyMessage) {
    targetBody.innerHTML = "";

    if (!rows.length) {
      const emptyRow = document.createElement("tr");
      emptyRow.innerHTML = `<td colspan="8" class="muted">${emptyMessage}</td>`;
      targetBody.appendChild(emptyRow);
      return;
    }

    const fragment = document.createDocumentFragment();

    rows.forEach((row) => {
      const tr = document.createElement("tr");
      tr.className = "clickable-row";
      tr.addEventListener("click", () => {
        window.location.href = `/flight/${encodeURIComponent(row.id)}`;
      });
      tr.innerHTML = `
        <td><span class="display-cell display-time">${row.dep_time || "--:--"}</span></td>
        <td><span class="display-cell display-time">${row.arr_time || "--:--"}</span></td>
        <td>
          <span class="display-cell display-delta" data-role="delta-min" data-reference-unix-ms="${row.reference_unix_ms ?? ""}">
            ${formatDeltaMinutes(row.reference_unix_ms)}
          </span>
        </td>
        <td>${row.flight || "--"}</td>
        <td>${row.route || "--"}</td>
        <td>${row.type || "--"}</td>
        <td><span class="pill ${row.status_class || "status-default"}">${row.status || "--"}</span></td>
        <td class="muted">${row.airplane || "--"}</td>
      `;
      fragment.appendChild(tr);
    });

    targetBody.appendChild(fragment);
  }

  function renderPlanesSnapshot(planesSnapshot) {
    const rows = (planesSnapshot && planesSnapshot.rows) || [];
    planesRows.innerHTML = "";

    if (!rows.length) {
      const emptyRow = document.createElement("tr");
      emptyRow.innerHTML = '<td colspan="8" class="muted">No planes currently tracked on ground.</td>';
      planesRows.appendChild(emptyRow);
      return;
    }

    const fragment = document.createDocumentFragment();

    rows.forEach((row) => {
      const tr = document.createElement("tr");
      tr.className = "clickable-row";
      tr.addEventListener("click", () => {
        window.location.href = `/plane/${encodeURIComponent(row.airplane)}`;
      });
      tr.innerHTML = `
        <td>${row.airplane || "--"}</td>
        <td><span class="pill ${row.status_class || "status-default"}">${row.status || "--"}</span></td>
        <td class="muted">${row.model || "--"}</td>
        <td>${row.type || "--"}</td>
        <td>${row.range || "--"}</td>
        <td class="muted">${row.speed || "--"}</td>
        <td class="muted">${row.stand || "--"}</td>
        <td class="muted">${row.route || "--"}</td>
      `;
      fragment.appendChild(tr);
    });

    planesRows.appendChild(fragment);
  }

  function renderFlightsSnapshot(windowSnapshot) {
    const rows = (windowSnapshot && windowSnapshot.rows) || [];
    latestFlightRows = rows;
    airportStatus.textContent = windowSnapshot && windowSnapshot.airport_icao ? windowSnapshot.airport_icao : "LIAG";
    flightsCountStatus.textContent = String(rows.length);

    const departures = rows.filter((row) => row.direction === "departure");
    const arrivals = rows.filter((row) => row.direction === "arrival");

    renderFlightRows(departureRows, departures, "No departures currently in the scheduling window.");
    renderFlightRows(arrivalRows, arrivals, "No arrivals currently in the scheduling window.");
  }

  function formatSimTime(date) {
    return new Intl.DateTimeFormat([], {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    }).format(date);
  }

  function renderClock() {
    if (!clockAnchor) return;
    const simUnixMs = currentSimUnixMs();
    simTimeStatus.textContent = formatSimTime(new Date(simUnixMs));
    simScaleStatus.textContent = "x" + clockAnchor.timeScale.toFixed(2);
  }

  function refreshFlightDeltas() {
    [departureRows, arrivalRows].forEach((body) => {
      const deltaCells = body.querySelectorAll('[data-role="delta-min"]');
      deltaCells.forEach((cell) => {
        const referenceUnixMs = Number(cell.dataset.referenceUnixMs || "");
        cell.textContent = Number.isFinite(referenceUnixMs)
          ? formatDeltaMinutes(referenceUnixMs)
          : "--";
      });
    });
  }

  function applyClockSync(clock) {
    clockAnchor = {
      simUnixMs: clock.sim_unix_ms,
      timeScale: clock.time_scale,
      syncId: clock.sync_id,
      receivedAtMs: Date.now(),
    };
    renderClock();
  }

  const scheme = window.location.protocol === "https:" ? "wss" : "ws";

  const eventsSocket = new WebSocket(`${scheme}://${window.location.host}/ws/events`);
  eventsSocket.addEventListener("message", (messageEvent) => {
    const payload = JSON.parse(messageEvent.data);
    if (payload.kind === "snapshot") renderSnapshot(payload.events || []);
    if (payload.kind === "append") appendEvents(payload.events || []);
  });
  eventsSocket.addEventListener("close", () => {
    appendEvents([{
      ts: "--:--:--",
      level: "WARNING",
      subsystem: "dashboard",
      message: "Live event stream disconnected.",
      fields: "",
    }]);
  });

  const clockSocket = new WebSocket(`${scheme}://${window.location.host}/ws/clock`);
  clockSocket.addEventListener("message", (messageEvent) => {
    const payload = JSON.parse(messageEvent.data);
    if (payload.kind === "sync" && payload.clock) {
      applyClockSync(payload.clock);
    }
  });
  clockSocket.addEventListener("close", () => {
    simTimeStatus.textContent = "Sim Time: disconnected";
  });

  const flightsSocket = new WebSocket(`${scheme}://${window.location.host}/ws/window-flights`);
  flightsSocket.addEventListener("message", (messageEvent) => {
    const payload = JSON.parse(messageEvent.data);
    if (payload.kind === "snapshot" && payload.window) {
      renderFlightsSnapshot(payload.window);
    }
  });
  flightsSocket.addEventListener("close", () => {
    renderFlightsSnapshot({ rows: [] });
  });

  const planesSocket = new WebSocket(`${scheme}://${window.location.host}/ws/planes-ground`);
  planesSocket.addEventListener("message", (messageEvent) => {
    const payload = JSON.parse(messageEvent.data);
    if (payload.kind === "snapshot" && payload.planes) {
      renderPlanesSnapshot(payload.planes);
    }
  });
  planesSocket.addEventListener("close", () => {
    renderPlanesSnapshot({ rows: [] });
  });

  renderClock();
  window.setInterval(renderClock, 250);
  window.setInterval(refreshFlightDeltas, 250);
})();
