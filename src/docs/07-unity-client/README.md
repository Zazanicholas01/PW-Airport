# Unity client integration

Unity is the “world renderer” and event source, while Python is authoritative for time and scheduling.

## Unity responsibilities (high level)

- Connect to backend websocket (`ws://localhost:8765`)
- During setup:
  - send spline registry (including `MasterSpline`)
  - send prefab registry
- During runtime:
  - spawn prefabs on backend command
  - follow assigned spline segments (`start_path`)
  - emit events (`path_completed`, `plane_left_stand`)
  - send time control commands (`set_time_scale`, `set_sim_time`) when applicable

## Backend setup expectations

The setup handler (`../../handlers/setup_bus.py`) expects to see the setup control sequence:

- `setup-init`
- `send-splines` ... `finish-send-splines`
- `send-prefabs` ... `finish-send-prefabs`

## Where to look

- Unity scripts: `../../../Unity_Scripts`
- Setup handler: `../../handlers/setup_bus.py`
- Path generation: `../../init_graph.py` + `../../../schema_nodi.json`

