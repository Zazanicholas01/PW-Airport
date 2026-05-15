(function () {
  const departureRows = document.getElementById("departure_rows");
  const arrivalRows = document.getElementById("arrival_rows");
  let lastFlightsSig = "";

  function stableSig(value) {
    return JSON.stringify(value);
  }

  function renderFlightRows(targetBody, rows, emptyMessage) {
    if (!targetBody) return;

    targetBody.innerHTML = "";

    if (!rows.length) {
      const emptyRow = document.createElement("tr");
      emptyRow.innerHTML = `<td colspan="7" class="muted">${emptyMessage}</td>`;
      targetBody.appendChild(emptyRow);
      return;
    }

    const fragment = document.createDocumentFragment();

    rows.forEach((row) => {
      const headerRow = document.createElement("tr");
      headerRow.className = "flight-group-header";
      headerRow.innerHTML = `
        <td colspan="7" class="flight-group-title">
          <span class="flight-group-title-text">${row.card_title || row.route || "--"}</span>
          <span class="pill ${row.status_class || "status-default"}">${row.status || "--"}</span>
        </td>
      `;

      const tr = document.createElement("tr");
      tr.className = "clickable-row flight-card-row";
      tr.dataset.href = `/flight/${encodeURIComponent(row.id)}`;

      tr.innerHTML = `
        <td><span class="display-cell display-time">${row.departure_time || row.dep_time || "--:--"}</span></td>
        <td><span class="display-cell display-time">${row.arrival_time || row.arr_time || "--:--"}</span></td>
        <td><span class="display-cell display-delta">${row.delta_time || "--"}</span></td>
      `;

      fragment.appendChild(headerRow);
      fragment.appendChild(tr);
    });

    targetBody.appendChild(fragment);
  }

  function renderFlightsSnapshot(windowSnapshot) {
    const rows = (windowSnapshot && windowSnapshot.rows) || [];
    const sig = stableSig(rows);
    if (sig === lastFlightsSig) {
      return;
    }

    lastFlightsSig = sig;

    const departures = rows.filter((row) => row.direction === "departure");
    const arrivals = rows.filter((row) => row.direction === "arrival");

    renderFlightRows(
      departureRows,
      departures,
      "No departures currently in the scheduling window."
    );
    renderFlightRows(
      arrivalRows,
      arrivals,
      "No arrivals currently in the scheduling window."
    );
  }

  document.addEventListener("click", (event) => {
    const row = event.target.closest(".clickable-row[data-href]");
    if (!row) return;
    window.location.href = row.dataset.href;
  });

  const scheme = window.location.protocol === "https:" ? "wss" : "ws";
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
})();
