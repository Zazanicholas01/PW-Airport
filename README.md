Setup Git & Github

    - Clonare Repository GitHub
        - git clone <nome_repository>
        - cd <cartella_creata>
    
    - Creare Nuovi Branches & Spostarsi su Branch di Lavoro
        - git branch -c dev && git branch -c start
        - git checkout start

docker compose up -d

Connection to metabase at:
    - http://localhost:3000

Connection string for metabase:
    - postgresql://airport:airport@postgres:5432/Airport

Recreate Database:
    - python3 -m db

Add Startup Static Values:
    - python3 -m src.startup
