# Transport (WebSocket)

This topic is derived from `../../transport/README.md`.

## Scope

Transport is responsible for:

- WebSocket server lifecycle and per-connection session state
- decoding/encoding message payloads
- routing incoming payloads to the correct handler (setup vs runtime)
- orchestrating background tasks (clock sync, spawns, flight scheduling)

## Key files

- `../../transport/ws_server.py`: orchestration and task loops
- `../../transport/message_bus.py`: internal async queues and dispatch boundary

## End-to-end flow (per connection)

1. Server bootstrap from `../../server.py`
2. On connection:
   - send initial `welcome`
   - start dispatcher loops
3. Incoming messages:
   - routed to setup handler until setup completes
   - then routed to runtime handler
4. Clock:
   - authoritative clock in `../../domain/sim_clock.py`
   - periodic `clock_sync` pushed to Unity and dashboard event log

## Next reads

- Full transport guide: `../../transport/README.md`
- Message contracts: `../14-message-contracts/README.md`
