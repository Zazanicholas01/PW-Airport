docker compose up -d

Connection to metabase at:
    - http://localhost:3002

Connection string for metabase:
    - postgresql://airport:airport@postgres:5432/Airport

Recreate Database:
    - python3 -m db

Add Startup Static Values:
    - python3 -m src.startup
