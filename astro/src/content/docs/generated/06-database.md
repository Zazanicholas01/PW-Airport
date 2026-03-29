---
title: Database
---

# Database

This topic is derived from `../../db/README.md` and `../../../scripts/`.

## Schema and models

Core SQLAlchemy models live in:

- `../../db/models.py`

Key entities (high level):

- `Flight` (`Viaggio`), `Airplane` (`Aereo`), `Stand` (`Piazzola`), `Path` (`Percorso`)

DB engine/session helpers:

- `../../db/engine.py`

## Initialization and seeding

- Schema creation/reset: `../../../scripts/init_db.py`
- Static seed (airports, airlines, terminals, stands, vehicles, …): `../../../scripts/startup.py`

## Runtime queries and transitions

Most domain-level DB transitions are in:

- `../../db/db_functions.py`

Examples:

- sliding-window queries for scheduler decisions
- stand reservation/linking
- airplane/flight status transitions

## Next reads

- `../../db/README.md` (full workflow guide)
- Message vocabulary: `../14-message-contracts/standard_vocabulary.md`
