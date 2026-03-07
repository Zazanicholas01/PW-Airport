export function parseHash(hash) {
  const value = hash || "#/overview";
  const resourceMatch = value.match(/^#\/resource\/([^/]+)\/(.+)$/);
  const planeAlias = value.match(/^#plane\/(.+)$/);
  const flightAlias = value.match(/^#flight\/(.+)$/);

  if (value === "#" || value === "" || value === "#/" || value === "#/overview") {
    return { name: "overview", params: {}, canonicalHash: "#/overview" };
  }
  if (value === "#/schedule") {
    return { name: "schedule", params: {}, canonicalHash: "#/schedule" };
  }
  if (value === "#/kpi") {
    return { name: "kpi", params: {}, canonicalHash: "#/kpi" };
  }
  if (resourceMatch) {
    const [, resourceType, id] = resourceMatch;
    return {
      name: "resource-detail",
      params: { resourceType, id: decodeURIComponent(id) },
      canonicalHash: `#/resource/${resourceType}/${encodeURIComponent(decodeURIComponent(id))}`,
    };
  }
  if (planeAlias) {
    const id = decodeURIComponent(planeAlias[1]);
    return {
      name: "resource-detail",
      params: { resourceType: "plane", id },
      canonicalHash: `#/resource/plane/${encodeURIComponent(id)}`,
    };
  }
  if (flightAlias) {
    const id = decodeURIComponent(flightAlias[1]);
    return {
      name: "resource-detail",
      params: { resourceType: "flight", id },
      canonicalHash: `#/resource/flight/${encodeURIComponent(id)}`,
    };
  }
  return { name: "not-found", params: {}, canonicalHash: "#/not-found" };
}

export function hrefForSchedule() {
  return "#/schedule";
}

export function hrefForOverview() {
  return "#/overview";
}

export function hrefForKpi() {
  return "#/kpi";
}

export function hrefForResource(resourceType, id) {
  return `#/resource/${resourceType}/${encodeURIComponent(String(id))}`;
}
