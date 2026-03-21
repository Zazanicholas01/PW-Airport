# Handlers

This topic consolidates `../../handlers/` behavior from `../../handlers/README.md`.

## Setup handler (`SetupBusHandler`)

File: `../../handlers/setup_bus.py`

Responsibilities:

- buffer spline and prefab batches sent by Unity
- feed splines to `InitGraph` (`../../init_graph.py`)
- feed prefabs to `PrefabStore` (`../../domain/prefab_store.py`)
- extract stand positions + landing spawn reference
- rebuild and persist DB `Path` rows (`Percorso`)
- mark setup complete and ignore later setup payloads

## Runtime handler (`RuntimeBusHandler`)

File: `../../handlers/runtime_bus.py`

Responsibilities:

- process runtime events after setup completion
- react to `path_completed` and `plane_left_stand`
- update DB state (airplane/flight/stand)
- manage disembark timers in simulation time (time-scale aware)

## Next reads

- Full handler guide: `../../handlers/README.md`
- Simulation clock: `../11-domain/README.md`
