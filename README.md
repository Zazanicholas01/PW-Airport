docker compose up -d

python3 db.py

Connection to metabase at:
    - http://localhost:3000

Connection string for metabase:
    - postgresql://airport:airport@postgres:5432/Airport

Unity MR Project:
    - MRProject/ folder (Meta Quest/Oculus)

Run websocket server:
    - python -m src.server

CSV logs are written to:
    - csv_log/pos.csv
    - csv_log/route_log.csv
    - csv_log/speed_log.csv
