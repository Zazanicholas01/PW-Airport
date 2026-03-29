---
title: Dashboard Reset Checklist
layout: ../../layouts/DocsLayout.astro
---

# Dashboard Reset Checklist

Goal: preserve the current dashboard HTML shell, CSS, and visual rendering style/layout, while removing the existing dashboard behavior and data plumbing so the dashboard can be rebuilt from scratch.

## Keep

These files define the current outer shell, styling, and visual assets. Keep them as the baseline unless you intentionally want to redesign the UI.

- `src/web/templates/dashboard.html`
  - Keep as the HTML entry shell.
  - It is currently minimal: `.shell`, `.panel`, and `#app`.
- `src/web/static/dashboard.css`
  - Keep as the main styling source.
  - This contains the board theme, layout primitives, table styling, pills, log styling, responsive rules, and image/detail layout.
- `src/web/static/background-airport.png`
  - Keep if you want the current background look.
- `src/web/static/background-airports.png`
  - Keep only if you still plan to use it; I did not find an active reference in the current dashboard HTML/CSS entry path.
- `src/web/static/planes/`
  - Keep only if the redesign will still render plane images.
  - Includes fallback and model images used by the current detail views.

## Keep With Review

These are presentation-oriented, but the current implementation is tightly mixed with old client behavior. Keep only if you want to salvage markup patterns instead of rebuilding them.

- `src/web/static/app/components/app-shell.js`
  - Reusable only as a reference for the current top bar/nav/status markup.
  - Not a clean keep if the app is being restarted from scratch.
- `src/web/static/app/components/flight-table.js`
  - Keep only as a markup reference for the flight board rows.
- `src/web/static/app/components/plane-table.js`
  - Keep only as a markup reference for the plane board rows.
- `src/web/static/app/components/event-log.js`
  - Keep only as a markup reference if you want the same log block structure.
- `src/web/static/app/components/detail-table.js`
  - Keep only as a markup reference for detail pages.
- `src/web/static/app/lib/format.js`
  - Keep only if you want to reuse current formatting helpers during the rebuild.
- `src/web/static/app/lib/dom.js`
  - Keep only if you want its DOM delegation helper.

## Delete

These files are the broken dashboard application logic, routing, refresh flow, API glue, and backend projection/event machinery. They are the correct reset candidates if the goal is “keep look and layout, remove dashboard system.”

### Client app/runtime

- `src/web/static/dashboard.js`
- `src/web/static/app/router.js`
- `src/web/static/app/store.js`
- `src/web/static/app/lib/routes.js`
- `src/web/static/app/services/api.js`
- `src/web/static/app/services/events.js`
- `src/web/static/app/services/refresh.js`
- `src/web/static/app/services/sim-clock.js`
- `src/web/static/app/screens/overview.js`
- `src/web/static/app/screens/schedule.js`
- `src/web/static/app/screens/kpi.js`
- `src/web/static/app/screens/resource-detail.js`
- `src/web/static/app/screens/not-found.js`

### Backend dashboard-specific runtime

- `src/web/dashboard_app.py`
  - Delete only after replacing it with a much smaller new app entrypoint that still serves `dashboard.html` and `/static`.
- `src/web/dashboard_projection.py`
- `src/web/dashboard_bridge.py`
- `src/web/dashboard_bus.py`
- `src/web/dashboard_sse.py`
- `src/web/contracts.py`

### Tests tied to old backend behavior

- `tests/test_dashboard_projection.py`

## Replace, Do Not Simply Delete

These are current entrypoints or references that should be updated as part of the reset, not just removed and forgotten.

- `src/web/dashboard_app.py`
  - Replace with a minimal app that:
  - serves `/` -> `dashboard.html`
  - mounts `/static`
  - optionally exposes only the new APIs you choose to rebuild
- `src/web/templates/dashboard.html`
  - Update the `<script>` tag to point to the new frontend entry file once created.
- `scripts/run_dashboard_dev.ps1`
  - Update the uvicorn target if the new app module name changes.
- `docker-compose.yml`
  - Update the dashboard service command if the new app module name changes.

## Docs and References To Clean Up After Reset

These should not be deleted first, but they will become misleading once the old dashboard implementation is removed.

- `README.md`
- `src/web/README.md`
- `astro/src/pages/00-general-overview/index.mdx`
- `astro/src/pages/01-architecture/index.mdx`
- `astro/src/pages/04-local-run/index.mdx`
- `astro/src/pages/13-dashboard-web/index.mdx`
- `src/db/README.md`
- `src/domain/README.md`
- `tasks_activity.txt`

## Recommended Deletion Order

1. Preserve a copy of:
   - `src/web/templates/dashboard.html`
   - `src/web/static/dashboard.css`
   - any image assets you still want
2. Create the new minimal dashboard app entrypoint.
3. Point `dashboard.html` to the new frontend entry file.
4. Remove old client runtime files under `src/web/static/app/` and old `src/web/static/dashboard.js`.
5. Remove old backend dashboard runtime files in `src/web/`.
6. Remove old tests tied to projection/SSE behavior.
7. Clean up scripts, compose config, and docs.

## Safety Notes

- The current visible layout is not stored in HTML alone. Most screen structure is generated in JavaScript.
- If you delete all JS immediately, `dashboard.html` will still render the outer shell but not the current boards/content.
- If you want to preserve the current rendered board markup exactly, first copy the relevant markup patterns out of:
  - `src/web/static/app/components/app-shell.js`
  - `src/web/static/app/screens/schedule.js`
  - `src/web/static/app/components/flight-table.js`
  - `src/web/static/app/components/plane-table.js`

## Practical Boundary

If the reset rule is strict, the safest interpretation is:

- Keep:
  - `src/web/templates/dashboard.html`
  - `src/web/static/dashboard.css`
  - selected static images
- Rebuild from scratch:
  - everything else under `src/web/` related to dashboard behavior
