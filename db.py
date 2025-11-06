"""Database bootstrap utility for the PW Airport project.

This script connects to the Postgres instance defined in docker-compose.yml,
recreates the Airport database from scratch, and ensures the schema is present.
Run it after the containers are up:

    docker compose up -d
    pip install psycopg[binary]
    python db.py
"""

from __future__ import annotations

import os
import sys
from typing import Iterable

try:
    import psycopg  # type: ignore
    from psycopg import sql  # type: ignore
except ImportError as exc:  # pragma: no cover - setup guard
    raise SystemExit(
        "Missing dependency: psycopg. Install it with `pip install psycopg[binary]` "
        "inside your virtual environment before running this script."
    ) from exc


DB_NAME = os.getenv("POSTGRES_DB", "Airport")
DB_USER = os.getenv("POSTGRES_USER", "airport")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "airport")
DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")
ADMIN_DB = os.getenv("POSTGRES_ADMIN_DB", "postgres")


DROP_STATEMENTS = [
    'DROP TABLE IF EXISTS "Operazione" CASCADE;',
    'DROP TABLE IF EXISTS "Merce" CASCADE;',
    'DROP TABLE IF EXISTS "Passeggero" CASCADE;',
    'DROP TABLE IF EXISTS "Percorso" CASCADE;',
    'DROP TABLE IF EXISTS "Veicolo" CASCADE;',
    'DROP TABLE IF EXISTS "Viaggio" CASCADE;',
    'DROP TABLE IF EXISTS "Piazzola" CASCADE;',
    'DROP TABLE IF EXISTS "Aereo" CASCADE;',
    'DROP TABLE IF EXISTS "Terminal" CASCADE;',
]

CREATE_AND_ALTER_STATEMENTS = [
    '''
    CREATE TABLE "Viaggio"(
        "id" INTEGER NOT NULL,
        "id_aereo" VARCHAR(255) NOT NULL,
        "orario_arrivo" TIMESTAMP(0) WITHOUT TIME ZONE NOT NULL,
        "orario_partenza" TIMESTAMP(0) WITHOUT TIME ZONE NOT NULL,
        "id_terminal" INTEGER NOT NULL,
        "id_piazzola" VARCHAR(255) NOT NULL,
        "provenienza" VARCHAR(255) NOT NULL,
        "destinazione" VARCHAR(255) NOT NULL
    );
    ''',
    'ALTER TABLE "Viaggio" ADD PRIMARY KEY("id");',
    '''
    CREATE TABLE "Aereo"(
        "Id" VARCHAR(255) NOT NULL,
        "Tipo" VARCHAR(255) NOT NULL,
        "Tratta" VARCHAR(255) NOT NULL,
        "Modello" VARCHAR(255) NOT NULL,
        "Capacita" INTEGER NOT NULL,
        "Posizione" jsonb NOT NULL,
        "Stato" VARCHAR(255) NOT NULL,
        "Velocita" FLOAT(53) NOT NULL,
        "Livello_Carburante" FLOAT(53) NOT NULL,
        "Manutenzione" BOOLEAN NOT NULL,
        "lista_waypoints" jsonb NOT NULL
    );
    ''',
    'ALTER TABLE "Aereo" ADD PRIMARY KEY("Id");',
    '''
    CREATE TABLE "Piazzola"(
        "id" VARCHAR(255) NOT NULL,
        "Tipo" VARCHAR(255) NOT NULL,
        "id_terminal" INTEGER NOT NULL,
        "Stato" VARCHAR(255) NOT NULL,
        "id_aereo" VARCHAR(255) NOT NULL,
        "Posizione" jsonb NOT NULL,
        "id_percorso" INTEGER NOT NULL
    );
    ''',
    'ALTER TABLE "Piazzola" ADD PRIMARY KEY("id");',
    '''
    CREATE TABLE "Terminal"(
        "id" INTEGER NOT NULL,
        "Tipo" VARCHAR(255) NOT NULL,
        "Capacita" INTEGER NOT NULL
    );
    ''',
    'ALTER TABLE "Terminal" ADD PRIMARY KEY("id");',
    '''
    CREATE TABLE "Veicolo"(
        "id" INTEGER NOT NULL,
        "Tipo" VARCHAR(255) NOT NULL,
        "Capacita" INTEGER NOT NULL,
        "Posizione" jsonb NOT NULL,
        "Destinazione" VARCHAR(255) NOT NULL,
        "Stato" VARCHAR(255) NOT NULL,
        "Velocita" FLOAT(53) NOT NULL,
        "Percorso" jsonb NOT NULL,
        "id_viaggio" INTEGER NOT NULL
    );
    ''',
    'ALTER TABLE "Veicolo" ADD PRIMARY KEY("id");',
    '''
    CREATE TABLE "Operazione"(
        "id" INTEGER NOT NULL,
        "TIpo" VARCHAR(255) NOT NULL,
        "id_viaggio" INTEGER NOT NULL,
        "id_aereo" VARCHAR(255) NOT NULL,
        "id_piazzola" VARCHAR(255) NOT NULL,
        "Stato" VARCHAR(255) NOT NULL
    );
    ''',
    'ALTER TABLE "Operazione" ADD PRIMARY KEY("id");',
    '''
    CREATE TABLE "Percorso"(
        "id" INTEGER NOT NULL,
        "Tipo" VARCHAR(255) NOT NULL,
        "Lista_Waypoints" jsonb NOT NULL,
        "Distanza" FLOAT(53) NOT NULL,
        "id_veicolo" INTEGER NOT NULL,
        "Stato" VARCHAR(255) NOT NULL
    );
    ''',
    'ALTER TABLE "Percorso" ADD PRIMARY KEY("id");',
    '''
    CREATE TABLE "Passeggero"(
        "id" VARCHAR(255) NOT NULL,
        "Nome" VARCHAR(255) NOT NULL,
        "Cognome" VARCHAR(255) NOT NULL,
        "Sesso" VARCHAR(255) NOT NULL,
        "Eta" INTEGER NOT NULL,
        "id_viaggio" INTEGER NOT NULL
    );
    ''',
    'ALTER TABLE "Passeggero" ADD PRIMARY KEY("id");',
    '''
    CREATE TABLE "Merce"(
        "id" VARCHAR(255) NOT NULL,
        "id_viaggio" INTEGER NOT NULL,
        "Tipo" VARCHAR(255) NOT NULL,
        "Quantita" INTEGER NOT NULL,
        "Peso" FLOAT(53) NOT NULL
    );
    ''',
    'ALTER TABLE "Merce" ADD PRIMARY KEY("id");',
    'ALTER TABLE "Viaggio" ADD CONSTRAINT "viaggio_id_aereo_foreign" FOREIGN KEY("id_aereo") REFERENCES "Aereo"("Id");',
    'ALTER TABLE "Passeggero" ADD CONSTRAINT "passeggero_id_viaggio_foreign" FOREIGN KEY("id_viaggio") REFERENCES "Viaggio"("id");',
    'ALTER TABLE "Piazzola" ADD CONSTRAINT "piazzola_id_terminal_foreign" FOREIGN KEY("id_terminal") REFERENCES "Terminal"("id");',
    'ALTER TABLE "Viaggio" ADD CONSTRAINT "viaggio_id_terminal_foreign" FOREIGN KEY("id_terminal") REFERENCES "Terminal"("id");',
    'ALTER TABLE "Merce" ADD CONSTRAINT "merce_id_viaggio_foreign" FOREIGN KEY("id_viaggio") REFERENCES "Viaggio"("id");',
    'ALTER TABLE "Piazzola" ADD CONSTRAINT "piazzola_id_aereo_foreign" FOREIGN KEY("id_aereo") REFERENCES "Aereo"("Id");',
    'ALTER TABLE "Percorso" ADD CONSTRAINT "percorso_id_veicolo_foreign" FOREIGN KEY("id_veicolo") REFERENCES "Veicolo"("id");',
    'ALTER TABLE "Operazione" ADD CONSTRAINT "operazione_id_piazzola_foreign" FOREIGN KEY("id_piazzola") REFERENCES "Piazzola"("id");',
    'ALTER TABLE "Piazzola" ADD CONSTRAINT "piazzola_id_percorso_foreign" FOREIGN KEY("id_percorso") REFERENCES "Percorso"("id");',
    'ALTER TABLE "Operazione" ADD CONSTRAINT "operazione_id_viaggio_foreign" FOREIGN KEY("id_viaggio") REFERENCES "Viaggio"("id");',
    'ALTER TABLE "Veicolo" ADD CONSTRAINT "veicolo_id_viaggio_foreign" FOREIGN KEY("id_viaggio") REFERENCES "Viaggio"("id");',
    'ALTER TABLE "Viaggio" ADD CONSTRAINT "viaggio_id_piazzola_foreign" FOREIGN KEY("id_piazzola") REFERENCES "Piazzola"("id");',
    'ALTER TABLE "Operazione" ADD CONSTRAINT "operazione_id_aereo_foreign" FOREIGN KEY("id_aereo") REFERENCES "Aereo"("Id");',
]


def _execute_statements(cursor: psycopg.Cursor, statements: Iterable[str]) -> None:
    """Run each SQL statement sequentially."""
    for statement in statements:
        sql_statement = statement.strip()
        if not sql_statement:
            continue
        cursor.execute(sql_statement)


def recreate_database() -> None:
    """Drop and recreate the target database to ensure a clean state."""
    print(f"Recreating database {DB_NAME!r} using admin database {ADMIN_DB!r}...")
    with psycopg.connect(
        dbname=ADMIN_DB,
        user=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT,
        autocommit=True,
    ) as admin_connection:
        with admin_connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT pg_terminate_backend(pid)
                FROM pg_stat_activity
                WHERE datname = %s
                  AND pid <> pg_backend_pid();
                """,
                (DB_NAME,),
            )
            cursor.execute(
                sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(DB_NAME))
            )
            cursor.execute(
                sql.SQL("CREATE DATABASE {}").format(sql.Identifier(DB_NAME))
            )


def create_schema() -> None:
    """Connect to Postgres and recreate the airport schema."""
    connection = psycopg.connect(
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT,
    )

    with connection:
        with connection.cursor() as cursor:
            _execute_statements(cursor, DROP_STATEMENTS)
            _execute_statements(cursor, CREATE_AND_ALTER_STATEMENTS)


def main() -> None:
    print(
        f"Connecting to Postgres at {DB_HOST}:{DB_PORT} "
        f"as {DB_USER} (database: {DB_NAME})..."
    )
    recreate_database()
    create_schema()
    print("Schema created successfully.")


if __name__ == "__main__":
    main()
